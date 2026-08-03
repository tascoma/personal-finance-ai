"""Parse phase orchestrator.

Turns one Document into a set of RawTransaction rows in `staged` status. The
heavy decision tree — which extractor to call, deterministic mapper vs LLM —
lives in `parse_document`. Tests should target that function (with stubbed
agents) rather than the routes.
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.mortgage import ExtractedMortgage, run_mortgage_extractor
from app.agents.paystub import ExtractedPaystubs, PaystubLine, run_paystub_extractor
from app.agents.statement import ExtractedStatement, ExtractedTxn, run_statement_extractor
from app.core.config import settings
from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
from app.models.review_queue import ReviewQueue
from app.services.file_readers import (
    ParseError,
    extract_csv_rows,
    extract_pdf_text,
    extract_xlsx_rows,
    read_opening_balances_xlsx,
)
from app.services.scrub import scrub_text
from app.services.statement_mapper import (
    csv_to_transactions_async,
    xlsx_to_transactions_async,
)

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────


async def account_keep_terms(db: AsyncSession) -> list[str]:
    """Chart-of-accounts names that must survive redaction.

    The orchestrator matches a statement to its source account on the
    institution / product name, so those strings are protected from the scrubber
    even when they look like something a rule would redact.
    """
    result = await db.scalars(select(Account.account_name).where(Account.is_active.is_(True)))
    return [name for name in result.all() if name]


async def _pdf_text_for_llm(db: AsyncSession, path: Path, doc_label: str) -> str:
    """Read a PDF and redact it before it becomes an LLM prompt.

    This is the only place full statement text leaves the process, so the scrub
    happens here rather than at each extractor.
    """
    text = extract_pdf_text(path)
    if not settings.scrub_before_llm:
        logger.warning("SCRUB_BEFORE_LLM is off — sending raw %s text to the LLM", doc_label)
        return text
    scrubbed, report = scrub_text(text, keep_terms=await account_keep_terms(db))
    logger.info("Scrubbed %s %s: %s", doc_label, path.name, report.summary())
    return scrubbed


def _normalize_description(desc: str) -> str:
    return re.sub(r"\s+", " ", desc.strip().lower())


def _dedup_hash(period_id: uuid.UUID, txn_date: object, description: str, amount: Decimal) -> str:
    payload = f"{period_id}|{txn_date}|{_normalize_description(description)}|{amount}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _wildcard_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a paystub mapping like ``INS MED U *`` or ``CO STK CONT|STOCK PURCH``
    into an anchored regex. ``*`` matches anything; ``|`` separates alternatives."""
    alternatives = [alt.strip() for alt in pattern.split("|") if alt.strip()]
    parts = []
    for alt in alternatives:
        escaped = re.escape(alt).replace(r"\*", ".*")
        parts.append(escaped)
    joined = "|".join(parts)
    return re.compile(rf"^(?:{joined})$", re.IGNORECASE)


# ── account suggestion ──────────────────────────────────────────────────────


async def suggest_for_paystub_line(
    db: AsyncSession, label: str
) -> tuple[int | None, Decimal]:
    """Return (account_code, confidence) for a paystub line label.

    Matches against `Account.paystub_mapping`. ``*`` is a wildcard, ``|`` lists
    alternatives. Exact-or-wildcard match → confidence 1.000; no match → (None, 0).
    """
    result = await db.scalars(
        select(Account).where(Account.paystub_mapping.is_not(None))
    )
    accounts = result.all()
    for acct in accounts:
        if not acct.paystub_mapping:
            continue
        pattern = _wildcard_to_regex(acct.paystub_mapping)
        if pattern.match(label.strip()):
            return acct.account_code, Decimal("1.000")
    return None, Decimal("0")


async def suggest_for_statement_txn(
    db: AsyncSession, description: str, source_account_code: int | None
) -> tuple[int | None, Decimal]:
    """v1: deterministic auto-classification is deferred to the Journal phase.

    This signature exists so the orchestrator's call site is stable; the Journal
    phase agent will replace this with full-context classification.
    """
    return None, Decimal("0")


# ── orchestrator ────────────────────────────────────────────────────────────


async def parse_document(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> int:
    """Parse one Document into RawTransaction rows. Returns row count written."""
    document = await db.get(Document, document_id)
    if document is None:
        raise ParseError("Document not found")

    period = await db.get(Period, document.period_id)
    if period is None:
        raise ParseError("Period not found")
    if period.status not in ("open", "pending_close"):
        raise ParseError("Documents can only be parsed in an open or pending-close period")

    document.parse_status = "in_progress"
    await db.flush()

    prior_txn_ids_result = await db.scalars(
        select(RawTransaction.raw_txn_id).where(RawTransaction.document_id == document_id)
    )
    prior_txn_ids = prior_txn_ids_result.all()
    if prior_txn_ids:
        await db.execute(delete(ReviewQueue).where(ReviewQueue.raw_txn_id.in_(prior_txn_ids)))
    await db.execute(
        delete(RawTransaction).where(RawTransaction.document_id == document_id)
    )

    if document.document_type == "opening_balances":
        try:
            line_count = await _post_opening_balances(db, document)
        except ParseError:
            document.parse_status = "failed"
            await db.commit()
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error posting opening balances for document %s",
                document_id,
                exc_info=True,
            )
            document.parse_status = "failed"
            await db.commit()
            raise ParseError(f"Unexpected parse failure: {exc}") from exc
        document.parse_status = "complete"
        document.parsed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        document.llm_model = None
        await db.commit()
        logger.info(
            "Posted opening-balance entry for document %s with %d lines",
            document_id,
            line_count,
        )
        return line_count

    try:
        transactions, llm_model = await _extract_transactions(
            document=document,
            db=db,
        )
        rows_written = await _persist_transactions(
            db=db,
            document=document,
            transactions=transactions,
        )
    except ParseError:
        document.parse_status = "failed"
        await db.commit()
        raise
    except Exception as exc:
        logger.error(
            "Unexpected error extracting transactions for document %s",
            document_id,
            exc_info=True,
        )
        document.parse_status = "failed"
        await db.commit()
        raise ParseError(f"Unexpected parse failure: {exc}") from exc

    document.parse_status = "complete"
    document.parsed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    document.llm_model = llm_model
    await db.commit()
    logger.info(
        "Parsed document %s into %d raw transactions (model=%s)",
        document_id,
        rows_written,
        llm_model,
    )
    return rows_written


async def parse_period(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> dict[uuid.UUID, int | str]:
    """Parse every pending document in the period.

    Per-document errors are caught and recorded in the result dict so a single
    bad file doesn't abort the rest.
    """
    result_pending = await db.scalars(
        select(Document).where(
            Document.period_id == period_id,
            Document.parse_status == "pending",
        )
    )
    pending: Sequence[Document] = result_pending.all()
    results: dict[uuid.UUID, int | str] = {}
    for doc in pending:
        try:
            count = await parse_document(db, doc.document_id)
            results[doc.document_id] = count
        except ParseError as exc:
            results[doc.document_id] = str(exc)
    return results


# ── extraction dispatch ─────────────────────────────────────────────────────


async def _extract_transactions(
    document: Document,
    db: AsyncSession,
) -> tuple[list["_PreparedTxn"], str | None]:
    """Run the right extractor for this document and return (rows, llm_model_name).

    `_PreparedTxn` carries the suggested account + confidence so persistence
    only has to compute the dedup hash and insert.
    """
    path = Path(document.file_path)
    extension = path.suffix.lower()
    doc_type = document.document_type

    if doc_type == "manual":
        raise ParseError("manual documents are not parsed")

    if doc_type == "opening_balances":
        raise ParseError("opening_balances handled in caller")

    if doc_type == "unknown":
        # Without a resolved type, the dispatch below silently routes any PDF
        # to the statement extractor — which mis-parses paystubs and mortgage
        # statements as bank statements. Force the orchestrator to run first.
        raise ParseError(
            "Document type is 'unknown' — run the orchestrator to classify it before parsing"
        )

    if doc_type == "paystub":
        if extension != ".pdf":
            raise ParseError(f"Paystubs must be .pdf (got {extension})")
        logger.debug("Extracting paystub via LLM: %s", path.name)
        text = await _pdf_text_for_llm(db, path, "paystub")
        extracted: ExtractedPaystubs = await run_paystub_extractor(text)
        prepared = await _prepare_paystub_lines(db, extracted, document.source_account_code)
        return prepared, settings.anthropic_model

    if doc_type == "mortgage_statement":
        if extension != ".pdf":
            raise ParseError(f"Mortgage statements must be .pdf (got {extension})")
        logger.debug("Extracting mortgage statement via LLM: %s", path.name)
        text = await _pdf_text_for_llm(db, path, "mortgage statement")
        extracted_mortgage: ExtractedMortgage = await run_mortgage_extractor(text)
        prepared = _prepare_mortgage_lines(extracted_mortgage, document.period_id)
        return prepared, settings.anthropic_model

    # All other types follow the statement shape regardless of upstream tag.
    # Rows are always decoded deterministically; the LLM is only consulted when the
    # header row itself is unrecognized, so `llm_model` is set only if that happened.
    if extension == ".csv":
        logger.debug("Parsing CSV statement: %s", path.name)
        rows = extract_csv_rows(path)
        txns, used_llm = await csv_to_transactions_async(rows)
        prepared = await _prepare_statement_txns(db, txns, document.source_account_code)
        return prepared, settings.anthropic_model if used_llm else None

    if extension == ".xlsx":
        logger.debug("Parsing XLSX statement: %s", path.name)
        rows_x = extract_xlsx_rows(path)
        txns, used_llm = await xlsx_to_transactions_async(rows_x)
        prepared = await _prepare_statement_txns(db, txns, document.source_account_code)
        return prepared, settings.anthropic_model if used_llm else None

    if extension == ".pdf":
        logger.debug("Extracting PDF statement via LLM: %s", path.name)
        text = await _pdf_text_for_llm(db, path, "statement")
        extracted_stmt: ExtractedStatement = await run_statement_extractor(text)
        prepared = await _prepare_statement_txns(
            db, extracted_stmt.transactions, document.source_account_code
        )
        return prepared, settings.anthropic_model

    raise ParseError(f"Unsupported extension: {extension}")


# ── prepared-row helpers ────────────────────────────────────────────────────


@dataclass(slots=True)
class _PreparedTxn:
    """Internal carrier between extraction and persistence."""

    txn_date: date
    description: str
    amount: Decimal
    suggested_account_code: int | None
    classifier_confidence: Decimal
    is_flagged: bool


async def _prepare_statement_txns(
    db: AsyncSession,
    txns: list[ExtractedTxn],
    source_account_code: int | None,
) -> list[_PreparedTxn]:
    prepared: list[_PreparedTxn] = []
    for t in txns:
        suggested, confidence = await suggest_for_statement_txn(
            db, t.description, source_account_code
        )
        prepared.append(
            _PreparedTxn(
                txn_date=t.txn_date,
                description=t.description,
                amount=Decimal(str(t.amount)),
                suggested_account_code=suggested,
                classifier_confidence=confidence,
                is_flagged=False,
            )
        )
    return prepared


async def _prepare_paystub_lines(
    db: AsyncSession,
    paystubs: ExtractedPaystubs,
    source_account_code: int | None,
) -> list[_PreparedTxn]:
    prepared: list[_PreparedTxn] = []
    for paystub in paystubs.paystubs:
        for line in paystub.lines:
            if line.kind == "net_pay":
                # Include net pay as the cash-to-checking transaction line.
                # suggested_account_code points to the deposit account (source).
                prepared.append(
                    _PreparedTxn(
                        txn_date=paystub.pay_date,
                        description=line.label,
                        amount=Decimal(str(line.amount)),  # always positive
                        suggested_account_code=source_account_code,
                        classifier_confidence=Decimal("1.000") if source_account_code else Decimal("0"),
                        is_flagged=source_account_code is None,
                    )
                )
                continue
            suggested, confidence = await suggest_for_paystub_line(db, line.label)
            if suggested is None:
                logger.warning(
                    "No paystub_mapping match for label %r — line will be flagged for review",
                    line.label,
                )
            signed = _signed_paystub_amount(line)
            prepared.append(
                _PreparedTxn(
                    txn_date=paystub.pay_date,
                    description=line.label,
                    amount=signed,
                    suggested_account_code=suggested,
                    classifier_confidence=confidence,
                    is_flagged=suggested is None,
                )
            )
    return prepared


_MORTGAGE_COMPONENTS: list[tuple[str, str, int]] = [
    ("principal",      "Mortgage Principal",  210102),
    ("interest",       "Mortgage Interest",   510101),
    ("escrow",         "Escrow Deposit",      100202),
    ("property_tax",   "Property Tax",        510102),
    ("home_insurance", "Home Insurance",      510103),
]


def _prepare_mortgage_lines(
    mortgage: ExtractedMortgage,
    period_id: uuid.UUID,
) -> list[_PreparedTxn]:
    prepared: list[_PreparedTxn] = []
    for field, description, account_code in _MORTGAGE_COMPONENTS:
        amount = Decimal(str(getattr(mortgage, field)))
        if amount <= Decimal("0"):
            continue
        prepared.append(
            _PreparedTxn(
                txn_date=mortgage.payment_date,
                description=description,
                amount=-amount,  # outflow from source account (checking)
                suggested_account_code=account_code,
                classifier_confidence=Decimal("1.000"),
                is_flagged=False,
            )
        )
    return prepared


def _signed_paystub_amount(line: PaystubLine) -> Decimal:
    """Earnings are positive; deductions and taxes reduce net pay (stored negative)."""
    amount = Decimal(str(line.amount))
    if line.kind == "earning":
        return amount
    return -amount


# ── opening balances ────────────────────────────────────────────────────────


_ZERO = Decimal("0")


async def _post_opening_balances(db: AsyncSession, document: Document) -> int:
    """Read the opening-balances XLSX and write one balanced JournalEntry.

    Sign convention in the workbook:
      positive balance → debit-normal account (Asset / Expense)
      negative balance → credit-normal account (Liability / Equity / Income)

    The reader only checks shape; we validate sign-vs-account-type here so a
    user-facing ParseError carries the offending account.
    """
    path = Path(document.file_path)
    if path.suffix.lower() != ".xlsx":
        raise ParseError(
            f"Opening balances must be uploaded as .xlsx (got {path.suffix})"
        )
    rows = read_opening_balances_xlsx(path)

    period = await db.get(Period, document.period_id)
    if period is None:
        raise ParseError("Period not found")

    needed_codes = {code for code, _ in rows}
    needed_codes.add(settings.opening_balance_equity_account_code)
    accounts_result = await db.scalars(
        select(Account).where(Account.account_code.in_(needed_codes))
    )
    accounts_by_code: dict[int, Account] = {a.account_code: a for a in accounts_result.all()}

    equity_code = settings.opening_balance_equity_account_code
    if equity_code not in accounts_by_code:
        raise ParseError(
            f"Equity offset account {equity_code} not found in Chart of Accounts — "
            "set OPENING_BALANCE_EQUITY_ACCOUNT_CODE or add the account"
        )

    eid = uuid.uuid4()
    entry = JournalEntry(
        entry_id=eid,
        period_id=document.period_id,
        entry_date=period.period_end,
        description=f"Opening balances — {document.file_name}",
        source_type="adjusting",
        source_document_id=document.document_id,
        is_adjusting=True,
        created_by="python",
    )

    lines: list[JournalLine] = []
    total_debits = _ZERO
    total_credits = _ZERO
    for code, balance in rows:
        if balance == _ZERO:
            continue
        acct = accounts_by_code.get(code)
        if acct is None:
            raise ParseError(f"Account {code} not found in Chart of Accounts")
        amount = abs(balance)
        if balance > _ZERO:
            if acct.normal_balance != "debit":
                raise ParseError(
                    f"Account {code} ({acct.account_name}) is a {acct.account_type} "
                    f"(normal balance: credit) but received a positive value {balance} — "
                    "use a negative number for credit-normal accounts"
                )
            lines.append(JournalLine(
                entry_id=eid,
                account_code=code,
                debit_amount=amount,
                credit_amount=_ZERO,
                memo="Opening balance",
            ))
            total_debits += amount
        else:
            if acct.normal_balance != "credit":
                raise ParseError(
                    f"Account {code} ({acct.account_name}) is a {acct.account_type} "
                    f"(normal balance: debit) but received a negative value {balance} — "
                    "use a positive number for debit-normal accounts"
                )
            lines.append(JournalLine(
                entry_id=eid,
                account_code=code,
                debit_amount=_ZERO,
                credit_amount=amount,
                memo="Opening balance",
            ))
            total_credits += amount

    if not lines:
        raise ParseError("Opening-balances file produced no non-zero lines")

    diff = total_debits - total_credits
    if diff > _ZERO:
        lines.append(JournalLine(
            entry_id=eid,
            account_code=equity_code,
            debit_amount=_ZERO,
            credit_amount=diff,
            memo="Opening balance offset",
        ))
    elif diff < _ZERO:
        lines.append(JournalLine(
            entry_id=eid,
            account_code=equity_code,
            debit_amount=-diff,
            credit_amount=_ZERO,
            memo="Opening balance offset",
        ))
    # If diff == 0 the entry is already balanced (rare but valid).

    db.add(entry)
    for line in lines:
        db.add(line)
    await db.flush()
    return len(lines)


# ── persistence ─────────────────────────────────────────────────────────────


async def _persist_transactions(
    db: AsyncSession,
    document: Document,
    transactions: list[_PreparedTxn],
) -> int:
    if not transactions:
        return 0

    existing_hashes_result = await db.scalars(
        select(RawTransaction.dedup_hash).where(
            RawTransaction.period_id == document.period_id,
            RawTransaction.dedup_hash.is_not(None),
        )
    )
    existing_hashes: set[str] = {h for h in existing_hashes_result.all() if h}

    for txn in transactions:
        dedup = _dedup_hash(document.period_id, txn.txn_date, txn.description, txn.amount)
        is_dup = dedup in existing_hashes
        existing_hashes.add(dedup)
        db.add(
            RawTransaction(
                document_id=document.document_id,
                period_id=document.period_id,
                txn_date=txn.txn_date,
                description=txn.description,
                amount=txn.amount,
                suggested_account_code=txn.suggested_account_code,
                classifier_confidence=txn.classifier_confidence,
                is_flagged=txn.is_flagged,
                is_duplicate=is_dup,
                dedup_hash=dedup,
                status="staged",
            )
        )
    await db.flush()
    return len(transactions)
