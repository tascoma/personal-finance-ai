import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.schemas.api_responses import (
    BalanceSheetPivotResponse,
    BalanceSheetPivotSectionSchema,
    BalanceSheetPivotRowSchema,
    CashflowStatementResponse,
    IncomeStatementResponse,
    StatementLineSchema,
    StatementSectionSchema,
)
from app.schemas.period import PeriodRead
from app.services import statements as stmt_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["statements"], dependencies=[Depends(get_current_user)])


@router.get("/statements/balance-sheet", response_model=BalanceSheetPivotResponse)
async def get_balance_sheet_pivot(
    db: AsyncSession = Depends(get_db_session),
) -> BalanceSheetPivotResponse:
    pivot = await stmt_service.compute_balance_sheet_pivot(db)

    def _convert_section(section: stmt_service.BalanceSheetPivotSection) -> BalanceSheetPivotSectionSchema:
        return BalanceSheetPivotSectionSchema(
            label=section.label,
            rows=[
                BalanceSheetPivotRowSchema(
                    account_code=r.account_code,
                    account_name=r.account_name,
                    sub_category=r.sub_category,
                    balances=[str(b) for b in r.balances],
                )
                for r in section.rows
            ],
            subtotals=[str(s) for s in section.subtotals],
        )

    return BalanceSheetPivotResponse(
        periods=[PeriodRead.model_validate(p) for p in pivot.periods],
        assets=[_convert_section(s) for s in pivot.assets],
        liabilities=[_convert_section(s) for s in pivot.liabilities],
        equity=[_convert_section(s) for s in pivot.equity],
        off_balance_sheet=[_convert_section(s) for s in pivot.off_balance_sheet],
        total_assets=[str(v) for v in pivot.total_assets],
        total_liabilities=[str(v) for v in pivot.total_liabilities],
        total_equity=[str(v) for v in pivot.total_equity],
        total_off_balance_sheet=[str(v) for v in pivot.total_off_balance_sheet],
    )


@router.get("/statements/income", response_model=IncomeStatementResponse)
async def get_income_statement(
    period_id: Optional[uuid.UUID] = Query(None),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> IncomeStatementResponse:
    period_ids = [period_id] if period_id else None
    if period_id is not None:
        label = str(period_id)
    elif year is not None:
        label = str(year)
    else:
        label = "All Periods"
    stmt = await stmt_service.compute_income_statement(db, period_ids, label, year=year)

    def _section(s: stmt_service.StatementSection) -> StatementSectionSchema:
        return StatementSectionSchema(
            label=s.label,
            lines=[
                StatementLineSchema(
                    account_code=ln.account_code,
                    account_name=ln.account_name,
                    sub_category=ln.sub_category,
                    amount=str(ln.amount),
                )
                for ln in s.lines
            ],
            subtotal=str(s.subtotal),
        )

    return IncomeStatementResponse(
        range_label=stmt.range_label,
        income=[_section(s) for s in stmt.income],
        expenses=[_section(s) for s in stmt.expenses],
        other_comprehensive_income=[_section(s) for s in stmt.other_comprehensive_income],
        total_income=str(stmt.total_income),
        total_expenses=str(stmt.total_expenses),
        total_oci=str(stmt.total_oci),
        net_income=str(stmt.net_income),
        comprehensive_income=str(stmt.comprehensive_income),
    )


@router.get("/statements/cashflow", response_model=CashflowStatementResponse)
async def get_cashflow_statement(
    period_id: Optional[uuid.UUID] = Query(None),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> CashflowStatementResponse:
    period_ids = [period_id] if period_id else None
    if period_id is not None:
        label = str(period_id)
    elif year is not None:
        label = str(year)
    else:
        label = "All Periods"
    stmt = await stmt_service.compute_cashflow(db, period_ids, label, year=year)

    def _line(ln: stmt_service.StatementLine) -> StatementLineSchema:
        return StatementLineSchema(
            account_code=ln.account_code,
            account_name=ln.account_name,
            sub_category=ln.sub_category,
            amount=str(ln.amount),
        )

    return CashflowStatementResponse(
        range_label=stmt.range_label,
        net_income=str(stmt.net_income),
        noncash_adjustments=[_line(ln) for ln in stmt.noncash_adjustments],
        working_capital_changes=[_line(ln) for ln in stmt.working_capital_changes],
        operating_total=str(stmt.operating_total),
        investing=[_line(ln) for ln in stmt.investing],
        investing_total=str(stmt.investing_total),
        financing=[_line(ln) for ln in stmt.financing],
        financing_total=str(stmt.financing_total),
        net_change_in_cash=str(stmt.net_change_in_cash),
        cash_by_account=[_line(ln) for ln in stmt.cash_by_account],
        beginning_cash=str(stmt.beginning_cash),
        ending_cash=str(stmt.ending_cash),
    )
