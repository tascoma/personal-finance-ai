"""Financial-statement computations.

All numbers are derived from posted journal lines — no separate balance table.
Each function returns plain dataclasses so route templates can render without
re-doing arithmetic. Sub-category grouping is preserved so the templates can
render sectioned statements (e.g. Current Assets vs Long-Term Assets).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.stated_balance import StatedBalance

_ZERO = Decimal("0")

# Income accounts presented below Net Income as Other Comprehensive Income.
OCI_ACCOUNT_CODES: frozenset[int] = frozenset({410103})

# Explicit display order for Asset sub-categories on the balance sheet.
# Anything not listed sorts alphabetically after these.
ASSET_SECTION_ORDER: tuple[str, ...] = (
    "Cash & Cash Equivalents",
    "Restricted Cash",
    "Investments",
    "Retirement & Tax-Advantaged Accounts",
    "Real Estate",
)


def _section_sort_key(account_type: str, label: str) -> tuple:
    if account_type == "Asset":
        try:
            return (0, ASSET_SECTION_ORDER.index(label), "")
        except ValueError:
            return (1, 0, label)
    return (0, 0, label)


# ── public dataclasses ──────────────────────────────────────────────────────


@dataclass
class StatementLine:
    account_code: int
    account_name: str
    sub_category: str
    amount: Decimal


@dataclass
class StatementSection:
    label: str
    lines: list[StatementLine] = field(default_factory=list)
    subtotal: Decimal = _ZERO


@dataclass
class BalanceSheet:
    as_of: str
    assets: list[StatementSection]
    liabilities: list[StatementSection]
    equity: list[StatementSection]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


@dataclass
class BalanceSheetPivotRow:
    account_code: int
    account_name: str
    sub_category: str
    balances: list[Decimal]


@dataclass
class BalanceSheetPivotSection:
    label: str
    rows: list[BalanceSheetPivotRow] = field(default_factory=list)
    subtotals: list[Decimal] = field(default_factory=list)


@dataclass
class BalanceSheetPivot:
    periods: list[Period]
    assets: list[BalanceSheetPivotSection]
    liabilities: list[BalanceSheetPivotSection]
    equity: list[BalanceSheetPivotSection]
    off_balance_sheet: list[BalanceSheetPivotSection]
    total_assets: list[Decimal]
    total_liabilities: list[Decimal]
    total_equity: list[Decimal]
    total_off_balance_sheet: list[Decimal]


@dataclass
class IncomeStatement:
    range_label: str
    income: list[StatementSection]
    expenses: list[StatementSection]
    other_comprehensive_income: list[StatementSection]
    total_income: Decimal
    total_expenses: Decimal
    total_oci: Decimal
    net_income: Decimal
    comprehensive_income: Decimal


@dataclass
class CashflowStatement:
    range_label: str
    net_income: Decimal
    noncash_adjustments: list[StatementLine]   # income/expense from non-cash entries, reversed
    working_capital_changes: list[StatementLine]  # changes in credit card balances
    operating_total: Decimal
    investing: list[StatementLine]
    investing_total: Decimal
    financing: list[StatementLine]
    financing_total: Decimal
    net_change_in_cash: Decimal
    cash_by_account: list[StatementLine]
    beginning_cash: Decimal
    ending_cash: Decimal


# ── data loading ─────────────────────────────────────────────────────────────


async def _load_accounts(db: AsyncSession) -> dict[int, Account]:
    result = await db.scalars(select(Account))
    return {a.account_code: a for a in result.all()}


async def _load_lines(
    db: AsyncSession,
    period_ids: list[UUID] | None,
    exclude_closing: bool = False,
) -> list[JournalLine]:
    """Load all journal lines from entries in the given periods (None = all)."""
    stmt = select(JournalLine).join(
        JournalEntry, JournalLine.entry_id == JournalEntry.entry_id
    )
    if period_ids is not None:
        if not period_ids:
            return []
        stmt = stmt.where(JournalEntry.period_id.in_(period_ids))
    if exclude_closing:
        stmt = stmt.where(JournalEntry.is_closing.is_(False))
    result = await db.scalars(stmt)
    return list(result.all())


async def _closed_period_ids(db: AsyncSession, year: int | None = None) -> list[UUID]:
    stmt = select(Period).where(Period.status == "closed")
    result = await db.scalars(stmt)
    periods = result.all()
    if year is not None:
        periods = [p for p in periods if p.period_start.year == year]
    return [p.period_id for p in periods]


async def list_periods_desc(db: AsyncSession) -> list[Period]:
    result = await db.scalars(select(Period).order_by(Period.period_start.desc()))
    return list(result.all())


# ── core math ────────────────────────────────────────────────────────────────


def _account_balance(acct: Account, debit: Decimal, credit: Decimal) -> Decimal:
    """Signed balance using normal-balance convention (always non-negative for healthy books)."""
    if acct.normal_balance == "debit":
        return debit - credit
    return credit - debit


def _group_by_subcategory(
    lines: Iterable[JournalLine],
    accounts: dict[int, Account],
    account_type: str,
) -> tuple[list[StatementSection], Decimal]:
    """Aggregate lines into per-account totals, grouped by sub_category.

    Filters out memo accounts (off-balance-sheet) and zero balances.
    """
    totals: dict[int, tuple[Decimal, Decimal]] = defaultdict(lambda: (_ZERO, _ZERO))
    for line in lines:
        acct = accounts.get(line.account_code)
        if acct is None or acct.account_type != account_type or acct.is_memo:
            continue
        d, c = totals[line.account_code]
        totals[line.account_code] = (d + line.debit_amount, c + line.credit_amount)

    by_sub: dict[str, StatementSection] = {}
    for code, (d, c) in totals.items():
        acct = accounts[code]
        balance = _account_balance(acct, d, c)
        if balance == _ZERO:
            continue
        section = by_sub.setdefault(
            acct.sub_category, StatementSection(label=acct.sub_category)
        )
        section.lines.append(
            StatementLine(
                account_code=code,
                account_name=acct.account_name,
                sub_category=acct.sub_category,
                amount=balance,
            )
        )
        section.subtotal += balance

    sections = sorted(by_sub.values(), key=lambda s: _section_sort_key(account_type, s.label))
    for s in sections:
        s.lines.sort(key=lambda ln: ln.account_code)
    grand_total = sum((s.subtotal for s in sections), _ZERO)
    return sections, grand_total


# ── public computations ──────────────────────────────────────────────────────


async def compute_balance_sheet(
    db: AsyncSession,
    period_ids: list[UUID] | None,
    as_of_label: str,
) -> BalanceSheet:
    """Cumulative balances of permanent accounts through the given periods."""
    accounts = await _load_accounts(db)
    lines = await _load_lines(db, period_ids)

    assets, total_assets = _group_by_subcategory(lines, accounts, "Asset")
    liabilities, total_liabilities = _group_by_subcategory(lines, accounts, "Liability")
    equity, total_equity = _group_by_subcategory(lines, accounts, "Equity")

    return BalanceSheet(
        as_of=as_of_label,
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
    )


def _partition_oci(
    sections: list[StatementSection],
) -> tuple[list[StatementSection], list[StatementSection], Decimal]:
    """Split OCI account lines out of regular income sections.

    Returns (operating_sections, oci_sections, oci_total). Sections that
    become empty after removing OCI lines are dropped.
    """
    operating: list[StatementSection] = []
    oci_by_sub: dict[str, StatementSection] = {}
    oci_total = _ZERO

    for sec in sections:
        op_lines: list[StatementLine] = []
        op_subtotal = _ZERO
        for ln in sec.lines:
            if ln.account_code in OCI_ACCOUNT_CODES:
                bucket = oci_by_sub.setdefault(
                    sec.label, StatementSection(label=sec.label)
                )
                bucket.lines.append(ln)
                bucket.subtotal += ln.amount
                oci_total += ln.amount
            else:
                op_lines.append(ln)
                op_subtotal += ln.amount
        if op_lines:
            operating.append(
                StatementSection(label=sec.label, lines=op_lines, subtotal=op_subtotal)
            )

    oci_sections = sorted(oci_by_sub.values(), key=lambda s: s.label)
    return operating, oci_sections, oci_total


async def compute_income_statement(
    db: AsyncSession,
    period_ids: list[UUID] | None,
    range_label: str,
    year: int | None = None,
) -> IncomeStatement:
    """Income and expenses for the given periods (or closed periods in `year`,
    or all closed periods if both are None).

    Unrealized mark-to-market accounts (see OCI_ACCOUNT_CODES) are partitioned
    out of regular income and reported separately as Other Comprehensive Income
    below Net Income.
    """
    accounts = await _load_accounts(db)
    if period_ids is None:
        period_ids = await _closed_period_ids(db, year=year)
    lines = await _load_lines(db, period_ids, exclude_closing=True)

    income_all, _ = _group_by_subcategory(lines, accounts, "Income")
    income, oci, total_oci = _partition_oci(income_all)
    total_income = sum((s.subtotal for s in income), _ZERO)
    expenses, total_expenses = _group_by_subcategory(lines, accounts, "Expense")

    net_income = total_income - total_expenses
    return IncomeStatement(
        range_label=range_label,
        income=income,
        expenses=expenses,
        other_comprehensive_income=oci,
        total_income=total_income,
        total_expenses=total_expenses,
        total_oci=total_oci,
        net_income=net_income,
        comprehensive_income=net_income + total_oci,
    )


async def compute_balance_sheet_pivot(db: AsyncSession) -> BalanceSheetPivot:
    """Cumulative balance-sheet balances with periods as columns and accounts as rows.

    Memo accounts (is_memo=True) are surfaced separately in the off_balance_sheet
    section, sourced from per-period StatedBalance snapshots (point-in-time, not
    cumulative). They never roll into total_assets/liabilities/equity.
    """
    accounts = await _load_accounts(db)
    # Anchor on the latest closed period, but include any earlier still-open
    # periods as columns too. This keeps bootstrap/seed entries posted to an
    # earlier "opening balances" period rolling into the cumulative columns
    # even if that seed period was never formally closed.
    max_closed_start = (await db.scalars(
        select(func.max(Period.period_start)).where(Period.status == "closed")
    )).first()
    if max_closed_start is None:
        periods: list[Period] = []
    else:
        periods_result = await db.scalars(
            select(Period)
            .where(Period.period_start <= max_closed_start)
            .order_by(Period.period_start.asc())
        )
        periods = list(periods_result.all())

    if not periods:
        return BalanceSheetPivot(
            periods=[],
            assets=[],
            liabilities=[],
            equity=[],
            off_balance_sheet=[],
            total_assets=[],
            total_liabilities=[],
            total_equity=[],
            total_off_balance_sheet=[],
        )

    entries_result = await db.scalars(select(JournalEntry))
    entry_to_period: dict[UUID, UUID] = {e.entry_id: e.period_id for e in entries_result.all()}

    all_lines = await _load_lines(db, None)

    lines_by_period: dict[UUID, list[JournalLine]] = defaultdict(list)
    for line in all_lines:
        pid = entry_to_period.get(line.entry_id)
        if pid is not None:
            lines_by_period[pid].append(line)

    bs_types = {"Asset", "Liability", "Equity"}
    n = len(periods)

    # Accumulate debits and credits cumulatively so each column is point-in-time.
    running_d: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    running_c: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    period_snapshots: list[dict[int, Decimal]] = []

    for period in periods:
        for line in lines_by_period.get(period.period_id, []):
            acct = accounts.get(line.account_code)
            if acct is None or acct.account_type not in bs_types or acct.is_memo:
                continue
            running_d[line.account_code] += line.debit_amount
            running_c[line.account_code] += line.credit_amount

        active_codes = set(running_d.keys()) | set(running_c.keys())
        snap: dict[int, Decimal] = {}
        for code in active_codes:
            acct = accounts.get(code)
            if acct is None:
                continue
            snap[code] = _account_balance(acct, running_d.get(code, _ZERO), running_c.get(code, _ZERO))
        period_snapshots.append(snap)

    all_codes: set[int] = set()
    for snap in period_snapshots:
        all_codes.update(snap.keys())

    def _build_pivot_sections(
        account_type: str,
    ) -> tuple[list[BalanceSheetPivotSection], list[Decimal]]:
        codes = sorted(c for c in all_codes if accounts[c].account_type == account_type)

        by_sub: dict[str, list[int]] = defaultdict(list)
        for code in codes:
            by_sub[accounts[code].sub_category].append(code)

        grand_totals: list[Decimal] = [_ZERO] * n
        sections: list[BalanceSheetPivotSection] = []

        for sub_label in sorted(
            by_sub.keys(), key=lambda label: _section_sort_key(account_type, label)
        ):
            rows: list[BalanceSheetPivotRow] = []
            sub_totals: list[Decimal] = [_ZERO] * n

            for code in sorted(by_sub[sub_label]):
                balances = [snap.get(code, _ZERO) for snap in period_snapshots]
                if not any(balances):
                    continue
                rows.append(BalanceSheetPivotRow(
                    account_code=code,
                    account_name=accounts[code].account_name,
                    sub_category=sub_label,
                    balances=balances,
                ))
                for i, b in enumerate(balances):
                    sub_totals[i] += b

            if rows:
                sections.append(BalanceSheetPivotSection(
                    label=sub_label,
                    rows=rows,
                    subtotals=sub_totals,
                ))
                for i, st in enumerate(sub_totals):
                    grand_totals[i] += st

        return sections, grand_totals

    assets, total_assets = _build_pivot_sections("Asset")
    liabilities, total_liabilities = _build_pivot_sections("Liability")
    equity, total_equity = _build_pivot_sections("Equity")

    off_bs, total_off_bs = await _build_off_balance_sheet_pivot(db, accounts, periods)

    return BalanceSheetPivot(
        periods=periods,
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        off_balance_sheet=off_bs,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
        total_off_balance_sheet=total_off_bs,
    )


async def _build_off_balance_sheet_pivot(
    db: AsyncSession,
    accounts: dict[int, Account],
    periods: list[Period],
) -> tuple[list[BalanceSheetPivotSection], list[Decimal]]:
    """Pivot StatedBalance snapshots for memo accounts across the given periods."""
    memo_codes = [code for code, a in accounts.items() if a.is_memo]
    if not memo_codes:
        return [], [_ZERO] * len(periods)

    period_ids = [p.period_id for p in periods]
    rows = (await db.execute(
        select(StatedBalance.period_id, StatedBalance.account_code, StatedBalance.stated_balance)
        .where(
            StatedBalance.account_code.in_(memo_codes),
            StatedBalance.period_id.in_(period_ids),
        )
    )).all()

    # balances[code][period_index] = stated balance for that snapshot
    period_index = {pid: i for i, pid in enumerate(period_ids)}
    balances: dict[int, list[Decimal]] = defaultdict(lambda: [_ZERO] * len(periods))
    for pid, code, amount in rows:
        balances[code][period_index[pid]] = amount

    by_sub: dict[str, list[int]] = defaultdict(list)
    for code in balances.keys():
        by_sub[accounts[code].sub_category].append(code)

    grand_totals: list[Decimal] = [_ZERO] * len(periods)
    sections: list[BalanceSheetPivotSection] = []
    for sub_label in sorted(by_sub.keys()):
        rows_out: list[BalanceSheetPivotRow] = []
        sub_totals: list[Decimal] = [_ZERO] * len(periods)
        for code in sorted(by_sub[sub_label]):
            bals = balances[code]
            if not any(bals):
                continue
            rows_out.append(BalanceSheetPivotRow(
                account_code=code,
                account_name=accounts[code].account_name,
                sub_category=sub_label,
                balances=bals,
            ))
            for i, b in enumerate(bals):
                sub_totals[i] += b
        if rows_out:
            sections.append(BalanceSheetPivotSection(
                label=sub_label,
                rows=rows_out,
                subtotals=sub_totals,
            ))
            for i, st in enumerate(sub_totals):
                grand_totals[i] += st

    return sections, grand_totals


def _is_cash_account(acct: Account) -> bool:
    return acct.account_type == "Asset" and "cash" in acct.sub_category.lower()


async def _beginning_cash(
    db: AsyncSession,
    accounts: dict[int, Account],
    period_ids: list[UUID],
) -> Decimal:
    """Sum of cash-account net changes from all closed periods ending before the selected period starts."""
    earliest_start_result = await db.scalars(
        select(Period.period_start)
        .where(Period.period_id.in_(period_ids))
        .order_by(Period.period_start)
        .limit(1)
    )
    earliest_start = earliest_start_result.first()
    if earliest_start is None:
        return _ZERO

    prior_id_result = await db.scalars(
        select(Period.period_id)
        .where(Period.status == "closed")
        .where(Period.period_end < earliest_start)
    )
    prior_ids = list(prior_id_result.all())
    if not prior_ids:
        return _ZERO

    prior_lines = await _load_lines(db, prior_ids, exclude_closing=True)
    cash_codes = {code for code, a in accounts.items() if _is_cash_account(a)}
    return sum(
        (ln.debit_amount - ln.credit_amount for ln in prior_lines if ln.account_code in cash_codes),
        _ZERO,
    )


def _is_working_capital_account(acct: Account) -> bool:
    # Credit cards are the only current operating liability in this chart of accounts.
    return acct.account_type == "Liability" and acct.sub_category == "Credit Cards"


async def compute_cashflow(
    db: AsyncSession,
    period_ids: list[UUID] | None,
    range_label: str,
    year: int | None = None,
) -> CashflowStatement:
    """Indirect-method cash flow for the given periods (or closed periods in
    `year`, or all closed periods since inception if both are None).

    Operating section: net income adjusted for (a) non-cash income/expense items
    (e.g. RSU vesting, unrealized gains) and (b) changes in credit card balances.
    Investing and financing sections cover direct cash flows to/from long-term
    asset and liability/equity accounts respectively.
    """
    accounts = await _load_accounts(db)
    # True "since inception" aggregates start beginning cash at zero (nothing to
    # roll forward from); a year-scoped aggregate rolls forward from the real
    # balance as of the start of that year, computed below via _beginning_cash.
    all_periods = period_ids is None and year is None
    if period_ids is None:
        period_ids = await _closed_period_ids(db, year=year)
    lines = await _load_lines(db, period_ids, exclude_closing=True)

    cash_codes = {code for code, a in accounts.items() if _is_cash_account(a)}
    wc_codes = {code for code, a in accounts.items() if _is_working_capital_account(a)}

    lines_by_entry: dict[UUID, list[JournalLine]] = defaultdict(list)
    for line in lines:
        lines_by_entry[line.entry_id].append(line)

    # Net income: all income/expense period activity, excluding OCI accounts
    # (those are reported separately on the income statement, below Net Income).
    # For income (normal credit): credit - debit = positive contribution.
    # For expense (normal debit): credit - debit = negative contribution.
    net_income = sum(
        line.credit_amount - line.debit_amount
        for line in lines
        if (a := accounts.get(line.account_code)) is not None
        and a.account_type in ("Income", "Expense")
        and line.account_code not in OCI_ACCOUNT_CODES
    )

    # Non-cash adjustments: entries with no cash and no working-capital lines whose
    # income/expense amounts are included in net income but represent no cash movement.
    # Reversed sign: -(credit - debit) = debit - credit. OCI accounts are excluded
    # because they were never added to net_income above.
    noncash: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for entry_lines in lines_by_entry.values():
        if any(ln.account_code in cash_codes for ln in entry_lines):
            continue
        if any(ln.account_code in wc_codes for ln in entry_lines):
            continue
        for ln in entry_lines:
            acct = accounts.get(ln.account_code)
            if acct is None or acct.account_type not in ("Income", "Expense"):
                continue
            if ln.account_code in OCI_ACCOUNT_CODES:
                continue
            noncash[ln.account_code] += ln.debit_amount - ln.credit_amount

    # Working capital changes: net change in credit card balances across all period
    # entries. Increase in liability = source of operating cash (positive).
    wc: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for line in lines:
        if line.account_code in wc_codes:
            wc[line.account_code] += line.credit_amount - line.debit_amount

    # Investing: cash-touching entries, non-cash asset accounts (excludes income/expense
    # and working-capital accounts).
    # Financing: cash-touching entries, long-term liability and equity accounts.
    investing: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    financing: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    cash_change: dict[int, Decimal] = defaultdict(lambda: _ZERO)

    for entry_lines in lines_by_entry.values():
        has_cash = any(ln.account_code in cash_codes for ln in entry_lines)
        if not has_cash:
            continue
        for ln in entry_lines:
            if ln.account_code in cash_codes:
                cash_change[ln.account_code] += ln.debit_amount - ln.credit_amount
                continue
            if ln.account_code in wc_codes:
                continue  # captured in working capital section
            acct = accounts.get(ln.account_code)
            if acct is None or acct.account_type in ("Income", "Expense"):
                continue  # captured in net income
            contribution = ln.credit_amount - ln.debit_amount
            if acct.account_type == "Asset":
                investing[ln.account_code] += contribution
            elif acct.account_type in ("Liability", "Equity"):
                financing[ln.account_code] += contribution

    def _to_lines(bucket: dict[int, Decimal]) -> tuple[list[StatementLine], Decimal]:
        out: list[StatementLine] = []
        total = _ZERO
        for code, amt in bucket.items():
            if amt == _ZERO:
                continue
            acct = accounts[code]
            out.append(StatementLine(
                account_code=code,
                account_name=acct.account_name,
                sub_category=acct.sub_category,
                amount=amt,
            ))
            total += amt
        out.sort(key=lambda ln: ln.account_code)
        return out, total

    noncash_lines, noncash_total = _to_lines(noncash)
    wc_lines, wc_total = _to_lines(wc)
    inv_lines, inv_total = _to_lines(investing)
    fin_lines, fin_total = _to_lines(financing)

    cash_by_account = [
        StatementLine(
            account_code=code,
            account_name=accounts[code].account_name,
            sub_category=accounts[code].sub_category,
            amount=amt,
        )
        for code, amt in sorted(cash_change.items())
        if amt != _ZERO
    ]
    net_change = sum((ln.amount for ln in cash_by_account), _ZERO)
    operating_total = net_income + noncash_total + wc_total
    beg_cash = _ZERO if all_periods else await _beginning_cash(db, accounts, period_ids)
    end_cash = beg_cash + net_change

    return CashflowStatement(
        range_label=range_label,
        net_income=net_income,
        noncash_adjustments=noncash_lines,
        working_capital_changes=wc_lines,
        operating_total=operating_total,
        investing=inv_lines,
        investing_total=inv_total,
        financing=fin_lines,
        financing_total=fin_total,
        net_change_in_cash=net_change,
        cash_by_account=cash_by_account,
        beginning_cash=beg_cash,
        ending_cash=end_cash,
    )
