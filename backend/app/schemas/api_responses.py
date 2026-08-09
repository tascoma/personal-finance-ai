"""Composite Pydantic schemas for the /api/v1/ JSON layer.

These don't map 1:1 to ORM models — they assemble data from multiple sources
for a single API response so the React frontend can render a full page from
one request.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.account import AccountRead
from app.schemas.document import DocumentRead
from app.schemas.journal import JournalEntryRead, JournalLineRead
from app.schemas.period import PeriodRead
from app.schemas.raw_transaction import RawTransactionRead
from app.schemas.reconciliation import (
    EquityRollupPreview,
    ReconciliationDetail,
    TempAccountPreview,
)


# ── Dashboard ─────────────────────────────────────────────────────────────────


class PeriodBarPoint(BaseModel):
    period_label: str
    income: str
    expenses: str
    net: str


class NetWorthPoint(BaseModel):
    period_label: str
    net_worth: str


class ExpenseCategoryPoint(BaseModel):
    category: str
    amount: str


class MoneyFlowBucketPoint(BaseModel):
    category: str
    amount: str


class MoneyFlowResponse(BaseModel):
    """Sources and uses; sum(income) == sum(expenses) + sum(fund_flows).

    Amounts are signed: positive fund_flows are uses (asset bought, debt repaid),
    negative ones are sources (cash drawn down).
    """

    income: list[MoneyFlowBucketPoint]
    expenses: list[MoneyFlowBucketPoint]
    fund_flows: list[MoneyFlowBucketPoint]


class PaycheckFlowResponse(BaseModel):
    """Paycheck-shaped money flow: gross → withholdings → take-home → spending.

    Amounts are strings (decimals). Invariants:
      sum(earnings) + sum(employer) == take_home + sum(deductions)
      take_home + sum(other_income) + sum(drawdowns) == sum(uses)
    Employer contributions appear once as income (employer) and once as a
    withholding (their paired asset debit stays in deductions). Deductions use
    per-account labels (e.g. "401(k)", "HSA") with sub_category fallback.
    """

    earnings: list[MoneyFlowBucketPoint]
    deductions: list[MoneyFlowBucketPoint]
    employer: list[MoneyFlowBucketPoint]
    take_home: str
    other_income: list[MoneyFlowBucketPoint]
    drawdowns: list[MoneyFlowBucketPoint]
    uses: list[MoneyFlowBucketPoint]


class ExpenseCategorySeriesPoint(BaseModel):
    period_label: str
    category: str
    amount: str


class AssetCompositionPoint(BaseModel):
    sub_category: str
    amount: str


class AssetSeriesPoint(BaseModel):
    period_label: str
    sub_category: str
    amount: str


class RetirementContributionPoint(BaseModel):
    account_code: int
    account_name: str
    amount: str


class RecentEntryPoint(BaseModel):
    description: str
    entry_date: str
    source_type: str
    period_label: str
    total_debit: str


class DashboardResponse(BaseModel):
    total_income: str
    total_expenses: str
    net_income: str
    total_assets: str
    total_assets_prev: str
    total_liabilities: str
    net_worth: str
    investing_cashflow: str
    salary_income: str
    retirement_contributions: str
    compensation_income: str
    lifestyle_expenses: str
    oci: str
    liquid_assets: str
    liquid_assets_prev: str
    tax_advantaged: str
    tax_advantaged_prev: str
    period_count: int
    has_data: bool
    period_bars: list[PeriodBarPoint]
    net_worth_series: list[NetWorthPoint]
    top_expense_categories: list[ExpenseCategoryPoint]
    money_flow: MoneyFlowResponse
    paycheck_flow: PaycheckFlowResponse
    expense_category_series: list[ExpenseCategorySeriesPoint]
    asset_composition: list[AssetCompositionPoint]
    asset_series: list[AssetSeriesPoint]
    ytd_year: Optional[int]
    ytd_retirement_contributions: list[RetirementContributionPoint]
    recent_entries: list[RecentEntryPoint]
    active_period: Optional[PeriodRead]


# ── Period detail ─────────────────────────────────────────────────────────────


class PeriodDetailResponse(BaseModel):
    period: PeriodRead
    transaction_count: int
    staged_count: int
    approved_count: int
    posted_count: int
    unclassified_count: int
    documents: list[DocumentRead]
    accounts: list[AccountRead]
    balance_accounts: list[AccountRead]
    stated_balances: dict[int, str]
    has_pending_documents: bool
    posted_doc_ids: list[str]
    next_status: Optional[str]
    prev_status: Optional[str]


# ── Ledger ────────────────────────────────────────────────────────────────────


class JournalEntryWithLines(JournalEntryRead):
    lines: list[JournalLineRead]


class LedgerResponse(BaseModel):
    periods: list[PeriodRead]
    entries_by_period: dict[str, list[JournalEntryWithLines]]
    accounts_by_code: dict[int, AccountRead]


# ── Statements ────────────────────────────────────────────────────────────────


class StatementLineSchema(BaseModel):
    account_code: int
    account_name: str
    sub_category: str
    amount: str


class StatementSectionSchema(BaseModel):
    label: str
    lines: list[StatementLineSchema]
    subtotal: str


class BalanceSheetPivotRowSchema(BaseModel):
    account_code: int
    account_name: str
    sub_category: str
    balances: list[str]


class BalanceSheetPivotSectionSchema(BaseModel):
    label: str
    rows: list[BalanceSheetPivotRowSchema]
    subtotals: list[str]


class BalanceSheetPivotResponse(BaseModel):
    periods: list[PeriodRead]
    assets: list[BalanceSheetPivotSectionSchema]
    liabilities: list[BalanceSheetPivotSectionSchema]
    equity: list[BalanceSheetPivotSectionSchema]
    off_balance_sheet: list[BalanceSheetPivotSectionSchema]
    total_assets: list[str]
    total_liabilities: list[str]
    total_equity: list[str]
    total_off_balance_sheet: list[str]


class IncomeStatementResponse(BaseModel):
    range_label: str
    income: list[StatementSectionSchema]
    expenses: list[StatementSectionSchema]
    other_comprehensive_income: list[StatementSectionSchema]
    total_income: str
    total_expenses: str
    total_oci: str
    net_income: str
    comprehensive_income: str


class CashflowStatementResponse(BaseModel):
    range_label: str
    net_income: str
    noncash_adjustments: list[StatementLineSchema]
    working_capital_changes: list[StatementLineSchema]
    operating_total: str
    investing: list[StatementLineSchema]
    investing_total: str
    financing: list[StatementLineSchema]
    financing_total: str
    net_change_in_cash: str
    cash_by_account: list[StatementLineSchema]
    beginning_cash: str
    ending_cash: str


# ── Journal page ──────────────────────────────────────────────────────────────


class JournalPageResponse(BaseModel):
    period: PeriodRead
    accounts: list[AccountRead]
    staged: list[RawTransactionRead]
    approved: list[RawTransactionRead]
    entries: list[JournalEntryWithLines]
    has_unclassified: bool
    documents: list[DocumentRead]
    docs_missing_source: list[DocumentRead]
    next_status: Optional[str]
    prev_status: Optional[str]


# ── Reconciliation page ───────────────────────────────────────────────────────


class AccountAnalysisSchema(BaseModel):
    account_code: int
    likely_causes: list[str]
    suggested_actions: list[str]
    severity: str


class ReconciliationAnalysisSchema(BaseModel):
    accounts: list[AccountAnalysisSchema]
    overall_summary: str


class ReconcilePageResponse(BaseModel):
    period: PeriodRead
    details: list[ReconciliationDetail]
    ran: bool
    has_gaps: bool
    has_investment_gaps: bool
    has_non_investment_gaps: bool
    analysis: Optional[ReconciliationAnalysisSchema]
    temp_preview: TempAccountPreview
    equity_preview: EquityRollupPreview


# ── Request schemas ───────────────────────────────────────────────────────────


class ManualTransactionItem(BaseModel):
    txn_date: str
    description: str
    amount: str
    account_code: int


class ManualTransactionBatch(BaseModel):
    transactions: list[ManualTransactionItem]


class JournalLineCreate(BaseModel):
    account_code: int
    debit: str
    credit: str
    memo: Optional[str] = None


class ManualJournalEntryCreate(BaseModel):
    entry_date: str
    description: str
    source_type: str
    lines: list[JournalLineCreate]


class StatedBalanceItem(BaseModel):
    account_code: int
    stated_balance: str


class OperationResult(BaseModel):
    ok: bool


class CountResult(BaseModel):
    count: int


class ParseResult(BaseModel):
    parsed: int
    errors: list[str]


class StatusUpdateRequest(BaseModel):
    new_status: str


class SourceAccountRequest(BaseModel):
    source_account_code: Optional[int] = None


class AccountCodeRequest(BaseModel):
    account_code: int


class UnrealizedGlRequest(BaseModel):
    account_code: int
