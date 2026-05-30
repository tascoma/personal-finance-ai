import logging
import uuid
from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._base import AgentError
from app.dependencies import get_current_user, get_db_session
from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.raw_transaction import RawTransaction
from app.schemas.account import AccountRead
from app.schemas.api_responses import (
    CountResult,
    JournalEntryWithLines,
    JournalPageResponse,
    ManualJournalEntryCreate,
    OperationResult,
)
from app.schemas.document import DocumentRead
from app.schemas.journal import JournalEntryRead, JournalLineRead
from app.schemas.period import PeriodRead
from app.schemas.raw_transaction import RawTransactionRead
from app.services import classify as classify_service
from app.services import journal as journal_service
from app.services import period as period_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["journal"], dependencies=[Depends(get_current_user)])


def _build_entry_with_lines(
    entry: JournalEntry,
    lines_by_entry: dict,
) -> JournalEntryWithLines:
    entry_lines = [JournalLineRead.model_validate(ln) for ln in lines_by_entry.get(entry.entry_id, [])]
    base = JournalEntryRead.model_validate(entry).model_dump()
    return JournalEntryWithLines(**base, lines=entry_lines)


@router.get("/periods/{period_id}/journal", response_model=JournalPageResponse)
async def get_journal_page(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> JournalPageResponse:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    accounts_result = await db.scalars(
        select(Account).where(Account.is_active.is_(True)).order_by(Account.account_code)
    )
    accounts = list(accounts_result.all())

    staged_result = await db.scalars(
        select(RawTransaction)
        .where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "staged",
            RawTransaction.is_duplicate.is_(False),
        )
        .order_by(RawTransaction.txn_date, RawTransaction.created_at)
    )
    approved_result = await db.scalars(
        select(RawTransaction)
        .where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "approved",
            RawTransaction.is_duplicate.is_(False),
        )
        .order_by(RawTransaction.txn_date, RawTransaction.created_at)
    )
    entries_result = await db.scalars(
        select(JournalEntry)
        .where(JournalEntry.period_id == period_id)
        .order_by(JournalEntry.entry_date, JournalEntry.created_at)
    )
    lines_result = await db.scalars(
        select(JournalLine).join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(JournalEntry.period_id == period_id)
    )

    lines_by_entry: dict = defaultdict(list)
    for line in lines_result.all():
        lines_by_entry[line.entry_id].append(line)

    staged = list(staged_result.all())
    has_unclassified = any(
        t.classifier_confidence == Decimal("0") and not t.is_duplicate for t in staged
    )

    all_docs_result = await db.scalars(
        select(Document)
        .where(Document.period_id == period_id)
        .order_by(Document.created_at)
    )
    all_docs = list(all_docs_result.all())
    docs_missing_source = [
        d for d in all_docs
        if d.source_account_code is None and d.parse_status == "complete"
    ]

    return JournalPageResponse(
        period=PeriodRead.model_validate(period),
        accounts=[AccountRead.model_validate(a) for a in accounts],
        staged=[RawTransactionRead.model_validate(t) for t in staged],
        approved=[RawTransactionRead.model_validate(t) for t in approved_result.all()],
        entries=[_build_entry_with_lines(e, lines_by_entry) for e in entries_result.all()],
        has_unclassified=has_unclassified,
        documents=[DocumentRead.model_validate(d) for d in all_docs],
        docs_missing_source=[DocumentRead.model_validate(d) for d in docs_missing_source],
        next_status=period_service.next_status(period.status),
        prev_status=period_service.prev_status(period.status),
    )


@router.post("/periods/{period_id}/classify", response_model=CountResult)
async def classify_transactions(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    try:
        count = await classify_service.classify_period(db, period_id)
    except AgentError as exc:
        raise HTTPException(status_code=502, detail="Classification failed") from exc
    logger.info("Classified %d transactions for period %s", count, period_id)
    return CountResult(count=count)


@router.post("/periods/{period_id}/post", response_model=CountResult)
async def post_transactions(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    if period.status != "pending_close":
        raise HTTPException(status_code=400, detail="Posting is only allowed in the journal phase (pending_close)")
    try:
        count = await journal_service.post_period(db, period_id)
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Posted %d transactions for period %s", count, period_id)
    return CountResult(count=count)


@router.post("/periods/{period_id}/journal/entries", response_model=JournalEntryWithLines, status_code=status.HTTP_201_CREATED)
async def create_manual_journal_entry(
    period_id: uuid.UUID,
    body: ManualJournalEntryCreate,
    db: AsyncSession = Depends(get_db_session),
) -> JournalEntryWithLines:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    if period.status == "closed":
        raise HTTPException(status_code=400, detail="Period is closed")

    try:
        entry_date = date_type.fromisoformat(body.entry_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date") from exc

    try:
        lines: list[tuple[int, Decimal, Decimal, str | None]] = [
            (ln.account_code, Decimal(ln.debit), Decimal(ln.credit), ln.memo)
            for ln in body.lines
        ]
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail=f"Invalid amount: {exc}") from exc

    try:
        entry = await journal_service.create_manual_entry(
            db, period_id, entry_date, body.description, body.source_type, lines
        )
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lines_result = await db.scalars(select(JournalLine).where(JournalLine.entry_id == entry.entry_id))
    lines_by_entry: dict = {entry.entry_id: list(lines_result.all())}
    logger.info("Created manual journal entry %s for period %s", entry.entry_id, period_id)
    return _build_entry_with_lines(entry, lines_by_entry)


@router.delete("/periods/{period_id}/journal/entries/{entry_id}", response_model=OperationResult)
async def delete_journal_entry(
    period_id: uuid.UUID,
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> OperationResult:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    if period.status == "closed":
        raise HTTPException(status_code=400, detail="Cannot delete entries from a closed period")
    try:
        await journal_service.delete_entry(db, entry_id, period_id)
    except journal_service.JournalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Deleted journal entry %s from period %s", entry_id, period_id)
    return OperationResult(ok=True)
