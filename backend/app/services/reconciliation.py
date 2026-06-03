"""Reconciliation service.

Deterministic Python math only — no LLM. Computes beginning balances from all
prior-period journal lines, adds the current period's net change, and compares
to user-stated ending balances. Investment accounts (brokerage, retirement,
etc.) are flagged so the UI can offer a one-click Unrealized Market Gain/Loss
adjusting entry rather than treating the gap as a bookkeeping error.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.reconciliation import Reconciliation
from app.models.stated_balance import StatedBalance
from app.schemas.reconciliation import EquityRollupPreview, TempAccountLine, TempAccountPreview
from app.services import journal as journal_service

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

UNREALIZED_GL_ACCOUNT = 410103
NET_INCOME_ACCOUNT = 300103
NET_WORTH_ACCOUNT = 300102

_INVESTMENT_SUBCATEGORIES = frozenset({
    "Investments",
    "Retirement & Tax-Advantaged Accounts",
})


class ReconciliationError(Exception):
    """Raised for invalid reconciliation state."""


def _signed_balance(normal_balance: str, debit_sum: Decimal, credit_sum: Decimal) -> Decimal:
    if normal_balance == "debit":
        return debit_sum - credit_sum
    return credit_sum - debit_sum


async def compute_account_balances(
    db: AsyncSession,
    period: Period,
) -> dict[int, dict]:
    """Compute beginning balance, period net change, and computed ending balance.

    Returns a dict keyed by account_code. Only covers non-memo, active
    Asset/Liability accounts that have a StatedBalance for this period.
    Returns {} if no StatedBalances exist.
    """
    # Round-trip 1: accounts with stated balances for this period
    rows = (await db.execute(
        select(Account, StatedBalance.stated_balance)
        .join(StatedBalance, StatedBalance.account_code == Account.account_code)
        .where(
            StatedBalance.period_id == period.period_id,
            Account.account_type.in_(["Asset", "Liability"]),
            Account.is_memo.is_(False),
            Account.is_active.is_(True),
        )
    )).all()

    if not rows:
        return {}

    account_by_code: dict[int, Account] = {acct.account_code: acct for acct, _ in rows}
    stated_by_code: dict[int, Decimal] = {acct.account_code: stated for acct, stated in rows}
    codes = list(account_by_code.keys())

    # Round-trip 2: prior-period line totals (all periods before this one)
    prior_rows = (await db.execute(
        select(
            JournalLine.account_code,
            func.sum(JournalLine.debit_amount).label("debit_sum"),
            func.sum(JournalLine.credit_amount).label("credit_sum"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .join(Period, Period.period_id == JournalEntry.period_id)
        .where(
            JournalLine.account_code.in_(codes),
            Period.period_start < period.period_start,
        )
        .group_by(JournalLine.account_code)
    )).all()
    prior_totals: dict[int, tuple[Decimal, Decimal]] = {
        r.account_code: (r.debit_sum or _ZERO, r.credit_sum or _ZERO)
        for r in prior_rows
    }

    # Round-trip 3: current-period line totals
    current_rows = (await db.execute(
        select(
            JournalLine.account_code,
            func.sum(JournalLine.debit_amount).label("debit_sum"),
            func.sum(JournalLine.credit_amount).label("credit_sum"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalLine.account_code.in_(codes),
            JournalEntry.period_id == period.period_id,
        )
        .group_by(JournalLine.account_code)
    )).all()
    current_totals: dict[int, tuple[Decimal, Decimal]] = {
        r.account_code: (r.debit_sum or _ZERO, r.credit_sum or _ZERO)
        for r in current_rows
    }

    result: dict[int, dict] = {}
    for code, acct in account_by_code.items():
        nb = acct.normal_balance
        pd, pc = prior_totals.get(code, (_ZERO, _ZERO))
        cd, cc = current_totals.get(code, (_ZERO, _ZERO))
        beginning = _signed_balance(nb, pd, pc)
        net_change = _signed_balance(nb, cd, cc)
        computed = beginning + net_change
        result[code] = {
            "account_name": acct.account_name,
            "normal_balance": nb,
            "sub_category": acct.sub_category,
            "is_investment": acct.sub_category in _INVESTMENT_SUBCATEGORIES,
            "beginning_balance": beginning,
            "period_net_change": net_change,
            "computed_balance": computed,
            "stated_balance": stated_by_code[code],
        }

    return result


async def run_reconciliation(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> tuple[list[Reconciliation], dict[int, dict]]:
    """Compute and persist Reconciliation rows for the given period.

    Idempotent: deletes any existing rows for this period before inserting.
    Raises ReconciliationError if the period is not in pending_close status
    or if no stated balances exist.

    Returns (rows, balances). Callers that need to render a reconciliation
    page can reuse `balances` to avoid recomputing it from scratch.
    """
    period = await db.get(Period, period_id)
    if period is None:
        raise ReconciliationError(f"Period {period_id} not found")
    if period.status not in ("pending_close", "closed"):
        raise ReconciliationError(
            f"Period must be in pending_close or closed status (current: {period.status})"
        )

    balances = await compute_account_balances(db, period)
    if not balances:
        raise ReconciliationError("No stated balances found for this period")

    # Delete existing rows (no unique constraint on model, so delete-then-insert)
    existing = (await db.scalars(
        select(Reconciliation).where(Reconciliation.period_id == period_id)
    )).all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    for code, data in balances.items():
        gap = data["stated_balance"] - data["computed_balance"]
        status = "reconciled" if gap == _ZERO else "pending"
        db.add(Reconciliation(
            period_id=period_id,
            account_code=code,
            computed_balance=data["computed_balance"],
            stated_balance=data["stated_balance"],
            status=status,
        ))

    await db.commit()

    # Single SELECT to repopulate the rows with DB-computed columns (gap, run_at)
    # — replaces an N-roundtrip per-row refresh loop.
    recon_rows = list((await db.scalars(
        select(Reconciliation).where(Reconciliation.period_id == period_id)
    )).all())

    reconciled = sum(1 for r in recon_rows if r.status == "reconciled")
    logger.info(
        "Reconciliation complete for period %s: %d/%d accounts reconciled",
        period_id, reconciled, len(recon_rows),
    )
    return recon_rows, balances


async def create_unrealized_gl_entry(
    db: AsyncSession,
    period_id: uuid.UUID,
    account_code: int,
    gap: Decimal,
) -> None:
    """Post an Unrealized Market Gain/Loss adjusting entry for an investment account.

    gap = stated_balance - computed_balance:
      gap > 0 → market gained: Debit investment, Credit 410103
      gap < 0 → market lost:   Debit 410103,    Credit investment
    """
    if gap == _ZERO:
        raise ReconciliationError("Gap is zero; no adjusting entry needed")

    acct = await db.get(Account, account_code)
    if acct is None:
        raise ReconciliationError(f"Account {account_code} not found")
    if acct.sub_category not in _INVESTMENT_SUBCATEGORIES:
        raise ReconciliationError(
            f"Account {account_code} ({acct.sub_category!r}) is not an investment account"
        )

    gl_acct = await db.get(Account, UNREALIZED_GL_ACCOUNT)
    if gl_acct is None:
        raise ReconciliationError(
            f"Unrealized G/L account {UNREALIZED_GL_ACCOUNT} not found in Chart of Accounts"
        )

    period = await db.get(Period, period_id)
    if period is None:
        raise ReconciliationError(f"Period {period_id} not found")

    abs_gap = abs(gap)
    if gap > _ZERO:
        memo = "Unrealized market gain"
        lines: list[tuple[int, Decimal, Decimal, str | None]] = [
            (account_code,          abs_gap, _ZERO,   memo),
            (UNREALIZED_GL_ACCOUNT, _ZERO,   abs_gap, memo),
        ]
    else:
        memo = "Unrealized market loss"
        lines = [
            (UNREALIZED_GL_ACCOUNT, abs_gap, _ZERO,   memo),
            (account_code,          _ZERO,   abs_gap, memo),
        ]

    await journal_service.create_manual_entry(
        db,
        period_id=period_id,
        entry_date=period.period_end,
        description="Unrealized market gain/loss adjustment",
        source_type="adjusting",
        lines=lines,
    )
    logger.info(
        "Posted unrealized G/L entry for account %d, gap=%s, period=%s",
        account_code, gap, period_id,
    )


async def post_unrealized_gl_targeted(
    db: AsyncSession,
    period_id: uuid.UUID,
    account_code: int,
) -> None:
    """Post unrealized G/L and close the reconciliation gap in one commit.

    Replaces the create_unrealized_gl_entry + run_reconciliation pair for the
    common case of resolving a single investment account gap:
    - Builds the journal entry and lines without committing.
    - Directly patches the one affected Reconciliation row.
    - Issues a single db.commit() (vs. two round trips in the old path).
    """
    acct = await db.get(Account, account_code)
    if acct is None:
        raise ReconciliationError(f"Account {account_code} not found")
    if acct.sub_category not in _INVESTMENT_SUBCATEGORIES:
        raise ReconciliationError(
            f"Account {account_code} ({acct.sub_category!r}) is not an investment account"
        )

    gl_acct = await db.get(Account, UNREALIZED_GL_ACCOUNT)
    if gl_acct is None:
        raise ReconciliationError(
            f"Unrealized G/L account {UNREALIZED_GL_ACCOUNT} not found in Chart of Accounts"
        )

    period = await db.get(Period, period_id)
    if period is None:
        raise ReconciliationError(f"Period {period_id} not found")

    recon_row = await db.scalar(
        select(Reconciliation).where(
            Reconciliation.period_id == period_id,
            Reconciliation.account_code == account_code,
        )
    )
    if recon_row is None:
        raise ReconciliationError(
            f"No reconciliation row found for account {account_code} in this period — "
            "run reconciliation first"
        )

    gap = recon_row.gap
    if gap == _ZERO:
        raise ReconciliationError("Gap is zero; no adjusting entry needed")

    abs_gap = abs(gap)
    if gap > _ZERO:
        memo = "Unrealized market gain"
        debit_code, credit_code = account_code, UNREALIZED_GL_ACCOUNT
    else:
        memo = "Unrealized market loss"
        debit_code, credit_code = UNREALIZED_GL_ACCOUNT, account_code

    eid = uuid.uuid4()
    db.add(JournalEntry(
        entry_id=eid,
        period_id=period_id,
        entry_date=period.period_end,
        description="Unrealized market gain/loss adjustment",
        source_type="adjusting",
        is_adjusting=True,
        is_closing=False,
        created_by="user",
    ))
    db.add(JournalLine(entry_id=eid, account_code=debit_code, debit_amount=abs_gap, credit_amount=_ZERO, memo=memo))
    db.add(JournalLine(entry_id=eid, account_code=credit_code, debit_amount=_ZERO, credit_amount=abs_gap, memo=memo))

    # The entry is sized to close the gap exactly, so computed balance → stated balance.
    recon_row.computed_balance = recon_row.stated_balance
    recon_row.status = "reconciled"

    await db.commit()
    logger.info(
        "Posted unrealized G/L entry for account %d, gap=%s, period=%s",
        account_code, gap, period_id,
    )


async def _fetch_temp_account_totals(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> list[tuple[Account, Decimal, Decimal]]:
    """Return (account, debit_sum, credit_sum) for Income/Expense accounts with period activity.

    Closing entries are excluded so the preview always shows the pre-closing
    operating balances regardless of whether closing has been posted.
    """
    rows = (await db.execute(
        select(
            Account,
            func.sum(JournalLine.debit_amount).label("debit_sum"),
            func.sum(JournalLine.credit_amount).label("credit_sum"),
        )
        .join(JournalLine, JournalLine.account_code == Account.account_code)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period_id,
            JournalEntry.is_closing.is_(False),
            Account.account_type.in_(["Income", "Expense"]),
            Account.is_memo.is_(False),
            Account.is_active.is_(True),
        )
        .group_by(Account.account_code)
        .order_by(Account.account_code)
    )).all()
    return [(row[0], row.debit_sum or _ZERO, row.credit_sum or _ZERO) for row in rows]


async def compute_temp_account_preview(
    db: AsyncSession,
    period: Period,
) -> TempAccountPreview:
    """Compute income/expense account balances for the period.

    Used to preview closing entries: each temp account's period balance shows
    what will be zeroed out when closing entries are posted.
    """
    raw = await _fetch_temp_account_totals(db, period.period_id)

    # Check specifically for a closing entry that touches income/expense accounts
    # (not the equity rollup, which only touches equity accounts).
    closing_entry = await db.scalar(
        select(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.entry_id)
        .join(Account, Account.account_code == JournalLine.account_code)
        .where(
            JournalEntry.period_id == period.period_id,
            JournalEntry.is_closing.is_(True),
            Account.account_type.in_(["Income", "Expense"]),
        )
        .limit(1)
    )
    closing_posted = closing_entry is not None

    income_accounts: list[TempAccountLine] = []
    expense_accounts: list[TempAccountLine] = []

    for acct, debit_sum, credit_sum in raw:
        balance = _signed_balance(acct.normal_balance, debit_sum, credit_sum)
        if not closing_posted and balance == _ZERO:
            continue
        line = TempAccountLine(
            account_code=acct.account_code,
            account_name=acct.account_name,
            account_type=acct.account_type,
            sub_category=acct.sub_category,
            normal_balance=acct.normal_balance,
            period_balance=balance,
        )
        if acct.account_type == "Income":
            income_accounts.append(line)
        else:
            expense_accounts.append(line)

    total_income = _ZERO
    for a in income_accounts:
        if a.normal_balance == "credit":
            total_income += a.period_balance
        else:
            total_income -= a.period_balance

    total_expenses = sum(a.period_balance for a in expense_accounts)
    net_income = total_income - total_expenses

    return TempAccountPreview(
        income_accounts=income_accounts,
        expense_accounts=expense_accounts,
        total_income=total_income,
        total_expenses=total_expenses,
        net_income=net_income,
        closing_posted=closing_posted,
    )


async def post_closing_entries(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> JournalEntry:
    """Post closing entries to zero out all income/expense accounts for the period.

    Debits each credit-normal income account (and credits debit-normal contra-income),
    credits each expense account, and offsets the net to account 300103
    (Current Period Net Income). Raises ReconciliationError if:
    - period not found or not in pending_close
    - closing entries already exist for this period
    - no income/expense activity to close
    """
    period = await db.get(Period, period_id)
    if period is None:
        raise ReconciliationError(f"Period {period_id} not found")
    if period.status not in ("pending_close", "closed"):
        raise ReconciliationError(
            f"Period must be in pending_close or closed status (current: {period.status})"
        )

    existing_closing = await db.scalar(
        select(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.entry_id)
        .join(Account, Account.account_code == JournalLine.account_code)
        .where(
            JournalEntry.period_id == period_id,
            JournalEntry.is_closing.is_(True),
            Account.account_type.in_(["Income", "Expense"]),
        )
        .limit(1)
    )
    if existing_closing is not None:
        raise ReconciliationError("Closing entries already posted for this period")

    net_income_acct = await db.get(Account, NET_INCOME_ACCOUNT)
    if net_income_acct is None:
        raise ReconciliationError(
            f"Account {NET_INCOME_ACCOUNT} not found in Chart of Accounts"
        )

    raw = await _fetch_temp_account_totals(db, period_id)

    lines: list[tuple[int, Decimal, Decimal, str | None]] = []
    net_income = _ZERO

    for acct, debit_sum, credit_sum in raw:
        balance = _signed_balance(acct.normal_balance, debit_sum, credit_sum)
        if balance == _ZERO:
            continue
        amt = abs(balance)
        if acct.account_type == "Income":
            if acct.normal_balance == "credit":
                # Debit to close (credit-normal); flip if balance is reversed
                if balance > _ZERO:
                    lines.append((acct.account_code, amt, _ZERO, "Close income"))
                else:
                    lines.append((acct.account_code, _ZERO, amt, "Close income"))
                net_income += balance
            else:
                # Debit-normal contra-income: credit to close; flip if reversed
                if balance > _ZERO:
                    lines.append((acct.account_code, _ZERO, amt, "Close contra-income"))
                else:
                    lines.append((acct.account_code, amt, _ZERO, "Close contra-income"))
                net_income -= balance
        else:
            # Credit to close expense (debit-normal); flip if balance is reversed
            if balance > _ZERO:
                lines.append((acct.account_code, _ZERO, amt, "Close expense"))
            else:
                lines.append((acct.account_code, amt, _ZERO, "Close expense"))
            net_income -= balance

    if not lines:
        raise ReconciliationError("No income or expense activity to close this period")

    if net_income > _ZERO:
        lines.append((NET_INCOME_ACCOUNT, _ZERO, net_income, "Net income to equity"))
    elif net_income < _ZERO:
        lines.append((NET_INCOME_ACCOUNT, abs(net_income), _ZERO, "Net loss to equity"))

    entry = await journal_service.create_manual_entry(
        db,
        period_id=period_id,
        entry_date=period.period_end,
        description="Closing entries",
        source_type="closing",
        lines=lines,
    )
    logger.info(
        "Posted closing entries for period %s: %d lines, net_income=%s",
        period_id, len(lines), net_income,
    )
    return entry


async def compute_equity_rollup_preview(
    db: AsyncSession,
    period: Period,
) -> EquityRollupPreview:
    """Compute account 300103's current-period balance and whether the rollup has been posted.

    The rollup entry moves the net income balance from 300103 to 300102.
    """
    # Exclude the equity rollup entry (identified by touching NET_WORTH_ACCOUNT) so that
    # the Income Summary preview balance reflects the net income even after rollup is posted.
    rollup_entry_ids = (
        select(JournalLine.entry_id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period.period_id,
            JournalLine.account_code == NET_WORTH_ACCOUNT,
        )
        .scalar_subquery()
    )
    row = (await db.execute(
        select(
            func.sum(JournalLine.debit_amount).label("debit_sum"),
            func.sum(JournalLine.credit_amount).label("credit_sum"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period.period_id,
            JournalLine.account_code == NET_INCOME_ACCOUNT,
            JournalLine.entry_id.not_in(rollup_entry_ids),
        )
    )).first()
    debit_sum = (row.debit_sum or _ZERO) if row else _ZERO
    credit_sum = (row.credit_sum or _ZERO) if row else _ZERO
    net_income_balance = credit_sum - debit_sum  # 300103 is credit-normal

    rollup_posted = await db.scalar(
        select(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period.period_id,
            JournalEntry.is_closing.is_(True),
            JournalLine.account_code == NET_WORTH_ACCOUNT,
        )
        .limit(1)
    ) is not None

    return EquityRollupPreview(
        net_income_balance=net_income_balance,
        rollup_posted=rollup_posted,
    )


async def post_equity_rollup(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> JournalEntry:
    """Roll 300103 (Current Period Net Income) into 300102 (Prior Period Net Worth).

    For profit: Debit 300103, Credit 300102.
    For loss:   Debit 300102, Credit 300103.
    Raises ReconciliationError if period is not pending_close, rollup is already
    posted, or 300103 has no current-period balance to roll over.
    """
    period = await db.get(Period, period_id)
    if period is None:
        raise ReconciliationError(f"Period {period_id} not found")
    if period.status not in ("pending_close", "closed"):
        raise ReconciliationError(
            f"Period must be in pending_close or closed status (current: {period.status})"
        )

    existing_rollup = await db.scalar(
        select(JournalEntry)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period_id,
            JournalEntry.is_closing.is_(True),
            JournalLine.account_code == NET_WORTH_ACCOUNT,
        )
        .limit(1)
    )
    if existing_rollup is not None:
        raise ReconciliationError("Equity rollup already posted for this period")

    for code, label in [(NET_INCOME_ACCOUNT, "300103"), (NET_WORTH_ACCOUNT, "300102")]:
        if await db.get(Account, code) is None:
            raise ReconciliationError(f"Account {label} not found in Chart of Accounts")

    row = (await db.execute(
        select(
            func.sum(JournalLine.debit_amount).label("debit_sum"),
            func.sum(JournalLine.credit_amount).label("credit_sum"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .where(
            JournalEntry.period_id == period_id,
            JournalLine.account_code == NET_INCOME_ACCOUNT,
        )
    )).first()
    debit_sum = (row.debit_sum or _ZERO) if row else _ZERO
    credit_sum = (row.credit_sum or _ZERO) if row else _ZERO
    balance = credit_sum - debit_sum  # positive = profit

    if balance == _ZERO:
        raise ReconciliationError(
            "No net income balance on account 300103 — post closing entries first"
        )

    abs_balance = abs(balance)
    if balance > _ZERO:
        lines: list[tuple[int, Decimal, Decimal, str | None]] = [
            (NET_INCOME_ACCOUNT, abs_balance, _ZERO, "Roll net income to equity"),
            (NET_WORTH_ACCOUNT, _ZERO, abs_balance, "Roll net income to equity"),
        ]
    else:
        lines = [
            (NET_WORTH_ACCOUNT, abs_balance, _ZERO, "Roll net loss to equity"),
            (NET_INCOME_ACCOUNT, _ZERO, abs_balance, "Roll net loss to equity"),
        ]

    entry = await journal_service.create_manual_entry(
        db,
        period_id=period_id,
        entry_date=period.period_end,
        description="Equity rollup — net income to prior period net worth",
        source_type="closing",
        lines=lines,
    )
    logger.info(
        "Posted equity rollup for period %s: balance=%s → 300102",
        period_id, balance,
    )
    return entry
