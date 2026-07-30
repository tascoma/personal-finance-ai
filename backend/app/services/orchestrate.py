"""Orchestration service — plan-then-execute parse for a batch of documents.

The flow:
  1. Load every `parse_status="pending"` document for the period, and the
     user's active chart of accounts.
  2. Build a short digest per document (filename, extension, small content
     peek) — never the full file.
  3. Call `run_orchestrator` once with the digests and account list to get an
     `OrchestrationPlan` covering the batch.
  4. For each step in the plan, persist any `document_type` correction and any
     matched `source_account_code`, then call `parse_service.parse_document`.
     If the orchestrator could not match a source account, the document is left
     as `pending` and the step is reported with `status="needs_review"` instead
     of being parsed.
  5. If any successfully parsed step requested it, run
     `classify_service.classify_period` once for the period at the end.

Per-step failures are caught so a single bad file doesn't abort the rest.

`orchestrate_parse_stream` is the canonical implementation — an async generator
that yields SSE-compatible progress dicts throughout execution.
`orchestrate_parse` is a thin wrapper that collects the final result.
"""

import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import (
    AccountChoice,
    DocumentDigest,
    OrchestrationPlan,
    run_orchestrator,
)
from app.core.config import settings
from app.models.account import Account
from app.models.document import Document
from app.schemas.orchestrate import OrchestrationResult
from app.services import classify as classify_service
from app.services import parse as parse_service
from app.services.file_readers import (
    ParseError,
    extract_csv_rows,
    extract_pdf_text,
    extract_xlsx_rows,
)
from app.services.scrub import scrub_description, scrub_text

logger = logging.getLogger(__name__)

PDF_PEEK_CHARS = 2500
TABULAR_PEEK_ROWS = 15


def _build_digest(document: Document, keep_terms: Sequence[str] = ()) -> DocumentDigest:
    """Read a small content peek from disk for the orchestrator's routing decision.

    The peek is the highest-PII payload in the pipeline — the top of a statement
    is exactly where the account holder's name, mailing address, and full account
    number sit — so it is redacted before it leaves. `keep_terms` protects the
    institution and product names the orchestrator matches on.
    """
    path = Path(document.file_path)
    extension = path.suffix.lower()
    peek = ""
    read_failed = False
    try:
        if extension == ".pdf":
            text = extract_pdf_text(path)
            peek = text[:PDF_PEEK_CHARS]
        elif extension == ".csv":
            rows = extract_csv_rows(path)
            peek = "\n".join(", ".join(f"{k}={v}" for k, v in r.items()) for r in rows[:TABULAR_PEEK_ROWS])
        elif extension == ".xlsx":
            rows_x = extract_xlsx_rows(path)
            peek = "\n".join(" | ".join(str(c) if c is not None else "" for c in r) for r in rows_x[:TABULAR_PEEK_ROWS])
        else:
            peek = f"(unsupported extension: {extension})"
            read_failed = True
    except ParseError as exc:
        logger.warning(
            "ParseError reading digest peek for document %s (%s): %s",
            document.document_id,
            document.file_name,
            exc,
        )
        peek = f"(could not read file: {exc})"
        read_failed = True
    except Exception as exc:
        logger.exception(
            "Unexpected error reading digest peek for document %s (%s)",
            document.document_id,
            document.file_name,
        )
        peek = f"(error reading file: {exc})"
        read_failed = True

    if not read_failed and not peek.strip():
        logger.warning(
            "Digest peek for document %s (%s) is empty — orchestrator will only see the filename",
            document.document_id,
            document.file_name,
        )
    elif not read_failed:
        logger.info(
            "Built digest for document %s (%s): %d chars of content peek",
            document.document_id,
            document.file_name,
            len(peek),
        )

    file_name = document.file_name
    if settings.scrub_before_llm and not read_failed:
        # Scrub after the peek is already sliced so the regex work stays bounded
        # by PDF_PEEK_CHARS rather than running over the whole document.
        peek, report = scrub_text(peek, keep_terms=keep_terms)
        # A filename like "Tony Scoma Statement.pdf" leaks through the digest too,
        # while "Credit Card - 6120_04-01-2026.csv" keeps its useful last-4.
        file_name = scrub_description(file_name, keep_terms=keep_terms)
        logger.info(
            "Scrubbed digest peek for document %s: %s",
            document.document_id,
            report.summary(),
        )

    return DocumentDigest(
        document_id=document.document_id,
        file_name=file_name,
        file_extension=extension,
        content_peek=peek,
    )


async def _load_account_choices(db: AsyncSession) -> tuple[list[AccountChoice], dict[int, Account]]:
    result = await db.scalars(
        select(Account).where(Account.is_active.is_(True)).order_by(Account.account_code)
    )
    accounts = result.all()
    by_code = {a.account_code: a for a in accounts}
    choices = [
        AccountChoice(
            account_code=a.account_code,
            account_name=a.account_name,
            account_type=a.account_type,
            sub_category=a.sub_category,
        )
        for a in accounts
    ]
    return choices, by_code


async def orchestrate_parse_stream(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> AsyncGenerator[dict, None]:
    """Async generator that runs orchestration and yields SSE-compatible progress dicts.

    Events emitted (in order):
      {"event": "planning"}
      {"event": "planned", "doc_count": N}
      {"event": "parsing",  "file_name": str, "index": int, "total": int}  — once per doc
      {"event": "parsed",   "file_name": str, "index": int, "total": int,
                             "status": "complete"|"failed"|"needs_review",
                             "txn_count": int}   — txn_count only on complete
      {"event": "classifying"}   — only if classifier runs
      {"event": "complete", "parsed": int, "failed": int, "needs_review": int,
                             "classifier_ran": bool, "classifier_updated": int}
      {"event": "error",    "message": str}   — emitted before re-raising on fatal errors
    """
    docs_result = await db.scalars(
        select(Document).where(
            Document.period_id == period_id,
            Document.parse_status == "pending",
        )
    )
    pending: Sequence[Document] = docs_result.all()
    if not pending:
        yield {
            "event": "complete",
            "parsed": 0,
            "failed": 0,
            "needs_review": 0,
            "classifier_ran": False,
            "classifier_updated": 0,
        }
        return

    docs_by_id: dict[uuid.UUID, Document] = {d.document_id: d for d in pending}
    # Accounts load first: their names are the scrubber's keep_terms, so an
    # institution or product name is never redacted out of a digest peek.
    account_choices, accounts_by_code = await _load_account_choices(db)
    keep_terms = [c.account_name for c in account_choices]
    digests = [_build_digest(d, keep_terms) for d in pending]

    logger.info(
        "Calling orchestrator for period %s with %d pending docs and %d active accounts",
        period_id,
        len(pending),
        len(account_choices),
    )
    if not account_choices:
        logger.warning(
            "No active accounts found — orchestrator cannot resolve any source_account_code for period %s",
            period_id,
        )

    yield {"event": "planning"}

    try:
        plan: OrchestrationPlan = await run_orchestrator(digests, account_choices)
    except Exception:
        logger.exception("Orchestrator agent failed for period %s", period_id)
        yield {"event": "error", "message": "Orchestration agent failed"}
        raise

    logger.info(
        "Orchestrator planned %d steps for period %s (from %d pending docs)",
        len(plan.steps),
        period_id,
        len(pending),
    )
    for step in plan.steps:
        logger.info(
            "Plan for document %s: resolved_type=%s, resolved_source_account_code=%s, "
            "run_classifier=%s, type_reason=%r, source_account_reason=%r",
            step.document_id,
            step.resolved_type,
            step.resolved_source_account_code,
            step.run_classifier,
            step.type_reason,
            step.source_account_reason,
        )

    yield {"event": "planned", "doc_count": len(plan.steps)}

    any_classifier_requested = False
    parsed = 0
    failed = 0
    needs_review = 0

    planned_ids = {step.document_id for step in plan.steps}
    missing = [d for d in pending if d.document_id not in planned_ids]
    for d in missing:
        logger.warning("Orchestrator skipped document %s — recording as failed", d.document_id)
        yield {"event": "parsed", "file_name": d.file_name, "status": "failed"}
        failed += 1

    total_planned = len(plan.steps)
    for i, step in enumerate(plan.steps):
        doc = docs_by_id.get(step.document_id)
        if doc is None:
            logger.warning(
                "Orchestrator returned unknown document_id %s — skipping", step.document_id
            )
            continue

        doc_id = doc.document_id
        file_name = doc.file_name

        yield {
            "event": "parsing",
            "file_name": file_name,
            "index": i + 1,
            "total": total_planned,
        }

        if step.resolved_type != doc.document_type:
            logger.info(
                "Orchestrator reclassified document %s: %s → %s (reason: %s)",
                doc.document_id,
                doc.document_type,
                step.resolved_type,
                step.type_reason,
            )
            doc.document_type = step.resolved_type

        resolved_account_name: str | None = None
        resolved_code: int | None = step.resolved_source_account_code
        if resolved_code is not None:
            account = accounts_by_code.get(resolved_code)
            if account is None:
                logger.warning(
                    "Orchestrator returned unknown account_code %s for document %s — treating as unresolved",
                    resolved_code,
                    doc.document_id,
                )
                resolved_code = None
            else:
                resolved_account_name = account.account_name
                if doc.source_account_code != account.account_code:
                    logger.info(
                        "Orchestrator set source_account_code=%s on document %s (reason: %s)",
                        account.account_code,
                        doc.document_id,
                        step.source_account_reason,
                    )
                    doc.source_account_code = account.account_code

        await db.commit()

        if resolved_code is None and step.resolved_type != "opening_balances":
            needs_review += 1
            logger.warning(
                "Document %s (%s) needs review: orchestrator could not resolve a source account "
                "(resolved_type=%s, source_account_reason=%r)",
                doc.document_id,
                doc.file_name,
                step.resolved_type,
                step.source_account_reason,
            )
            yield {
                "event": "parsed",
                "file_name": file_name,
                "index": i + 1,
                "total": total_planned,
                "status": "needs_review",
            }
            continue

        if step.run_classifier:
            any_classifier_requested = True

        try:
            txn_count = await parse_service.parse_document(db, doc_id)
            parsed += 1
            yield {
                "event": "parsed",
                "file_name": file_name,
                "index": i + 1,
                "total": total_planned,
                "status": "complete",
                "txn_count": txn_count,
            }
        except ParseError as exc:
            logger.warning(
                "ParseError parsing document %s (%s) as %s: %s",
                doc_id,
                file_name,
                step.resolved_type,
                exc,
            )
            failed += 1
            yield {
                "event": "parsed",
                "file_name": file_name,
                "index": i + 1,
                "total": total_planned,
                "status": "failed",
            }
        except Exception as exc:
            logger.exception(
                "Unexpected error parsing document %s (%s) as %s",
                doc_id,
                file_name,
                step.resolved_type,
            )
            try:
                await db.rollback()
            except Exception:
                logger.exception("Failed to roll back session after parse error for document %s", doc_id)
            failed += 1
            yield {
                "event": "parsed",
                "file_name": file_name,
                "index": i + 1,
                "total": total_planned,
                "status": "failed",
            }

    classifier_updated = 0
    if any_classifier_requested and parsed > 0:
        yield {"event": "classifying"}
        try:
            classifier_updated = await classify_service.classify_period(db, period_id)
            logger.info(
                "Classifier updated %d transactions for period %s after orchestration",
                classifier_updated,
                period_id,
            )
        except Exception:
            logger.exception(
                "Classifier failed after orchestration for period %s — continuing", period_id
            )

    yield {
        "event": "complete",
        "parsed": parsed,
        "failed": failed,
        "needs_review": needs_review,
        "classifier_ran": any_classifier_requested and parsed > 0,
        "classifier_updated": classifier_updated,
    }


async def orchestrate_parse(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> OrchestrationResult:
    """Non-streaming wrapper around orchestrate_parse_stream.

    Runs the generator to completion and returns the final OrchestrationResult.
    Any exception raised inside the generator propagates to the caller.
    """
    complete_event: dict = {}
    async for event in orchestrate_parse_stream(db, period_id):
        if event["event"] == "complete":
            complete_event = event
    return OrchestrationResult(
        period_id=period_id,
        parsed=complete_event.get("parsed", 0),
        failed=complete_event.get("failed", 0),
        needs_review=complete_event.get("needs_review", 0),
        classifier_ran=complete_event.get("classifier_ran", False),
        classifier_updated=complete_event.get("classifier_updated", 0),
    )
