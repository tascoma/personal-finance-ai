"""Journal posting service.

Converts approved RawTransactions into balanced double-entry JournalEntry +
JournalLine records. All debit/credit decisions are deterministic Python.

Posting rules
─────────────
Statement transactions (bank_statement, credit_card, investment, mortgage_statement):
  One 2-line entry per transaction.
  amount >= 0  →  Debit source_account,   Credit category_account
  amount <  0  →  Debit category_account, Credit source_account
  Both lines use abs(amount). Uniform across Asset and Liability sources because
  the Parse phase signs amounts from the cardholder's perspective.

Paystub transactions:
  One multi-line entry per paystub document (all txns for that doc grouped together).
  earning   (amount > 0)  →  Credit suggested_account_code
  deduction (amount < 0)  →  Debit  suggested_account_code  (abs value)
  Balancing line: Debit doc.source_account_code with net_pay = sum(amounts).
  Raises JournalError if source_account_code is None or net_pay <= 0.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.raw_transaction import RawTransaction

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


class JournalError(Exception):
    """Raised for invalid or unpostable journal operations."""


_VALID_MANUAL_SOURCE_TYPES = frozenset({"manual", "adjusting", "closing"})


async def create_manual_entry(
    db: AsyncSession,
    period_id: uuid.UUID,
    entry_date: date,
    description: str,
    source_type: str,
    lines: list[tuple[int, Decimal, Decimal, str | None]],
) -> JournalEntry:
    """Create a balanced journal entry directly (no RawTransaction workflow).

    Each line is (account_code, debit_amount, credit_amount, memo).
    Raises JournalError if the entry is empty or does not balance.
    """
    if source_type not in _VALID_MANUAL_SOURCE_TYPES:
        raise JournalError(f"Invalid source_type: {source_type!r}")
    if not lines:
        raise JournalError("Entry must have at least one line")

    total_debits = sum(d for _, d, _, _ in lines)
    total_credits = sum(c for _, _, c, _ in lines)
    if total_debits != total_credits:
        raise JournalError(
            f"Entry does not balance: debits={total_debits} credits={total_credits}"
        )

    eid = uuid.uuid4()
    entry = JournalEntry(
        entry_id=eid,
        period_id=period_id,
        entry_date=entry_date,
        description=description,
        source_type=source_type,
        is_adjusting=(source_type == "adjusting"),
        is_closing=(source_type == "closing"),
        created_by="user",
    )
    db.add(entry)
    for account_code, debit, credit, memo in lines:
        db.add(JournalLine(
            entry_id=eid,
            account_code=account_code,
            debit_amount=debit,
            credit_amount=credit,
            memo=memo,
        ))
    await db.commit()
    await db.refresh(entry)
    logger.info("Created manual journal entry %s for period %s", eid, period_id)
    return entry


async def delete_manual_entry(
    db: AsyncSession,
    entry_id: uuid.UUID,
    period_id: uuid.UUID,
) -> None:
    """Delete a user-created journal entry and its lines.

    Only entries with created_by='user' belonging to the given period may be deleted.
    """
    entry = await db.get(JournalEntry, entry_id)
    if entry is None or entry.period_id != period_id:
        raise JournalError("Journal entry not found")
    if entry.created_by != "user":
        raise JournalError("Only manually-created entries can be deleted")

    lines_result = await db.scalars(
        select(JournalLine).where(JournalLine.entry_id == entry_id)
    )
    for line in lines_result.all():
        await db.delete(line)
    await db.delete(entry)
    await db.commit()
    logger.info("Deleted manual journal entry %s", entry_id)


async def delete_entry(
    db: AsyncSession,
    entry_id: uuid.UUID,
    period_id: uuid.UUID,
) -> None:
    """Delete any journal entry and its lines.

    For system-created entries (paystub/statement), also reverts the associated
    RawTransactions back to 'approved' so they can be corrected and re-posted.
    """
    from app.models.raw_transaction import RawTransaction  # local to avoid circular

    entry = await db.get(JournalEntry, entry_id)
    if entry is None or entry.period_id != period_id:
        raise JournalError("Journal entry not found")

    if entry.created_by == "python":
        txns_result = await db.scalars(
            select(RawTransaction).where(
                RawTransaction.journal_entry_id == entry_id,
                RawTransaction.period_id == period_id,
            )
        )
        for txn in txns_result.all():
            txn.status = "approved"
            txn.journal_entry_id = None

    await db.execute(delete(JournalLine).where(JournalLine.entry_id == entry_id))
    await db.delete(entry)
    await db.commit()
    logger.info("Deleted journal entry %s (created_by=%s)", entry_id, entry.created_by)


async def post_period(db: AsyncSession, period_id: uuid.UUID) -> int:
    """Post all approved transactions for the period as journal entries.

    Returns the number of JournalEntry records created. Skips entries that
    fail validation (missing accounts, unbalanced paystub) and logs a warning.
    """
    txns_result = await db.scalars(
        select(RawTransaction)
        .where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "approved",
        )
        .order_by(RawTransaction.document_id, RawTransaction.txn_date)
    )
    approved: Sequence[RawTransaction] = txns_result.all()
    if not approved:
        return 0

    doc_ids = {t.document_id for t in approved}
    docs_result = await db.scalars(
        select(Document).where(Document.document_id.in_(doc_ids))
    )
    docs_by_id: dict[uuid.UUID, Document] = {d.document_id: d for d in docs_result.all()}

    # Collect all account codes we'll need and load them in one query
    needed_codes: set[int] = set()
    for txn in approved:
        if txn.suggested_account_code:
            needed_codes.add(txn.suggested_account_code)
    for doc in docs_by_id.values():
        if doc.source_account_code:
            needed_codes.add(doc.source_account_code)

    accounts_result = await db.scalars(
        select(Account).where(Account.account_code.in_(needed_codes))
    )
    accounts_by_code: dict[int, Account] = {a.account_code: a for a in accounts_result.all()}

    # Paystubs and mortgage statements group all txns from one document into a
    # single balanced entry; other statement txns post individually.
    paystub_groups: dict[uuid.UUID, list[RawTransaction]] = {}
    mortgage_groups: dict[uuid.UUID, list[RawTransaction]] = {}
    statement_txns: list[RawTransaction] = []

    for txn in approved:
        doc = docs_by_id.get(txn.document_id)
        if doc is None:
            logger.warning("Transaction %s has no document — skipping", txn.raw_txn_id)
            continue
        if doc.document_type == "paystub":
            paystub_groups.setdefault(doc.document_id, []).append(txn)
        elif doc.document_type == "mortgage_statement":
            mortgage_groups.setdefault(doc.document_id, []).append(txn)
        else:
            statement_txns.append(txn)

    entries_created = 0

    for txn in statement_txns:
        doc = docs_by_id[txn.document_id]
        try:
            entry, lines = _build_statement_entry(txn, doc, accounts_by_code)
        except JournalError as exc:
            logger.warning("Skipping statement txn %s: %s", txn.raw_txn_id, exc)
            continue
        db.add(entry)
        for line in lines:
            db.add(line)
        txn.status = "posted"
        txn.journal_entry_id = entry.entry_id
        entries_created += 1

    for doc_id, group in paystub_groups.items():
        doc = docs_by_id[doc_id]
        try:
            period_entries = _build_paystub_entries(doc, group, accounts_by_code)
        except JournalError as exc:
            logger.warning("Skipping paystub doc %s: %s", doc_id, exc)
            continue
        for entry, lines, txn_group in period_entries:
            db.add(entry)
            for line in lines:
                db.add(line)
            for txn in txn_group:
                txn.status = "posted"
                txn.journal_entry_id = entry.entry_id
            entries_created += 1

    for doc_id, group in mortgage_groups.items():
        doc = docs_by_id[doc_id]
        try:
            entry, lines = _build_mortgage_entry(doc, group, accounts_by_code)
        except JournalError as exc:
            logger.warning("Skipping mortgage doc %s: %s", doc_id, exc)
            continue
        db.add(entry)
        for line in lines:
            db.add(line)
        for txn in group:
            txn.status = "posted"
            txn.journal_entry_id = entry.entry_id
        entries_created += 1

    await db.commit()
    logger.info("Posted %d journal entries for period %s", entries_created, period_id)
    return entries_created


def _build_statement_entry(
    txn: RawTransaction,
    doc: Document,
    accounts_by_code: dict[int, Account],
) -> tuple[JournalEntry, list[JournalLine]]:
    if doc.source_account_code is None:
        raise JournalError(f"Document {doc.document_id} has no source_account_code")
    if txn.suggested_account_code is None:
        raise JournalError(f"Transaction {txn.raw_txn_id} has no suggested_account_code")
    if doc.source_account_code not in accounts_by_code:
        raise JournalError(f"Source account {doc.source_account_code} not found")
    if txn.suggested_account_code not in accounts_by_code:
        raise JournalError(f"Category account {txn.suggested_account_code} not found")

    eid = uuid.uuid4()
    entry = JournalEntry(
        entry_id=eid,
        period_id=txn.period_id,
        entry_date=txn.txn_date,
        description=txn.description,
        source_type="statement",
        source_document_id=doc.document_id,
        created_by="python",
    )
    amount = abs(txn.amount)
    if txn.amount >= _ZERO:
        debit_code, credit_code = doc.source_account_code, txn.suggested_account_code
    else:
        debit_code, credit_code = txn.suggested_account_code, doc.source_account_code

    lines = [
        JournalLine(entry_id=eid, account_code=debit_code, debit_amount=amount, credit_amount=_ZERO),
        JournalLine(entry_id=eid, account_code=credit_code, debit_amount=_ZERO, credit_amount=amount),
    ]
    return entry, lines


def _build_mortgage_entry(
    doc: Document,
    txns: list[RawTransaction],
    accounts_by_code: dict[int, Account],
) -> tuple[JournalEntry, list[JournalLine]]:
    """Build one balanced entry per mortgage statement.

    Each component transaction (principal, interest, escrow, taxes, insurance)
    becomes a debit line against its suggested_account_code; the total is
    credited to the document's source_account_code (checking).
    """
    if doc.source_account_code is None:
        raise JournalError(f"Mortgage document {doc.document_id} has no source_account_code")
    if doc.source_account_code not in accounts_by_code:
        raise JournalError(f"Source account {doc.source_account_code} not found")
    for txn in txns:
        if txn.suggested_account_code is None:
            raise JournalError(
                f"Mortgage transaction {txn.raw_txn_id} ({txn.description!r}) "
                "has no suggested_account_code"
            )
        if txn.suggested_account_code not in accounts_by_code:
            raise JournalError(f"Account {txn.suggested_account_code} not found")

    eid = uuid.uuid4()
    entry = JournalEntry(
        entry_id=eid,
        period_id=txns[0].period_id,
        entry_date=txns[0].txn_date,
        description=f"Mortgage Payment — {doc.file_name}",
        source_type="statement",
        source_document_id=doc.document_id,
        created_by="python",
    )

    lines: list[JournalLine] = []
    total = _ZERO
    for txn in txns:
        amount = abs(txn.amount)
        lines.append(JournalLine(
            entry_id=eid,
            account_code=txn.suggested_account_code,
            debit_amount=amount,
            credit_amount=_ZERO,
            memo=txn.description,
        ))
        total += amount

    if total <= _ZERO:
        raise JournalError(
            f"Mortgage document {doc.document_id} has no positive payment components"
        )

    lines.append(JournalLine(
        entry_id=eid,
        account_code=doc.source_account_code,
        debit_amount=_ZERO,
        credit_amount=total,
    ))

    return entry, lines


async def unpost_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    period_id: uuid.UUID,
) -> int:
    """Reverse posting for all transactions from a specific document.

    Deletes the JournalEntry and JournalLine records that were created during
    posting and resets those RawTransactions back to 'approved' so they can be
    corrected and re-posted. Returns the number of transactions reverted.
    """
    txns_result = await db.scalars(
        select(RawTransaction).where(
            RawTransaction.document_id == document_id,
            RawTransaction.period_id == period_id,
            RawTransaction.status == "posted",
        )
    )
    txns: Sequence[RawTransaction] = txns_result.all()
    if not txns:
        return 0

    entry_ids = {t.journal_entry_id for t in txns if t.journal_entry_id}

    await db.execute(delete(JournalLine).where(JournalLine.entry_id.in_(entry_ids)))
    await db.execute(delete(JournalEntry).where(JournalEntry.entry_id.in_(entry_ids)))

    for txn in txns:
        txn.status = "approved"
        txn.journal_entry_id = None

    await db.commit()
    logger.info(
        "Unposted %d transactions for document %s (deleted %d entries)",
        len(txns),
        document_id,
        len(entry_ids),
    )
    return len(txns)


def _build_paystub_entries(
    doc: Document,
    txns: list[RawTransaction],
    accounts_by_code: dict[int, Account],
) -> list[tuple[JournalEntry, list[JournalLine], list[RawTransaction]]]:
    """Build one balanced journal entry per pay date found in the document.

    Paystubs can contain multiple pay periods (e.g. two pay dates in one PDF).
    Each pay date becomes its own entry so the ledger shows discrete paychecks.
    """
    # Determine the deposit (source) account once for the whole document.
    # Prefer the document's own field; fall back to whichever transaction has
    # the LARGEST positive amount mapped to an Asset account — that is the net
    # pay deposit, not a small employer contribution like CO STK CONT.
    source_code: int | None = doc.source_account_code
    if source_code is None:
        best_amount = _ZERO
        for txn in txns:
            if txn.suggested_account_code and txn.amount > best_amount:
                acct = accounts_by_code.get(txn.suggested_account_code)
                if acct and acct.account_type == "Asset":
                    best_amount = txn.amount
                    source_code = txn.suggested_account_code
    if source_code is None:
        raise JournalError(
            f"Paystub document {doc.document_id} has no deposit account — "
            "assign the checking account to the net pay line before posting"
        )

    # Group transactions by pay date; preserve document order within each date.
    date_groups: dict = {}
    for txn in txns:
        date_groups.setdefault(txn.txn_date, []).append(txn)

    results: list[tuple[JournalEntry, list[JournalLine], list[RawTransaction]]] = []
    for pay_date in sorted(date_groups):
        group = date_groups[pay_date]
        entry, lines = _build_single_paystub_entry(doc, pay_date, group, source_code, accounts_by_code)
        results.append((entry, lines, group))
    return results


def _build_single_paystub_entry(
    doc: Document,
    pay_date,
    txns: list[RawTransaction],
    source_code: int,
    accounts_by_code: dict[int, Account],
) -> tuple[JournalEntry, list[JournalLine]]:
    eid = uuid.uuid4()
    entry = JournalEntry(
        entry_id=eid,
        period_id=txns[0].period_id,
        entry_date=pay_date,
        description=f"Paystub — {doc.file_name}",
        source_type="paystub",
        source_document_id=doc.document_id,
        created_by="python",
    )

    lines: list[JournalLine] = []
    explicit_net_pay = _ZERO

    for txn in txns:
        if txn.suggested_account_code is None:
            raise JournalError(
                f"Paystub transaction {txn.raw_txn_id} ({txn.description!r}) "
                "has no suggested_account_code"
            )
        if txn.suggested_account_code not in accounts_by_code:
            raise JournalError(f"Account {txn.suggested_account_code} not found")

        # The net pay transaction maps to the deposit account — accumulate it
        # as the balancing debit rather than running it through P&L logic.
        if txn.suggested_account_code == source_code:
            explicit_net_pay += txn.amount
            continue

        amount = abs(txn.amount)
        if txn.amount >= _ZERO:
            lines.append(JournalLine(
                entry_id=eid,
                account_code=txn.suggested_account_code,
                debit_amount=_ZERO,
                credit_amount=amount,
                memo=txn.description,
            ))
        else:
            lines.append(JournalLine(
                entry_id=eid,
                account_code=txn.suggested_account_code,
                debit_amount=amount,
                credit_amount=_ZERO,
                memo=txn.description,
            ))

    # Use the explicit net pay amount if present; otherwise compute from P&L lines.
    net_pay = explicit_net_pay if explicit_net_pay > _ZERO else sum(
        t.amount for t in txns if t.suggested_account_code != source_code
    )
    if net_pay <= _ZERO:
        raise JournalError(
            f"Paystub net pay computed as {net_pay} — check for missing earning lines"
        )
    lines.append(JournalLine(
        entry_id=eid,
        account_code=source_code,
        debit_amount=net_pay,
        credit_amount=_ZERO,
    ))

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    if total_debits != total_credits:
        raise JournalError(
            f"Paystub entry does not balance: debits={total_debits} credits={total_credits}"
        )

    return entry, lines
