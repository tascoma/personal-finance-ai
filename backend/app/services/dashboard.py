"""Dashboard metrics — all data computed in two queries (lines + recent entries).

Every monetary field on the chart dataclasses below is `Decimal`, matching the
`Numeric(15, 2)` columns they aggregate. The route layer serializes them with
`str(...)`, so a float anywhere in this chain would leak its repr into the API
(a period net of 1234.56 arriving at the client as "1234.5600000000001").
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import ZERO as _ZERO
from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.services.statements import OCI_ACCOUNT_CODES


@dataclass
class PeriodBar:
    label: str
    income: Decimal
    expenses: Decimal
    net: Decimal


@dataclass
class NetWorthPoint:
    label: str
    net_worth: Decimal


@dataclass
class ExpenseCategory:
    label: str
    amount: Decimal


@dataclass
class MoneyFlowBucket:
    label: str
    amount: Decimal


@dataclass
class MoneyFlow:
    """Sources and uses of money, grouped by sub_category.

    Guarantees the identity

        sum(income) == sum(expenses) + sum(fund_flows)

    where a *use* of funds is `debit - credit` for both Asset and Liability
    lines: an asset increase is a use, a liability decrease (paying down debt)
    is a use, and a cash decrease is a negative use — i.e. a source. Income is
    just a negative use, negated once here so it reads positive.

    The identity holds because over any union of whole balanced entries
    `sum(debit - credit) == 0`; restricting to entries whose lines are all
    Income/Expense/Asset/Liability rearranges that into the statement above.
    See _flow_entry_is_excluded for the restriction.

    Note this is a *different* line set from total_income/total_expenses, which
    exclude OCI per-line rather than per-entry. The two agree unless income is
    ever booked inside an excluded entry (e.g. a receipt posted against equity).
    """

    income: list[MoneyFlowBucket]
    expenses: list[MoneyFlowBucket]
    fund_flows: list[MoneyFlowBucket]


# Employer-side income that never touches take-home cash: each is offset by an
# asset debit in the same paystub entry (a retirement/investment account), not by
# the net-pay deposit. Listed separately so the Sankey can label the source as
# employer money; the paired asset debit stays in the deduction buckets, so the
# contribution appears once as income and once as a withholding — the two sides
# of the same flow. Keyed income account code -> destination asset sub_category.
_EMPLOYER_CONTRIB_DESTINATIONS: dict[int, str] = {
    400106: "Retirement & Tax-Advantaged Accounts",  # employer 401(k) match
    400104: "Investments",                           # employer stock contribution
}

# Paystub withholdings that land in an asset get a per-account label so the
# Sankey can show "401(k)" (employee deferral + employer match merged) rather
# than a whole sub_category. Expense withholdings fall back to sub_category
# ("Payroll Taxes", "Employee Benefits", "Giving"). Mirrored by
# DEDUCTION_FUND_LABELS in frontend/src/pages/dashboard/sankeyData.ts.
_DEDUCTION_ACCOUNT_LABELS: dict[int, str] = {
    111102: "401(k)",                # Merrill – Roth 401(k)
    111103: "HSA",                   # HSA – Investments
    100201: "HSA",                   # HSA – Cash (Restricted Cash)
    112101: "Vested Fidelity",       # Fidelity – RSUs (Vested)
    110102: "ComputerShare – ASPP",  # employee ASPP + employer stock
}


@dataclass
class PaycheckFlow:
    """Paycheck-shaped money flow: gross → withholdings → take-home → spending.

    Built from the same balanced whole-entry line set as MoneyFlow, but decomposed
    into a multi-stage graph. Paystub entries (source_type == "paystub") are split
    into gross earnings, the withholdings that branch off (taxes, benefits, and
    pre-tax savings), and the net cash actually deposited (take_home). Everything
    else feeds a downstream "spendable" pool along with take-home.

    Invariants, exact over Decimal (see test_paycheck_flow_balances):
      sum(earnings) + sum(employer)            == take_home + sum(deductions)
      take_home + sum(other_income) + drawdowns_total == sum(uses)
    Employer contributions appear once as income (the employer list) and once as
    a withholding (their paired asset debit stays in deductions) — the two sides
    of the same flow, exactly like an employee deferral.
    """

    earnings: list[MoneyFlowBucket]      # employee gross by sub_category
    deductions: list[MoneyFlowBucket]    # taxes, benefits, savings withholdings —
                                         # per-account labels via _DEDUCTION_ACCOUNT_LABELS,
                                         # sub_category fallback
    employer: list[MoneyFlowBucket]      # employer contributions; label = savings destination
    take_home: Decimal                   # net cash deposited = sum(earnings) − sum(deductions)
    other_income: list[MoneyFlowBucket]  # non-paystub income by sub_category
    drawdowns: list[MoneyFlowBucket]     # non-paystub sources feeding spending (cash drawn, assets sold)
    uses: list[MoneyFlowBucket]          # living expenses + post-tax savings + cash saved


@dataclass
class ExpenseCategorySeriesPoint:
    period_label: str
    category: str
    amount: Decimal


@dataclass
class AssetCompositionPoint:
    sub_category: str
    amount: Decimal


@dataclass
class AssetSeriesPoint:
    period_label: str
    sub_category: str
    amount: Decimal


@dataclass
class RetirementContributionPoint:
    account_code: int
    account_name: str
    amount: Decimal


@dataclass
class RecentEntry:
    description: str
    entry_date: str
    source_type: str
    period_label: str
    total_debit: Decimal


@dataclass
class DashboardData:
    total_income: Decimal
    total_expenses: Decimal
    net_income: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    investing_cashflow: Decimal
    salary_income: Decimal
    retirement_contributions: Decimal
    compensation_income: Decimal
    lifestyle_expenses: Decimal
    oci: Decimal
    period_bars: list[PeriodBar]
    net_worth_series: list[NetWorthPoint]
    top_expense_categories: list[ExpenseCategory]
    money_flow: MoneyFlow
    paycheck_flow: PaycheckFlow
    expense_category_series: list[ExpenseCategorySeriesPoint]
    asset_composition: list[AssetCompositionPoint]
    asset_series: list[AssetSeriesPoint]
    recent_entries: list[RecentEntry]
    period_count: int
    has_data: bool
    liquid_assets: Decimal
    liquid_assets_prev: Decimal
    tax_advantaged: Decimal
    tax_advantaged_prev: Decimal
    total_assets_prev: Decimal
    ytd_year: int | None
    ytd_retirement_contributions: list[RetirementContributionPoint]


def _sum_by_type(
    lines: list[JournalLine],
    accounts: dict[int, Account],
    account_type: str,
    exclude_codes: frozenset[int] = frozenset(),
) -> Decimal:
    total = _ZERO
    for line in lines:
        acct = accounts.get(line.account_code)
        if acct is None or acct.account_type != account_type or acct.is_memo:
            continue
        if line.account_code in exclude_codes:
            continue
        # Income accounts always contribute credit − debit regardless of normal_balance,
        # so that contra-income accounts (e.g. Capital Losses, debit-normal) correctly
        # reduce total_income rather than adding to it.
        if acct.normal_balance == "debit" and account_type != "Income":
            total += line.debit_amount - line.credit_amount
        else:
            total += line.credit_amount - line.debit_amount
    return total


# Dining Out + Alcohol are treated as discretionary alongside the "Lifestyle"
# sub_category (Travel, Entertainment, Hobbies, Electronics).
_LIFESTYLE_EXTRA_CODES = {520102, 520103}
_RETIREMENT_CODES = frozenset({111101, 111102, 111103})
_REAL_ESTATE_SUBCATS = frozenset({"Real Estate"})


def _is_lifestyle(acct: Account) -> bool:
    return acct.sub_category == "Lifestyle" or acct.account_code in _LIFESTYLE_EXTRA_CODES


def _expense_by_subcategory(
    lines: list[JournalLine],
    accounts: dict[int, Account],
) -> list[ExpenseCategory]:
    by_cat: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for line in lines:
        acct = accounts.get(line.account_code)
        if acct is None or acct.account_type != "Expense" or acct.is_memo:
            continue
        by_cat[acct.sub_category] += line.debit_amount - line.credit_amount
    return sorted(
        [ExpenseCategory(label=k, amount=v) for k, v in by_cat.items() if v > _ZERO],
        key=lambda c: c.amount,
        reverse=True,
    )[:8]


# The four account types whose debit − credit provably sums to zero over any
# union of whole balanced entries. Anything else (Equity opening balances, memo
# accounts) would leave the money-flow identity unbalanced.
_FLOW_TYPES = frozenset({"Income", "Expense", "Asset", "Liability"})


def _flow_entry_is_excluded(entry_lines: list[JournalLine], accounts: dict[int, Account]) -> bool:
    """Whether an entry must be kept out of the money-flow model entirely.

    Entries are dropped whole, never line by line — dropping one leg of a
    balanced entry is exactly what breaks the identity in MoneyFlow. An entry
    goes if any line is on an unknown account, on an account outside
    _FLOW_TYPES, or on an OCI account (unrealized marks pair an income leg with
    an asset leg that isn't a real use of funds, so both legs must go).
    """
    for line in entry_lines:
        acct = accounts.get(line.account_code)
        if acct is None or acct.account_type not in _FLOW_TYPES:
            return True
        if line.account_code in OCI_ACCOUNT_CODES:
            return True
    return False


def _flow_buckets(
    lines: list[JournalLine],
    accounts: dict[int, Account],
    types: tuple[str, ...],
) -> list[MoneyFlowBucket]:
    """Signed debit − credit by sub_category. Positive means a use of funds.

    No normal_balance branch: contra accounts (e.g. Capital Losses, which is
    debit-normal Income) net down their own bucket for free. Zero buckets are
    dropped; negative ones are kept, since the Sankey renders them on the
    opposite side rather than discarding them.
    """
    by_cat: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for line in lines:
        acct = accounts.get(line.account_code)
        if acct is None or acct.account_type not in types:
            continue
        by_cat[acct.sub_category] += line.debit_amount - line.credit_amount
    return sorted(
        [MoneyFlowBucket(label=k, amount=v) for k, v in by_cat.items() if v != _ZERO],
        key=lambda b: b.amount,
        reverse=True,
    )


def _sorted_buckets(by_cat: dict[str, Decimal]) -> list[MoneyFlowBucket]:
    return sorted(
        [MoneyFlowBucket(label=k, amount=v) for k, v in by_cat.items() if v > _ZERO],
        key=lambda b: b.amount,
        reverse=True,
    )


def _paycheck_flow(
    flow_entries: list[tuple[str, list[JournalLine]]],
    accounts: dict[int, Account],
    spendable_cash_codes: frozenset[int],
) -> PaycheckFlow:
    """Decompose balanced flow entries into the paycheck-shaped graph.

    See PaycheckFlow for the model and its balance invariants. The invariants hold
    because `sum(debit − credit) == 0` over each whole entry: within a paystub
    entry the employee earning credits equal take-home plus the withholding debits,
    and over non-paystub entries income equals expenses plus fund flows.
    """
    earn: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    employer: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    ded: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    take_home = _ZERO

    other: dict[str, Decimal] = defaultdict(lambda: _ZERO)  # non-paystub income, positive
    use: dict[str, Decimal] = defaultdict(lambda: _ZERO)    # non-paystub expense/asset/liab, signed (+ = use)
    cash_change = _ZERO  # net change of spendable cash across all entries (includes take-home)

    for source_type, entry_lines in flow_entries:
        for line in entry_lines:
            acct = accounts.get(line.account_code)
            if acct is None:
                continue
            signed = line.debit_amount - line.credit_amount  # positive = a use of funds

            if line.account_code in spendable_cash_codes:
                cash_change += signed
                if source_type == "paystub":
                    take_home += signed
                continue

            if source_type == "paystub":
                if acct.account_type == "Income":
                    credit = -signed  # income is credit-normal
                    dest = _EMPLOYER_CONTRIB_DESTINATIONS.get(line.account_code)
                    if dest is not None:
                        employer[dest] += credit
                    else:
                        earn[acct.sub_category] += credit
                else:
                    # Expense / Asset / Liability debit — a withholding branching
                    # off the paystub before take-home.
                    ded[_DEDUCTION_ACCOUNT_LABELS.get(line.account_code, acct.sub_category)] += signed
            else:
                if acct.account_type == "Income":
                    other[acct.sub_category] += -signed
                else:
                    use[acct.sub_category] += signed

    # Split non-paystub uses into uses (positive) and drawdown sources (negative),
    # then place the net cash change on the correct side of the spendable pool.
    uses: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    drawdowns: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for cat, amt in use.items():
        if amt > _ZERO:
            uses[cat] += amt
        elif amt < _ZERO:
            drawdowns[cat] += -amt
    if cash_change > _ZERO:
        uses["Cash & Cash Equivalents"] += cash_change
    elif cash_change < _ZERO:
        drawdowns["Cash & Cash Equivalents"] += -cash_change

    return PaycheckFlow(
        earnings=_sorted_buckets(earn),
        deductions=_sorted_buckets(ded),
        employer=_sorted_buckets(employer),
        take_home=take_home,
        other_income=_sorted_buckets(other),
        drawdowns=_sorted_buckets(drawdowns),
        uses=_sorted_buckets(uses),
    )


async def compute_dashboard(
    db: AsyncSession,
    year: int | None = None,
    period_id: uuid.UUID | None = None,
    from_period_id: uuid.UUID | None = None,
    to_period_id: uuid.UUID | None = None,
) -> DashboardData:
    accounts_result = await db.scalars(select(Account))
    accounts: dict[int, Account] = {a.account_code: a for a in accounts_result.all()}

    periods_result = await db.scalars(select(Period).order_by(Period.period_start.asc()))
    all_periods = list(periods_result.all())

    if period_id is not None:
        periods = [p for p in all_periods if p.period_id == period_id]
    elif from_period_id is not None or to_period_id is not None:
        from_start = next((p.period_start for p in all_periods if p.period_id == from_period_id), None)
        to_start = next((p.period_start for p in all_periods if p.period_id == to_period_id), None)
        periods = [
            p for p in all_periods
            if (from_start is None or p.period_start >= from_start)
            and (to_start is None or p.period_start <= to_start)
        ]
    elif year is not None:
        periods = [p for p in all_periods if p.period_start.year == year]
    else:
        periods = all_periods

    # Only closed periods contribute to operating (income/expense) metrics, but
    # balance-sheet cumulative state must also include any earlier still-open
    # periods (e.g. an "opening balances" seed posted to a bootstrap month that
    # was never formally closed). Without this, KPI totals like total_assets
    # show just the latest period's net change instead of the running balance.
    all_closed_periods = [p for p in all_periods if p.status == "closed"]

    closed_filter_periods = [p for p in periods if p.status == "closed"]
    filter_closed_ids = {p.period_id for p in closed_filter_periods}

    if all_closed_periods:
        max_closed_start = max(p.period_start for p in all_closed_periods)
        bs_relevant_periods = [p for p in all_periods if p.period_start <= max_closed_start]
    else:
        bs_relevant_periods = []
    bs_relevant_ids = {p.period_id for p in bs_relevant_periods}

    # Balance-sheet figures are cumulative — use all bs-relevant periods up to and
    # including the last closed period in the filter selection so that
    # total_assets / net_worth reflect the actual balance, not just the period's change.
    if closed_filter_periods:
        max_filter_start = max(p.period_start for p in closed_filter_periods)
        bs_period_ids = {p.period_id for p in bs_relevant_periods if p.period_start <= max_filter_start}
    else:
        bs_period_ids = bs_relevant_ids

    rows = await db.execute(
        select(
            JournalLine,
            JournalEntry.period_id,
            JournalEntry.entry_id,
            JournalEntry.is_closing,
            JournalEntry.source_type,
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
    )
    all_rows = rows.all()

    # lines_bs_all     — all closed periods up to last filtered period (balance-sheet KPI totals)
    # lines_bs_by_pid  — all closed periods by period (net-worth series running total)
    # lines_operating  — filtered closed periods, no closing entries (income/expense flow figures)
    lines_bs_all: list[JournalLine] = []
    lines_bs_by_pid: dict = defaultdict(list)
    lines_operating: list[JournalLine] = []
    lines_operating_by_period: dict = defaultdict(list)
    lines_operating_by_entry: dict = defaultdict(list)
    entry_source_type: dict = {}
    for line, pid, entry_id, is_closing, source_type in all_rows:
        if pid in bs_relevant_ids:
            lines_bs_by_pid[pid].append(line)
        if pid in bs_period_ids:
            lines_bs_all.append(line)
        if pid in filter_closed_ids and not is_closing:
            lines_operating.append(line)
            lines_operating_by_period[pid].append(line)
            lines_operating_by_entry[entry_id].append(line)
            entry_source_type[entry_id] = source_type

    # Income/Expense must exclude closing entries — closing entries zero out those
    # accounts by reversing them into equity, so including them cancels everything to zero.
    total_income = _sum_by_type(lines_operating, accounts, "Income", exclude_codes=OCI_ACCOUNT_CODES)
    total_expenses = _sum_by_type(lines_operating, accounts, "Expense")
    net_income = total_income - total_expenses
    oci = sum(
        (line.credit_amount - line.debit_amount for line in lines_operating if line.account_code in OCI_ACCOUNT_CODES),
        _ZERO,
    )
    total_assets = _sum_by_type(lines_bs_all, accounts, "Asset")
    total_liabilities = _sum_by_type(lines_bs_all, accounts, "Liability")
    net_worth = total_assets - total_liabilities

    cash_codes = {code for code, a in accounts.items() if a.account_type == "Asset" and "cash" in a.sub_category.lower()}
    # Take-home lands in true spendable cash (checking/savings). Restricted cash
    # (e.g. an HSA) also matches "cash" but is a pre-tax savings destination, not
    # money you take home — exclude it so it counts as a paystub deduction instead.
    spendable_cash_codes = frozenset(
        code for code, a in accounts.items()
        if a.account_type == "Asset"
        and "cash" in a.sub_category.lower()
        and "restricted" not in a.sub_category.lower()
    )
    wc_codes = {code for code, a in accounts.items() if a.account_type == "Liability" and a.sub_category == "Credit Cards"}
    investing_bucket: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for entry_lines in lines_operating_by_entry.values():
        if not any(ln.account_code in cash_codes for ln in entry_lines):
            continue
        # Opening balance entries credit equity alongside asset debits — exclude them
        # so their starting balances don't distort investing cashflow.
        if any(accounts.get(ln.account_code) and accounts[ln.account_code].account_type == "Equity" for ln in entry_lines):
            continue
        for ln in entry_lines:
            if ln.account_code in cash_codes or ln.account_code in wc_codes:
                continue
            acct = accounts.get(ln.account_code)
            if acct is None or acct.account_type in ("Income", "Expense"):
                continue
            if acct.account_type == "Asset":
                investing_bucket[ln.account_code] += ln.credit_amount - ln.debit_amount
    investing_cashflow = sum(investing_bucket.values(), _ZERO)

    salary_income = sum(
        (ln.credit_amount - ln.debit_amount for ln in lines_operating if ln.account_code == 400101),
        _ZERO,
    )

    # Retirement contributions: only count changes from cash-touching entries so
    # investment value adjustments (which post against Income/Equity, not cash) are excluded.
    retirement_contributions = _ZERO
    for entry_lines in lines_operating_by_entry.values():
        if not any(ln.account_code in cash_codes for ln in entry_lines):
            continue
        if any(accounts.get(ln.account_code) and accounts[ln.account_code].account_type == "Equity" for ln in entry_lines):
            continue
        for ln in entry_lines:
            if ln.account_code in _RETIREMENT_CODES:
                retirement_contributions += ln.debit_amount - ln.credit_amount
    _compensation_codes = {400101, 400102}
    compensation_income = sum(
        (ln.credit_amount - ln.debit_amount for ln in lines_operating if ln.account_code in _compensation_codes),
        _ZERO,
    )

    # YTD per-account retirement contributions. When the caller scopes to a
    # calendar year (the `year` filter the iOS dashboard uses), the progress bars
    # follow that year so every visualization honours the same scope. Otherwise
    # (web from/to range or no filter) they default to the most recent closed
    # year, matching the existing YTD-growth pattern on the frontend.
    if year is not None:
        ytd_year: int | None = year
    elif all_closed_periods:
        ytd_year = max(p.period_start.year for p in all_closed_periods)
    else:
        ytd_year = None
    ytd_contribs_by_code: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    if ytd_year is not None:
        ytd_period_ids = {p.period_id for p in all_closed_periods if p.period_start.year == ytd_year}
        ytd_lines_by_entry: dict = defaultdict(list)
        for line, pid, entry_id, is_closing, _source_type in all_rows:
            if pid in ytd_period_ids and not is_closing:
                ytd_lines_by_entry[entry_id].append(line)
        for entry_lines in ytd_lines_by_entry.values():
            if not any(ln.account_code in cash_codes for ln in entry_lines):
                continue
            if any(accounts.get(ln.account_code) and accounts[ln.account_code].account_type == "Equity" for ln in entry_lines):
                continue
            for ln in entry_lines:
                if ln.account_code in _RETIREMENT_CODES:
                    ytd_contribs_by_code[ln.account_code] += ln.debit_amount - ln.credit_amount
    ytd_retirement_contributions = [
        RetirementContributionPoint(
            account_code=code,
            account_name=accounts[code].account_name if code in accounts else str(code),
            amount=ytd_contribs_by_code.get(code, _ZERO),
        )
        for code in sorted(_RETIREMENT_CODES)
    ]

    lifestyle_expenses = _ZERO
    for ln in lines_operating:
        acct = accounts.get(ln.account_code)
        if acct is None or acct.is_memo or acct.account_type != "Expense":
            continue
        if _is_lifestyle(acct):
            lifestyle_expenses += ln.debit_amount - ln.credit_amount

    # Walk ALL closed periods in chronological order so the running balance-sheet
    # total is always correct. Only emit chart points for periods in the filter.
    period_bars: list[PeriodBar] = []
    running_assets = _ZERO
    running_liabilities = _ZERO
    running_liquid = _ZERO
    running_tax_adv = _ZERO
    running_assets_by_subcat: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    net_worth_series: list[NetWorthPoint] = []
    expense_category_series: list[ExpenseCategorySeriesPoint] = []
    asset_series: list[AssetSeriesPoint] = []
    asset_composition_snapshot: dict[str, Decimal] = {}
    liquid_filter_snapshots: list[Decimal] = []
    tax_adv_filter_snapshots: list[Decimal] = []
    total_assets_filter_snapshots: list[Decimal] = []

    for p in bs_relevant_periods:
        p_bs_lines = lines_bs_by_pid.get(p.period_id, [])
        running_assets += _sum_by_type(p_bs_lines, accounts, "Asset")
        running_liabilities += _sum_by_type(p_bs_lines, accounts, "Liability")

        for ln in p_bs_lines:
            acct = accounts.get(ln.account_code)
            if acct is None or acct.account_type != "Asset" or acct.is_memo:
                continue
            delta = ln.debit_amount - ln.credit_amount
            running_assets_by_subcat[acct.sub_category] += delta
            if acct.account_code in _RETIREMENT_CODES:
                running_tax_adv += delta
            elif acct.sub_category not in _REAL_ESTATE_SUBCATS:
                running_liquid += delta

        if p.period_id in filter_closed_ids:
            liquid_filter_snapshots.append(running_liquid)
            tax_adv_filter_snapshots.append(running_tax_adv)
            total_assets_filter_snapshots.append(running_assets)

        if p.period_id not in filter_closed_ids:
            continue

        p_op_lines = lines_operating_by_period.get(p.period_id, [])
        p_income = _sum_by_type(p_op_lines, accounts, "Income", exclude_codes=OCI_ACCOUNT_CODES)
        p_expenses = _sum_by_type(p_op_lines, accounts, "Expense")
        label = p.period_start.strftime("%b %Y")
        period_bars.append(PeriodBar(
            label=label,
            income=p_income,
            expenses=p_expenses,
            net=p_income - p_expenses,
        ))
        net_worth_series.append(NetWorthPoint(
            label=label,
            net_worth=running_assets - running_liabilities,
        ))

        per_cat: dict[str, Decimal] = defaultdict(lambda: _ZERO)
        for ln in p_op_lines:
            acct = accounts.get(ln.account_code)
            if acct is None or acct.account_type != "Expense" or acct.is_memo:
                continue
            per_cat[acct.sub_category] += ln.debit_amount - ln.credit_amount
        for cat, amt in per_cat.items():
            if amt > _ZERO:
                expense_category_series.append(ExpenseCategorySeriesPoint(
                    period_label=label,
                    category=cat,
                    amount=amt,
                ))

        for subcat, amt in running_assets_by_subcat.items():
            if amt > _ZERO:
                asset_series.append(AssetSeriesPoint(
                    period_label=label,
                    sub_category=subcat,
                    amount=amt,
                ))
        # Composition reflects the latest filter-scope period; overwritten each iteration.
        asset_composition_snapshot = dict(running_assets_by_subcat)

    asset_composition = sorted(
        [
            AssetCompositionPoint(sub_category=k, amount=v)
            for k, v in asset_composition_snapshot.items()
            if v > _ZERO
        ],
        key=lambda c: c.amount,
        reverse=True,
    )

    liquid_assets = liquid_filter_snapshots[-1] if liquid_filter_snapshots else _ZERO
    liquid_assets_prev = liquid_filter_snapshots[-2] if len(liquid_filter_snapshots) >= 2 else _ZERO
    tax_advantaged = tax_adv_filter_snapshots[-1] if tax_adv_filter_snapshots else _ZERO
    tax_advantaged_prev = tax_adv_filter_snapshots[-2] if len(tax_adv_filter_snapshots) >= 2 else _ZERO
    total_assets_prev_val = total_assets_filter_snapshots[-2] if len(total_assets_filter_snapshots) >= 2 else _ZERO

    top_expense_categories = _expense_by_subcategory(lines_operating, accounts)

    # Sources and uses. Built from whole entries only (see _flow_entry_is_excluded)
    # so the three lists balance; income is negated so it reads as a positive source.
    flow_entries = [
        (entry_source_type.get(eid, "manual"), entry_lines)
        for eid, entry_lines in lines_operating_by_entry.items()
        if not _flow_entry_is_excluded(entry_lines, accounts)
    ]
    lines_flow = [line for _source_type, entry_lines in flow_entries for line in entry_lines]
    paycheck_flow = _paycheck_flow(flow_entries, accounts, spendable_cash_codes)
    money_flow = MoneyFlow(
        # Negated (income is credit-normal, so debit − credit is negative), which
        # also reverses _flow_buckets' ordering — re-sort so the largest leads.
        income=sorted(
            [
                MoneyFlowBucket(label=b.label, amount=-b.amount)
                for b in _flow_buckets(lines_flow, accounts, ("Income",))
            ],
            key=lambda b: b.amount,
            reverse=True,
        ),
        expenses=_flow_buckets(lines_flow, accounts, ("Expense",)),
        fund_flows=_flow_buckets(lines_flow, accounts, ("Asset", "Liability")),
    )

    recent_result = await db.execute(
        select(JournalEntry, Period.period_start)
        .join(Period, JournalEntry.period_id == Period.period_id)
        .where(JournalEntry.period_id.in_(filter_closed_ids))
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
        .limit(6)
    )
    period_labels: dict = {p.period_id: p.period_start.strftime("%b %Y") for p in all_closed_periods}

    lines_by_entry: dict = defaultdict(list)
    for line, _period_id, entry_id, _is_closing, _source_type in all_rows:
        lines_by_entry[entry_id].append(line)

    recent_entries: list[RecentEntry] = []
    for entry, _period_start in recent_result.all():
        entry_lines = lines_by_entry.get(entry.entry_id, [])
        total_debit = sum((ln.debit_amount for ln in entry_lines), start=_ZERO)
        recent_entries.append(RecentEntry(
            description=entry.description,
            entry_date=entry.entry_date.strftime("%Y-%m-%d"),
            source_type=entry.source_type,
            period_label=period_labels.get(entry.period_id, ""),
            total_debit=total_debit,
        ))

    has_data = len(lines_bs_all) > 0

    return DashboardData(
        total_income=total_income,
        total_expenses=total_expenses,
        net_income=net_income,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=net_worth,
        investing_cashflow=investing_cashflow,
        salary_income=salary_income,
        retirement_contributions=retirement_contributions,
        compensation_income=compensation_income,
        lifestyle_expenses=lifestyle_expenses,
        oci=oci,
        period_bars=period_bars,
        net_worth_series=net_worth_series,
        top_expense_categories=top_expense_categories,
        money_flow=money_flow,
        paycheck_flow=paycheck_flow,
        expense_category_series=expense_category_series,
        asset_composition=asset_composition,
        asset_series=asset_series,
        recent_entries=recent_entries,
        period_count=len(closed_filter_periods),
        has_data=has_data,
        liquid_assets=liquid_assets,
        liquid_assets_prev=liquid_assets_prev,
        tax_advantaged=tax_advantaged,
        tax_advantaged_prev=tax_advantaged_prev,
        total_assets_prev=total_assets_prev_val,
        ytd_year=ytd_year,
        ytd_retirement_contributions=ytd_retirement_contributions,
    )
