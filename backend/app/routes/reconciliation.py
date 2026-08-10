import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._base import AgentError
from app.agents.reconciliation import (
    AccountGap,
    ReconciliationAnalysis,
    run_reconciliation_agent,
)
from app.core.config import settings
from app.core.money import ZERO
from app.dependencies import get_current_user, get_db_session
from app.models.journal import JournalEntry, JournalLine
from app.models.reconciliation import Reconciliation
from app.schemas.api_responses import (
    AccountAnalysisSchema,
    ReconcilePageResponse,
    ReconciliationAnalysisSchema,
    UnrealizedGlRequest,
)
from app.schemas.period import PeriodRead
from app.schemas.reconciliation import ReconciliationDetail
from app.services import period as period_service
from app.services import reconciliation as recon_service
from app.services.scrub import scrub_description

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reconciliation"], dependencies=[Depends(get_current_user)])


async def _build_page(
    db: AsyncSession,
    period_id: uuid.UUID,
    analysis: ReconciliationAnalysis | None = None,
    balances: dict[int, dict] | None = None,
) -> ReconcilePageResponse:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    recon_rows = await db.scalars(
        select(Reconciliation).where(Reconciliation.period_id == period_id)
    )
    raw_rows = list(recon_rows.all())
    ran = len(raw_rows) > 0

    if ran:
        if balances is None:
            balances = await recon_service.compute_account_balances(db, period)
        details: list[ReconciliationDetail] = [
            ReconciliationDetail(
                recon_id=row.recon_id,
                period_id=row.period_id,
                account_code=row.account_code,
                account_name=balances.get(row.account_code, {}).get("account_name", ""),
                is_investment=balances.get(row.account_code, {}).get("is_investment", False),
                beginning_balance=balances.get(row.account_code, {}).get("beginning_balance", row.computed_balance),
                period_net_change=balances.get(row.account_code, {}).get(
                    "period_net_change", ZERO
                ),
                computed_balance=row.computed_balance,
                stated_balance=row.stated_balance,
                gap=row.gap,
                status=row.status,
                run_at=row.run_at,
            )
            for row in raw_rows
        ]
    else:
        details = []

    has_gaps = any(d.gap != 0 for d in details)
    has_investment_gaps = any(d.gap != 0 and d.is_investment for d in details)
    has_non_investment_gaps = any(d.gap != 0 and not d.is_investment for d in details)

    temp_preview = await recon_service.compute_temp_account_preview(db, period)
    equity_preview = await recon_service.compute_equity_rollup_preview(db, period)

    analysis_schema: ReconciliationAnalysisSchema | None = None
    if analysis is not None:
        analysis_schema = ReconciliationAnalysisSchema(
            accounts=[
                AccountAnalysisSchema(
                    account_code=a.account_code,
                    likely_causes=a.likely_causes,
                    suggested_actions=a.suggested_actions,
                    severity=a.severity,
                )
                for a in analysis.accounts
            ],
            overall_summary=analysis.overall_summary,
        )

    return ReconcilePageResponse(
        period=PeriodRead.model_validate(period),
        details=details,
        ran=ran,
        has_gaps=has_gaps,
        has_investment_gaps=has_investment_gaps,
        has_non_investment_gaps=has_non_investment_gaps,
        analysis=analysis_schema,
        temp_preview=temp_preview,
        equity_preview=equity_preview,
    )


@router.get("/periods/{period_id}/reconcile", response_model=ReconcilePageResponse)
async def get_reconcile_page(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    return await _build_page(db, period_id)


@router.post("/periods/{period_id}/reconcile", response_model=ReconcilePageResponse)
async def run_reconciliation(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    try:
        _, balances = await recon_service.run_reconciliation(db, period_id)
    except recon_service.ReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _build_page(db, period_id, balances=balances)


@router.post("/periods/{period_id}/reconcile/analyze", response_model=ReconcilePageResponse)
async def analyze_reconciliation(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    period = await period_service.get_period(db, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    recon_rows = await db.scalars(
        select(Reconciliation).where(Reconciliation.period_id == period_id)
    )
    raw_rows = list(recon_rows.all())

    gaps: list[AccountGap] = []
    balances = await recon_service.compute_account_balances(db, period)
    for row in raw_rows:
        info = balances.get(row.account_code, {})
        if row.gap == 0 or info.get("is_investment", False):
            continue
        recent_entries_result = await db.scalars(
            select(JournalEntry.description)
            .join(JournalLine, JournalLine.entry_id == JournalEntry.entry_id)
            .where(
                JournalEntry.period_id == period_id,
                JournalLine.account_code == row.account_code,
            )
            .order_by(JournalEntry.entry_date.desc())
            .limit(5)
        )
        account_name = info.get("account_name", "")
        recent_descriptions = list(recent_entries_result.all())
        if settings.scrub_before_llm:
            # These descriptions are derived from statement text, so they carry
            # the same identifiers. The account name is a keep_term — it comes
            # from the chart of accounts and the agent needs it to reason.
            recent_descriptions = [
                scrub_description(d, keep_terms=[account_name]) for d in recent_descriptions
            ]
        gaps.append(AccountGap(
            account_code=row.account_code,
            account_name=account_name,
            computed_balance=row.computed_balance,
            stated_balance=row.stated_balance,
            gap=row.gap,
            recent_entry_descriptions=recent_descriptions,
        ))

    analysis: ReconciliationAnalysis | None = None
    if gaps:
        # recent_entry_descriptions are user-supplied JE text and can carry
        # prompt-injection content. The agent's output is advisory only — a
        # structured ReconciliationAnalysis shown to the operator, never used to
        # post journal entries — so the blast radius is limited to bad advice.
        try:
            analysis = await run_reconciliation_agent(gaps)
        except AgentError as exc:
            raise HTTPException(status_code=502, detail="Reconciliation analysis failed") from exc

    return await _build_page(db, period_id, analysis=analysis)


@router.post("/periods/{period_id}/reconcile/post-unrealized", response_model=ReconcilePageResponse)
async def post_unrealized_gl(
    period_id: uuid.UUID,
    body: UnrealizedGlRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    try:
        await recon_service.post_unrealized_gl_targeted(db, period_id, body.account_code)
    except recon_service.ReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _build_page(db, period_id)


@router.post("/periods/{period_id}/reconcile/post-closing", response_model=ReconcilePageResponse)
async def post_closing_entries(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    try:
        await recon_service.post_closing_entries(db, period_id)
    except recon_service.ReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _build_page(db, period_id)


@router.post("/periods/{period_id}/reconcile/post-equity-rollup", response_model=ReconcilePageResponse)
async def post_equity_rollup(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ReconcilePageResponse:
    try:
        await recon_service.post_equity_rollup(db, period_id)
    except recon_service.ReconciliationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _build_page(db, period_id)
