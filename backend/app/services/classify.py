import logging
import uuid
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.classifier import ClassifierOutput, TxnInput, run_classifier
from app.core.config import settings
from app.models.account import Account
from app.models.document import Document
from app.models.raw_transaction import RawTransaction
from app.services.scrub import scrub_description

logger = logging.getLogger(__name__)

CONFIDENCE_FLAG_THRESHOLD = Decimal("0.7")


async def classify_period(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> int:
    """Assign suggested account codes to unclassified statement transactions.

    Skips paystub-derived rows (already classified in Parse phase), rows with
    classifier_confidence > 0, and duplicates. Idempotent. Returns count updated.
    """
    txns_result = await db.scalars(
        select(RawTransaction).where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "staged",
            RawTransaction.classifier_confidence == Decimal("0"),
            RawTransaction.is_duplicate.is_(False),
        )
    )
    candidates: Sequence[RawTransaction] = txns_result.all()
    if not candidates:
        return 0

    doc_ids = {t.document_id for t in candidates}
    docs_result = await db.scalars(
        select(Document).where(Document.document_id.in_(doc_ids))
    )
    docs_by_id: dict[uuid.UUID, Document] = {d.document_id: d for d in docs_result.all()}

    accounts_result = await db.scalars(
        select(Account).where(Account.is_active.is_(True)).order_by(Account.account_code)
    )
    all_accounts: Sequence[Account] = accounts_result.all()
    accounts_by_code: dict[int, Account] = {a.account_code: a for a in all_accounts}

    txn_inputs: list[TxnInput] = []
    eligible: list[RawTransaction] = []
    for txn in candidates:
        doc = docs_by_id.get(txn.document_id)
        if doc is None or doc.document_type == "paystub":
            continue
        source = accounts_by_code.get(doc.source_account_code) if doc.source_account_code else None
        txn_inputs.append(
            TxnInput(
                id=txn.raw_txn_id.hex[:8],
                description=txn.description,
                amount=txn.amount,
                source_account_name=source.account_name if source else "Unknown",
                source_account_type=source.account_type if source else "Asset",
            )
        )
        eligible.append(txn)

    if not eligible:
        return 0

    coa_table = _build_coa_table(all_accounts)
    keep_terms = [a.account_name for a in all_accounts if a.account_name]
    eligible_by_short_id: dict[str, RawTransaction] = {
        t.raw_txn_id.hex[:8]: t for t in eligible
    }
    valid_codes: set[int] = {a.account_code for a in all_accounts}

    all_suggestions: list = []
    batch_size = 25
    total_batches = (len(txn_inputs) + batch_size - 1) // batch_size
    for batch_num, batch_start in enumerate(range(0, len(txn_inputs), batch_size), start=1):
        batch = txn_inputs[batch_start : batch_start + batch_size]
        logger.info(
            "Classifying batch %d/%d (%d txns) for period %s",
            batch_num,
            total_batches,
            len(batch),
            period_id,
        )
        # txn descriptions are untrusted (lifted verbatim from uploaded statements),
        # so they can carry prompt-injection text. The blast radius is bounded: the
        # agent returns a structured ClassifierOutput and any account_code it picks is
        # validated against valid_codes below — an out-of-range code is flagged, not posted.
        # `_format_txn_inputs` also redacts identifiers out of each description; the
        # round trip is keyed on `id`, never on the description text.
        user_prompt = (
            f"Chart of accounts:\n{coa_table}\n\n"
            f"Transactions to classify:\n{_format_txn_inputs(batch, keep_terms)}"
        )
        try:
            output = await run_classifier(user_prompt)
        except Exception:
            logger.error(
                "Classifier agent call failed for period %s (batch %d/%d)",
                period_id,
                batch_num,
                total_batches,
                exc_info=True,
            )
            raise
        logger.info(
            "Batch %d/%d returned %d suggestions",
            batch_num,
            total_batches,
            len(output.suggestions),
        )
        all_suggestions.extend(output.suggestions)

    updated = 0
    for suggestion in all_suggestions:
        txn = eligible_by_short_id.get(suggestion.id)
        if txn is None:
            logger.warning("Classifier returned unknown id %r — skipping", suggestion.id)
            continue
        if suggestion.account_code not in valid_codes:
            logger.warning(
                "Classifier returned unknown account_code %d for txn %s — flagging",
                suggestion.account_code,
                txn.raw_txn_id,
            )
            txn.is_flagged = True
            continue
        confidence = Decimal(str(suggestion.confidence))
        txn.suggested_account_code = suggestion.account_code
        txn.classifier_confidence = confidence
        txn.is_flagged = confidence < CONFIDENCE_FLAG_THRESHOLD
        updated += 1

    await db.commit()
    logger.info("Classified %d transactions in period %s", updated, period_id)
    return updated


def _build_coa_table(accounts: Sequence[Account]) -> str:
    lines = ["code | name | type | sub_category"]
    for a in accounts:
        if not a.is_memo and a.is_active:
            lines.append(f"{a.account_code} | {a.account_name} | {a.account_type} | {a.sub_category}")
    return "\n".join(lines)


def _format_txn_inputs(inputs: list[TxnInput], keep_terms: Sequence[str] = ()) -> str:
    """Render the batch as a pipe table, redacting each description on the way out.

    Only the prompt is redacted — `raw_transactions.description` keeps the
    verbatim statement text, so dedup hashes and the audit trail are unaffected.
    `source_account_name` comes from the chart of accounts and is never scrubbed.
    """
    lines = ["id | description | amount | source_account | source_type"]
    for t in inputs:
        description = (
            scrub_description(t.description, keep_terms=keep_terms)
            if settings.scrub_before_llm
            else t.description
        )
        lines.append(
            f"{t.id} | {description} | {t.amount} | {t.source_account_name} | {t.source_account_type}"
        )
    return "\n".join(lines)
