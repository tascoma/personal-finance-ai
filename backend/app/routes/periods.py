import json
import logging
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.models.account import Account
from app.models.raw_transaction import RawTransaction
from app.models.user import User
from app.services import apns as apns_service
from app.schemas.account import AccountRead
from app.schemas.api_responses import (
    OperationResult,
    ParseResult,
    PeriodDetailResponse,
    StatedBalanceItem,
    StatusUpdateRequest,
)
from app.schemas.document import DocumentRead
from app.schemas.orchestrate import OrchestrationResult
from app.schemas.period import PeriodCreate, PeriodRead
from app.agents._base import AgentError
from app.services import document as document_service
from app.services import orchestrate as orchestrate_service
from app.services import parse as parse_service
from app.services import period as period_service
from app.services import stated_balance as stated_balance_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["periods"], dependencies=[Depends(get_current_user)])


@router.get("/periods", response_model=list[PeriodRead])
async def list_periods(
    db: AsyncSession = Depends(get_db_session),
) -> list[PeriodRead]:
    periods = await period_service.list_periods(db)
    return [PeriodRead.model_validate(p) for p in periods]


@router.post("/periods", response_model=PeriodRead, status_code=status.HTTP_201_CREATED)
async def create_period(
    body: PeriodCreate,
    db: AsyncSession = Depends(get_db_session),
) -> PeriodRead:
    try:
        period = await period_service.create_period(db, year=body.year, month=body.month)
    except period_service.PeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Created period %s", period.period_id)
    return PeriodRead.model_validate(period)


@router.get("/periods/{period_id}", response_model=PeriodDetailResponse)
async def get_period_detail(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> PeriodDetailResponse:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    documents = await document_service.list_documents(db, period_id)

    accounts_result = await db.scalars(
        select(Account).where(Account.is_active.is_(True)).order_by(Account.account_code)
    )
    accounts = list(accounts_result.all())

    balance_accounts = await stated_balance_service.list_balance_accounts(db)
    balances = await stated_balance_service.list_balances(db, period_id)
    stated_balances = {row.account_code: str(row.stated_balance) for row in balances}

    txn_count = await db.scalar(
        select(func.count()).select_from(RawTransaction).where(RawTransaction.period_id == period_id)
    ) or 0
    staged_count = await db.scalar(
        select(func.count()).select_from(RawTransaction).where(
            RawTransaction.period_id == period_id, RawTransaction.status == "staged"
        )
    ) or 0
    approved_count = await db.scalar(
        select(func.count()).select_from(RawTransaction).where(
            RawTransaction.period_id == period_id, RawTransaction.status == "approved"
        )
    ) or 0
    posted_count = await db.scalar(
        select(func.count()).select_from(RawTransaction).where(
            RawTransaction.period_id == period_id, RawTransaction.status == "posted"
        )
    ) or 0
    unclassified_count = await db.scalar(
        select(func.count()).select_from(RawTransaction).where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "staged",
            RawTransaction.classifier_confidence == Decimal("0"),
            RawTransaction.is_duplicate.is_(False),
        )
    ) or 0
    posted_doc_ids_result = await db.scalars(
        select(RawTransaction.document_id).where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "posted",
        ).distinct()
    )
    posted_doc_ids = [str(did) for did in posted_doc_ids_result.all() if did is not None]

    return PeriodDetailResponse(
        period=PeriodRead.model_validate(period),
        transaction_count=int(txn_count),
        staged_count=int(staged_count),
        approved_count=int(approved_count),
        posted_count=int(posted_count),
        unclassified_count=int(unclassified_count),
        documents=[DocumentRead.model_validate(d) for d in documents],
        accounts=[AccountRead.model_validate(a) for a in accounts],
        balance_accounts=[AccountRead.model_validate(a) for a in balance_accounts],
        stated_balances=stated_balances,
        has_pending_documents=any(d.parse_status == "pending" for d in documents),
        posted_doc_ids=posted_doc_ids,
        next_status=period_service.next_status(period.status),
        prev_status=period_service.prev_status(period.status),
    )


@router.post("/periods/{period_id}/status", response_model=PeriodRead)
async def update_period_status(
    period_id: uuid.UUID,
    body: StatusUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> PeriodRead:
    try:
        period = await period_service.update_status(db, period_id, body.new_status)
    except period_service.PeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Updated period %s status to %s", period_id, body.new_status)

    # When the user advances the workflow to pending_close, push a reminder to
    # their other devices. Background-scheduled so the HTTP response doesn't
    # wait on APNs latency.
    if body.new_status == "pending_close":
        background_tasks.add_task(
            apns_service.notify_user,
            db,
            current_user.user_id,
            title="Ready to close",
            body=f"Period {period.period_start:%b %Y} is ready to close.",
            extra={"period_id": str(period_id), "kind": "period_pending_close"},
        )

    return PeriodRead.model_validate(period)


@router.post("/periods/{period_id}/step-back", response_model=PeriodRead)
async def step_back_period(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> PeriodRead:
    try:
        period = await period_service.step_back(db, period_id)
    except period_service.PeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Stepped back period %s to %s", period_id, period.status)
    return PeriodRead.model_validate(period)


@router.post("/periods/{period_id}/reopen", response_model=PeriodRead)
async def reopen_period(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> PeriodRead:
    try:
        period = await period_service.reopen_period(db, period_id)
    except period_service.PeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Reopened period %s", period_id)
    return PeriodRead.model_validate(period)


@router.delete("/periods/{period_id}", response_model=OperationResult)
async def delete_period(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> OperationResult:
    try:
        await period_service.delete_period(db, period_id)
    except period_service.PeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Deleted period %s", period_id)
    return OperationResult(ok=True)


@router.post("/periods/{period_id}/parse", response_model=ParseResult)
async def parse_all_documents(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ParseResult:
    results = await parse_service.parse_period(db, period_id)
    errors = [str(err) for err in results.values() if isinstance(err, str)]
    parsed = sum(1 for v in results.values() if not isinstance(v, str))
    logger.info("Parsed %d documents for period %s, %d errors", parsed, period_id, len(errors))
    return ParseResult(parsed=parsed, errors=errors)


@router.post("/periods/{period_id}/orchestrate-parse", response_model=OrchestrationResult)
async def orchestrate_parse_documents(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> OrchestrationResult:
    try:
        result = await orchestrate_service.orchestrate_parse(db, period_id)
    except AgentError as exc:
        logger.exception("Orchestrator agent failed for period %s", period_id)
        raise HTTPException(status_code=502, detail="Orchestration agent failed") from exc
    except Exception:
        logger.exception("Unexpected error orchestrating period %s", period_id)
        raise HTTPException(
            status_code=500, detail="Unexpected error during orchestration"
        )
    logger.info(
        "Orchestrated parse for period %s: %d parsed, %d failed, %d need review, classifier_ran=%s",
        period_id,
        result.parsed,
        result.failed,
        result.needs_review,
        result.classifier_ran,
    )
    return result


@router.post("/periods/{period_id}/orchestrate-parse/stream")
async def orchestrate_parse_stream(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """SSE endpoint that streams orchestration progress as newline-delimited JSON events."""
    async def event_generator() -> object:
        try:
            async for event in orchestrate_service.orchestrate_parse_stream(db, period_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception:
            logger.exception("Error in orchestration stream for period %s", period_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/periods/{period_id}/balances", response_model=OperationResult)
async def upsert_balances(
    period_id: uuid.UUID,
    body: list[StatedBalanceItem],
    db: AsyncSession = Depends(get_db_session),
) -> OperationResult:
    valid_codes = {
        acct.account_code
        for acct in await stated_balance_service.list_balance_accounts(db)
    }
    batch: dict[int, Decimal] = {}
    for item in body:
        if item.account_code not in valid_codes:
            continue
        try:
            batch[item.account_code] = Decimal(item.stated_balance)
        except InvalidOperation:
            raise HTTPException(status_code=400, detail=f"Invalid balance for account {item.account_code}")
    try:
        count = await stated_balance_service.upsert_balances_batch(db, period_id, batch)
    except stated_balance_service.BalanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Upserted %d balance(s) for period %s", count, period_id)
    return OperationResult(ok=True)
