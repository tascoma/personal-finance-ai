import logging
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.schemas.api_responses import (
    AssetCompositionPoint,
    AssetSeriesPoint,
    DashboardResponse,
    ExpenseCategoryPoint,
    ExpenseCategorySeriesPoint,
    NetWorthPoint,
    PeriodBarPoint,
    RecentEntryPoint,
    RetirementContributionPoint,
)
from app.schemas.period import PeriodRead
from app.services import dashboard as dashboard_service
from app.services.period import get_current_open_period

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    year: int | None = Query(None),
    period_id: uuid.UUID | None = Query(None),
    from_period_id: uuid.UUID | None = Query(None),
    to_period_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardResponse:
    data = await dashboard_service.compute_dashboard(
        db,
        year=year,
        period_id=period_id,
        from_period_id=from_period_id,
        to_period_id=to_period_id,
    )
    active_period = await get_current_open_period(db)

    return DashboardResponse(
        total_income=str(data.total_income),
        total_expenses=str(data.total_expenses),
        net_income=str(data.net_income),
        total_assets=str(data.total_assets),
        total_assets_prev=str(data.total_assets_prev),
        total_liabilities=str(data.total_liabilities),
        net_worth=str(data.net_worth),
        investing_cashflow=str(data.investing_cashflow),
        salary_income=str(data.salary_income),
        retirement_contributions=str(data.retirement_contributions),
        compensation_income=str(data.compensation_income),
        lifestyle_expenses=str(data.lifestyle_expenses),
        oci=str(data.oci),
        liquid_assets=str(data.liquid_assets),
        liquid_assets_prev=str(data.liquid_assets_prev),
        tax_advantaged=str(data.tax_advantaged),
        tax_advantaged_prev=str(data.tax_advantaged_prev),
        period_count=data.period_count,
        has_data=data.has_data,
        period_bars=[
            PeriodBarPoint(
                period_label=b.label,
                income=str(b.income),
                expenses=str(b.expenses),
                net=str(b.net),
            )
            for b in data.period_bars
        ],
        net_worth_series=[
            NetWorthPoint(period_label=p.label, net_worth=str(p.net_worth))
            for p in data.net_worth_series
        ],
        top_expense_categories=[
            ExpenseCategoryPoint(category=c.label, amount=str(c.amount))
            for c in data.top_expense_categories
        ],
        expense_category_series=[
            ExpenseCategorySeriesPoint(
                period_label=p.period_label,
                category=p.category,
                amount=str(p.amount),
            )
            for p in data.expense_category_series
        ],
        asset_composition=[
            AssetCompositionPoint(sub_category=c.sub_category, amount=str(c.amount))
            for c in data.asset_composition
        ],
        asset_series=[
            AssetSeriesPoint(
                period_label=p.period_label,
                sub_category=p.sub_category,
                amount=str(p.amount),
            )
            for p in data.asset_series
        ],
        ytd_year=data.ytd_year,
        ytd_retirement_contributions=[
            RetirementContributionPoint(
                account_code=c.account_code,
                account_name=c.account_name,
                amount=str(c.amount),
            )
            for c in data.ytd_retirement_contributions
        ],
        recent_entries=[
            RecentEntryPoint(
                description=e.description,
                entry_date=e.entry_date,
                source_type=e.source_type,
                period_label=e.period_label,
                total_debit=str(e.total_debit),
            )
            for e in data.recent_entries
        ],
        active_period=PeriodRead.model_validate(active_period) if active_period else None,
    )
