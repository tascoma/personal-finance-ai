"""Tests for the Reconciliation phase — service logic and HTTP routes.

All balance math is deterministic Python. The LLM agent is stubbed for HTTP
route tests so no real API calls are made.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.reconciliation import AccountAnalysis, ReconciliationAnalysis
from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.main import app
from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.reconciliation import Reconciliation
from app.models.stated_balance import StatedBalance
from app.models.user import User
from app.services import journal as journal_service
from app.services import period as period_service
from app.services import reconciliation as recon_service
from app.services import statements as statements_service
from app.services.reconciliation import ReconciliationError

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_ZERO = Decimal("0")


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            Account(account_code=100101, account_name="Checking",
                    account_type="Asset", sub_category="Cash & Cash Equivalents",
                    normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=200101, account_name="Credit Card",
                    account_type="Liability", sub_category="Credit Cards",
                    normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=110101, account_name="EJ – Brokerage",
                    account_type="Asset", sub_category="Investments",
                    normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary",
                    account_type="Income", sub_category="Earned Income",
                    normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=410103, account_name="Unrealized Market Gain/Loss",
                    account_type="Income", sub_category="Investment Income",
                    normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries",
                    account_type="Expense", sub_category="Food",
                    normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=300103, account_name="Current Period Net Income",
                    account_type="Equity", sub_category="Retained Equity",
                    normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=300102, account_name="Prior Period Net Worth",
                    account_type="Equity", sub_category="Retained Equity",
                    normal_balance="credit", is_memo=False, is_active=True),
        ])
        await s.commit()
    yield factory
    await eng.dispose()


async def _make_period(factory, year: int, month: int, target_status: str = "pending_close") -> Period:
    """Create a period and advance it to the desired status."""
    async with factory() as s:
        period = await period_service.create_period(s, year, month)
    status_chain = ["open", "pending_review", "pending_close", "closed"]
    idx = status_chain.index(target_status)
    for next_s in status_chain[1:idx + 1]:
        async with factory() as s:
            period = await period_service.update_status(s, period.period_id, next_s)
    return period


async def _post_journal_lines(
    factory,
    period: Period,
    lines: list[tuple[int, Decimal, Decimal]],
    description: str = "Test entry",
) -> JournalEntry:
    """Post a balanced manual journal entry (debit, credit) tuples."""
    async with factory() as s:
        entry = await journal_service.create_manual_entry(
            s,
            period_id=period.period_id,
            entry_date=period.period_start,
            description=description,
            source_type="adjusting",
            lines=[(code, debit, credit, None) for code, debit, credit in lines],
        )
    return entry


async def _set_stated_balance(factory, period_id: uuid.UUID, account_code: int, amount: Decimal) -> None:
    async with factory() as s:
        sb = StatedBalance(
            period_id=period_id,
            account_code=account_code,
            stated_balance=amount,
        )
        s.add(sb)
        await s.commit()


# ── service tests — balance computation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_beginning_balance_debit_account(session_factory):
    """Prior-period lines aggregate correctly for a debit-normal account."""
    prior = await _make_period(session_factory, 2026, 3)
    current = await _make_period(session_factory, 2026, 4)

    # Prior period: net debit $800 to checking
    await _post_journal_lines(session_factory, prior, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _post_journal_lines(session_factory, prior, [
        (520101, Decimal("200"), _ZERO),
        (100101, _ZERO, Decimal("200")),
    ])

    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("800"))

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert 100101 in result
    assert result[100101]["beginning_balance"] == Decimal("800")
    assert result[100101]["period_net_change"] == _ZERO
    assert result[100101]["computed_balance"] == Decimal("800")


@pytest.mark.asyncio
async def test_net_change_current_period(session_factory):
    """Current-period lines are counted as net change, not beginning."""
    prior = await _make_period(session_factory, 2026, 3)
    current = await _make_period(session_factory, 2026, 4)

    await _post_journal_lines(session_factory, prior, [
        (100101, Decimal("800"), _ZERO),
        (400101, _ZERO, Decimal("800")),
    ])
    # Current period: +$300 inflow to checking
    await _post_journal_lines(session_factory, current, [
        (100101, Decimal("300"), _ZERO),
        (400101, _ZERO, Decimal("300")),
    ])

    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("1100"))

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert result[100101]["beginning_balance"] == Decimal("800")
    assert result[100101]["period_net_change"] == Decimal("300")
    assert result[100101]["computed_balance"] == Decimal("1100")


@pytest.mark.asyncio
async def test_liability_credit_normal_balance(session_factory):
    """Credit-normal account: balance = credit_sum - debit_sum."""
    prior = await _make_period(session_factory, 2026, 3)
    current = await _make_period(session_factory, 2026, 4)

    # Prior period: credit card charged $500, then $100 payment made
    await _post_journal_lines(session_factory, prior, [
        (520101, Decimal("500"), _ZERO),
        (200101, _ZERO, Decimal("500")),   # liability increases (credit)
    ])
    await _post_journal_lines(session_factory, prior, [
        (200101, Decimal("100"), _ZERO),   # payment reduces liability (debit)
        (100101, _ZERO, Decimal("100")),
    ])

    await _set_stated_balance(session_factory, current.period_id, 200101, Decimal("400"))

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert result[200101]["beginning_balance"] == Decimal("400")  # credit - debit = 500-100


@pytest.mark.asyncio
async def test_first_period_beginning_balance_is_zero(session_factory):
    """With no prior periods, beginning balance is zero."""
    current = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("500"))

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert result[100101]["beginning_balance"] == _ZERO


@pytest.mark.asyncio
async def test_is_investment_flag(session_factory):
    """Investment account sub_category sets is_investment=True."""
    current = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("500"))
    await _set_stated_balance(session_factory, current.period_id, 110101, Decimal("10000"))

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert result[100101]["is_investment"] is False
    assert result[110101]["is_investment"] is True


@pytest.mark.asyncio
async def test_no_stated_balances_returns_empty(session_factory):
    """compute_account_balances returns {} when no stated balances exist."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        current_obj = await s.get(Period, current.period_id)
        result = await recon_service.compute_account_balances(s, current_obj)

    assert result == {}


# ── service tests — run_reconciliation ───────────────────────────────────────


@pytest.mark.asyncio
async def test_reconciled_status_when_gap_zero(session_factory):
    """When computed == stated, status is reconciled and gap is 0."""
    current = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, current, [
        (100101, Decimal("1100"), _ZERO),
        (400101, _ZERO, Decimal("1100")),
    ])
    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("1100"))

    async with session_factory() as s:
        rows, _ = await recon_service.run_reconciliation(s, current.period_id)

    assert len(rows) == 1
    assert rows[0].status == "reconciled"
    assert rows[0].gap == _ZERO


@pytest.mark.asyncio
async def test_pending_status_when_gap_nonzero(session_factory):
    """When computed != stated, status is pending and gap reflects the difference."""
    current = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, current, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("1200"))

    async with session_factory() as s:
        rows, _ = await recon_service.run_reconciliation(s, current.period_id)

    assert rows[0].status == "pending"
    assert rows[0].gap == Decimal("200")   # stated - computed = 1200 - 1000


@pytest.mark.asyncio
async def test_run_idempotent(session_factory):
    """Running reconciliation twice produces only one row per account."""
    current = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, current.period_id, 100101, Decimal("0"))

    async with session_factory() as s:
        await recon_service.run_reconciliation(s, current.period_id)
    async with session_factory() as s:
        await recon_service.run_reconciliation(s, current.period_id)

    async with session_factory() as s:
        rows = (await s.scalars(
            select(Reconciliation).where(Reconciliation.period_id == current.period_id)
        )).all()

    assert len(rows) == 1


@pytest.mark.asyncio
async def test_error_on_wrong_status(session_factory):
    """Period must be pending_close; open period raises ReconciliationError."""
    open_p = await _make_period(session_factory, 2026, 4, target_status="open")
    await _set_stated_balance(session_factory, open_p.period_id, 100101, Decimal("0"))

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="pending_close"):
            await recon_service.run_reconciliation(s, open_p.period_id)


@pytest.mark.asyncio
async def test_error_no_stated_balances(session_factory):
    """No stated balances raises ReconciliationError."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="stated balances"):
            await recon_service.run_reconciliation(s, current.period_id)


# ── service tests — unrealized G/L entry ─────────────────────────────────────


@pytest.mark.asyncio
async def test_create_unrealized_gl_entry_market_gain(session_factory):
    """Positive gap (market gained): Debit investment, Credit 410103."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        await recon_service.create_unrealized_gl_entry(
            s, current.period_id, 110101, Decimal("500")
        )

    async with session_factory() as s:
        entries = (await s.scalars(select(JournalEntry))).all()
        assert len(entries) == 1
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entries[0].entry_id)
        )).all()

    by_account = {line.account_code: line for line in lines}
    # Investment account debited (asset increases)
    assert by_account[110101].debit_amount == Decimal("500")
    assert by_account[110101].credit_amount == _ZERO
    # G/L account credited (income)
    assert by_account[410103].credit_amount == Decimal("500")
    assert by_account[410103].debit_amount == _ZERO


@pytest.mark.asyncio
async def test_create_unrealized_gl_entry_market_loss(session_factory):
    """Negative gap (market lost): Debit 410103, Credit investment."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        await recon_service.create_unrealized_gl_entry(
            s, current.period_id, 110101, Decimal("-300")
        )

    async with session_factory() as s:
        lines = (await s.scalars(select(JournalLine))).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[410103].debit_amount == Decimal("300")
    assert by_account[410103].credit_amount == _ZERO
    assert by_account[110101].credit_amount == Decimal("300")
    assert by_account[110101].debit_amount == _ZERO


@pytest.mark.asyncio
async def test_unrealized_gl_closes_gap(session_factory):
    """After posting G/L entry, re-running reconciliation closes the gap."""
    current = await _make_period(session_factory, 2026, 4)
    # Brokerage has no journal entries, but stated balance is $10,000
    await _set_stated_balance(session_factory, current.period_id, 110101, Decimal("10000"))

    # First reconciliation: gap = $10,000 - $0 = $10,000
    async with session_factory() as s:
        rows, _ = await recon_service.run_reconciliation(s, current.period_id)
    assert rows[0].status == "pending"
    assert rows[0].gap == Decimal("10000")

    # Post unrealized G/L entry
    async with session_factory() as s:
        await recon_service.create_unrealized_gl_entry(
            s, current.period_id, 110101, Decimal("10000")
        )

    # Second reconciliation: gap should be 0
    async with session_factory() as s:
        rows, _ = await recon_service.run_reconciliation(s, current.period_id)
    assert rows[0].status == "reconciled"
    assert rows[0].gap == _ZERO


@pytest.mark.asyncio
async def test_unrealized_gl_error_non_investment_account(session_factory):
    """Posting G/L for a non-investment account raises ReconciliationError."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="not an investment account"):
            await recon_service.create_unrealized_gl_entry(
                s, current.period_id, 100101, Decimal("50")
            )


@pytest.mark.asyncio
async def test_unrealized_gl_error_zero_gap(session_factory):
    """Zero gap raises ReconciliationError (no entry needed)."""
    current = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="zero"):
            await recon_service.create_unrealized_gl_entry(
                s, current.period_id, 110101, _ZERO
            )


# ── HTTP route tests ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    async def override_db():
        async with session_factory() as s:
            yield s

    monkeypatch.setattr(
        "app.routes.reconciliation.run_reconciliation_agent",
        AsyncMock(return_value=ReconciliationAnalysis(
            accounts=[
                AccountAnalysis(
                    account_code=100101,
                    likely_causes=["Timing difference"],
                    suggested_actions=["Check outstanding checks"],
                    severity="low",
                )
            ],
            overall_summary="Minor timing difference detected.",
        )),
    )
    async def _mock_user() -> User:
        import uuid
        return User(user_id=uuid.uuid4(), email="test@test.com", hashed_password="", is_active=True)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = _mock_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reconcile_page_renders(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    response = await client.get(f"/api/v1/periods/{period.period_id}/reconcile")
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "details" in data
    assert "ran" in data


@pytest.mark.asyncio
async def test_reconcile_page_empty_before_run(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    response = await client.get(f"/api/v1/periods/{period.period_id}/reconcile")
    assert response.status_code == 200
    data = response.json()
    assert data["ran"] is False
    assert data["details"] == []


@pytest.mark.asyncio
async def test_post_reconcile_creates_rows(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, period.period_id, 100101, Decimal("500"))

    response = await client.post(f"/api/v1/periods/{period.period_id}/reconcile")
    assert response.status_code == 200

    async with session_factory() as s:
        rows = (await s.scalars(
            select(Reconciliation).where(Reconciliation.period_id == period.period_id)
        )).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_post_reconcile_idempotent(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, period.period_id, 100101, Decimal("0"))

    await client.post(f"/api/v1/periods/{period.period_id}/reconcile")
    await client.post(f"/api/v1/periods/{period.period_id}/reconcile")

    async with session_factory() as s:
        rows = (await s.scalars(
            select(Reconciliation).where(Reconciliation.period_id == period.period_id)
        )).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_post_unrealized_creates_journal_entry(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, period.period_id, 110101, Decimal("10000"))
    # Run reconciliation first to create the Reconciliation row
    await client.post(f"/api/v1/periods/{period.period_id}/reconcile")

    response = await client.post(
        f"/api/v1/periods/{period.period_id}/reconcile/post-unrealized",
        json={"account_code": 110101},
    )
    assert response.status_code == 200

    async with session_factory() as s:
        entries = (await s.scalars(select(JournalEntry))).all()
    assert len(entries) == 1
    assert entries[0].source_type == "adjusting"


@pytest.mark.asyncio
async def test_analyze_renders_analysis(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    await _set_stated_balance(session_factory, period.period_id, 100101, Decimal("999"))
    await client.post(f"/api/v1/periods/{period.period_id}/reconcile")

    response = await client.post(f"/api/v1/periods/{period.period_id}/reconcile/analyze")
    assert response.status_code == 200
    data = response.json()
    assert data["analysis"] is not None
    assert "Minor timing difference detected" in data["analysis"]["overall_summary"]


@pytest.mark.asyncio
async def test_analyze_returns_null_analysis_when_no_non_investment_gaps(client, session_factory):
    """If all gaps are in investment accounts, analysis is null (no AI call needed)."""
    period = await _make_period(session_factory, 2026, 4)
    # Only investment account gap
    await _set_stated_balance(session_factory, period.period_id, 110101, Decimal("5000"))
    await client.post(f"/api/v1/periods/{period.period_id}/reconcile")

    response = await client.post(f"/api/v1/periods/{period.period_id}/reconcile/analyze")
    assert response.status_code == 200
    assert response.json()["analysis"] is None


@pytest.mark.asyncio
async def test_close_period_via_status_route(client, session_factory):
    period = await _make_period(session_factory, 2026, 4)
    response = await client.post(
        f"/api/v1/periods/{period.period_id}/status",
        json={"new_status": "closed"},
    )
    assert response.status_code == 200

    async with session_factory() as s:
        updated = await s.get(Period, period.period_id)
    assert updated.status == "closed"


# ── service tests — compute_temp_account_preview ─────────────────────────────


@pytest.mark.asyncio
async def test_compute_temp_preview_returns_accounts(session_factory):
    """Income and expense accounts with period activity appear in the preview."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("300"), _ZERO),
        (100101, _ZERO, Decimal("300")),
    ])

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_temp_account_preview(s, period_obj)

    assert len(preview.income_accounts) == 1
    assert preview.income_accounts[0].account_code == 400101
    assert preview.income_accounts[0].period_balance == Decimal("1000")

    assert len(preview.expense_accounts) == 1
    assert preview.expense_accounts[0].account_code == 520101
    assert preview.expense_accounts[0].period_balance == Decimal("300")

    assert preview.total_income == Decimal("1000")
    assert preview.total_expenses == Decimal("300")
    assert preview.net_income == Decimal("700")
    assert preview.closing_posted is False


@pytest.mark.asyncio
async def test_compute_temp_preview_closing_posted_flag(session_factory):
    """closing_posted is True once an is_closing entry exists for the period."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("500"), _ZERO),
        (400101, _ZERO, Decimal("500")),
    ])

    async with session_factory() as s:
        await journal_service.create_manual_entry(
            s,
            period_id=period.period_id,
            entry_date=period.period_end,
            description="Closing entries",
            source_type="closing",
            lines=[
                (400101, Decimal("500"), _ZERO, "Close income"),
                (300103, _ZERO, Decimal("500"), "Net income to equity"),
            ],
        )

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_temp_account_preview(s, period_obj)

    assert preview.closing_posted is True


@pytest.mark.asyncio
async def test_compute_temp_preview_no_activity(session_factory):
    """No income/expense journal lines → both account lists are empty."""
    period = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_temp_account_preview(s, period_obj)

    assert preview.income_accounts == []
    assert preview.expense_accounts == []
    assert preview.net_income == _ZERO
    assert preview.closing_posted is False


# ── service tests — post_closing_entries ────────────────────────────────────


@pytest.mark.asyncio
async def test_post_closing_entries_profit(session_factory):
    """Income $1000, expense $300 → balanced closing entry; 300103 credited $700."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("300"), _ZERO),
        (100101, _ZERO, Decimal("300")),
    ])

    async with session_factory() as s:
        entry = await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()
        closing_entry = await s.get(JournalEntry, entry.entry_id)

    assert closing_entry.source_type == "closing"
    assert closing_entry.is_closing is True

    by_account = {line.account_code: line for line in lines}
    # Income account debited to zero its credit balance
    assert by_account[400101].debit_amount == Decimal("1000")
    assert by_account[400101].credit_amount == _ZERO
    # Expense account credited to zero its debit balance
    assert by_account[520101].credit_amount == Decimal("300")
    assert by_account[520101].debit_amount == _ZERO
    # Net income account credited for the profit
    assert by_account[300103].credit_amount == Decimal("700")
    assert by_account[300103].debit_amount == _ZERO

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    assert total_debits == total_credits


@pytest.mark.asyncio
async def test_post_closing_entries_net_loss(session_factory):
    """When expenses exceed income, 300103 is debited for the net loss."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("200"), _ZERO),
        (400101, _ZERO, Decimal("200")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("500"), _ZERO),
        (100101, _ZERO, Decimal("500")),
    ])

    async with session_factory() as s:
        entry = await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[300103].debit_amount == Decimal("300")  # net loss
    assert by_account[300103].credit_amount == _ZERO

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    assert total_debits == total_credits


@pytest.mark.asyncio
async def test_post_closing_entries_idempotency(session_factory):
    """Second call raises ReconciliationError about already-posted entries."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("500"), _ZERO),
        (400101, _ZERO, Decimal("500")),
    ])

    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="already posted"):
            await recon_service.post_closing_entries(s, period.period_id)


@pytest.mark.asyncio
async def test_post_closing_entries_wrong_status(session_factory):
    """Period not in pending_close raises ReconciliationError."""
    period = await _make_period(session_factory, 2026, 4, target_status="open")
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("500"), _ZERO),
        (400101, _ZERO, Decimal("500")),
    ])

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="pending_close"):
            await recon_service.post_closing_entries(s, period.period_id)


@pytest.mark.asyncio
async def test_post_closing_entries_no_activity(session_factory):
    """No income/expense lines raises ReconciliationError."""
    period = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="No income or expense activity"):
            await recon_service.post_closing_entries(s, period.period_id)


# ── HTTP route test — post-closing ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_closing_route_creates_entry(client, session_factory):
    """POST /periods/{id}/reconcile/post-closing creates a closing journal entry."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("800"), _ZERO),
        (400101, _ZERO, Decimal("800")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("150"), _ZERO),
        (100101, _ZERO, Decimal("150")),
    ])

    response = await client.post(f"/api/v1/periods/{period.period_id}/reconcile/post-closing")
    assert response.status_code == 200

    async with session_factory() as s:
        entries = (await s.scalars(
            select(JournalEntry).where(
                JournalEntry.period_id == period.period_id,
                JournalEntry.is_closing.is_(True),
            )
        )).all()
    assert len(entries) == 1
    assert entries[0].source_type == "closing"


# ── service tests — compute_equity_rollup_preview ────────────────────────────


@pytest.mark.asyncio
async def test_compute_equity_rollup_preview_after_closing(session_factory):
    """After posting closing entries, 300103 balance appears in the preview."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("600"), _ZERO),
        (400101, _ZERO, Decimal("600")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_equity_rollup_preview(s, period_obj)

    assert preview.net_income_balance == Decimal("600")
    assert preview.rollup_posted is False


@pytest.mark.asyncio
async def test_compute_equity_rollup_preview_rollup_posted_flag(session_factory):
    """rollup_posted is True once the equity rollup entry exists."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("400"), _ZERO),
        (400101, _ZERO, Decimal("400")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)
    async with session_factory() as s:
        await recon_service.post_equity_rollup(s, period.period_id)

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_equity_rollup_preview(s, period_obj)

    assert preview.rollup_posted is True


@pytest.mark.asyncio
async def test_compute_equity_rollup_preview_no_closing_yet(session_factory):
    """Before any closing entries, 300103 balance is zero."""
    period = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        preview = await recon_service.compute_equity_rollup_preview(s, period_obj)

    assert preview.net_income_balance == _ZERO
    assert preview.rollup_posted is False


# ── service tests — post_equity_rollup ───────────────────────────────────────


@pytest.mark.asyncio
async def test_post_equity_rollup_profit(session_factory):
    """Profit: DR 300103, CR 300102 for the net income amount; entry balances."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("200"), _ZERO),
        (100101, _ZERO, Decimal("200")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        entry = await recon_service.post_equity_rollup(s, period.period_id)

    async with session_factory() as s:
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[300103].debit_amount == Decimal("800")
    assert by_account[300103].credit_amount == _ZERO
    assert by_account[300102].credit_amount == Decimal("800")
    assert by_account[300102].debit_amount == _ZERO

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    assert total_debits == total_credits


@pytest.mark.asyncio
async def test_post_equity_rollup_net_loss(session_factory):
    """Net loss: DR 300102, CR 300103."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("100"), _ZERO),
        (400101, _ZERO, Decimal("100")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("500"), _ZERO),
        (100101, _ZERO, Decimal("500")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        entry = await recon_service.post_equity_rollup(s, period.period_id)

    async with session_factory() as s:
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[300102].debit_amount == Decimal("400")   # loss debits equity
    assert by_account[300103].credit_amount == Decimal("400")


@pytest.mark.asyncio
async def test_post_equity_rollup_idempotency(session_factory):
    """Second call raises ReconciliationError about already-posted rollup."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("500"), _ZERO),
        (400101, _ZERO, Decimal("500")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)
    async with session_factory() as s:
        await recon_service.post_equity_rollup(s, period.period_id)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="already posted"):
            await recon_service.post_equity_rollup(s, period.period_id)


@pytest.mark.asyncio
async def test_post_equity_rollup_requires_closing_first(session_factory):
    """Raises if 300103 has no balance (closing entries not yet posted)."""
    period = await _make_period(session_factory, 2026, 4)

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="300103"):
            await recon_service.post_equity_rollup(s, period.period_id)


@pytest.mark.asyncio
async def test_post_equity_rollup_wrong_status(session_factory):
    """Period not in pending_close raises ReconciliationError."""
    period = await _make_period(session_factory, 2026, 4, target_status="open")

    async with session_factory() as s:
        with pytest.raises(ReconciliationError, match="pending_close"):
            await recon_service.post_equity_rollup(s, period.period_id)


@pytest.mark.asyncio
async def test_closing_posted_flag_unaffected_by_equity_rollup(session_factory):
    """closing_posted in temp preview stays True even after equity rollup is posted."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("300"), _ZERO),
        (400101, _ZERO, Decimal("300")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)
    async with session_factory() as s:
        await recon_service.post_equity_rollup(s, period.period_id)

    async with session_factory() as s:
        period_obj = await s.get(Period, period.period_id)
        temp = await recon_service.compute_temp_account_preview(s, period_obj)

    assert temp.closing_posted is True


# ── HTTP route test — post-equity-rollup ─────────────────────────────────────


@pytest.mark.asyncio
async def test_post_equity_rollup_route(client, session_factory):
    """POST /periods/{id}/reconcile/post-equity-rollup creates the rollup entry."""
    period = await _make_period(session_factory, 2026, 4)
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("900"), _ZERO),
        (400101, _ZERO, Decimal("900")),
    ])
    async with session_factory() as s:
        await recon_service.post_closing_entries(s, period.period_id)

    response = await client.post(f"/api/v1/periods/{period.period_id}/reconcile/post-equity-rollup")
    assert response.status_code == 200

    async with session_factory() as s:
        lines = (await s.scalars(
            select(JournalLine).where(JournalLine.account_code == 300102)
        )).all()
    assert len(lines) == 1
    assert lines[0].credit_amount == Decimal("900")


# ── regression: a brand-new account flows through the reports ────────────────


@pytest.mark.asyncio
async def test_new_income_account_aggregates_in_statement_and_closing(session_factory):
    """A freshly added Income account (not pinned anywhere) must aggregate into the
    income statement and get swept into equity by the period close — proving the
    reporting/close paths are account_type-driven, not a hardcoded code list."""
    period = await _make_period(session_factory, 2026, 5)  # pending_close

    # Simulate the user adding "Other Income" via the Add-Account modal: a new
    # Income account with its own code/sub-category, not referenced by any of the
    # curated dashboard KPIs (400101 salary, 400102 comp, 410103 OCI).
    async with session_factory() as s:
        s.add(Account(
            account_code=400107, account_name="Other Income", account_type="Income",
            sub_category="Other Income", normal_balance="credit",
            is_memo=False, is_active=True,
        ))
        await s.commit()

    # Salary $1000 + Other Income $500, less $300 groceries.
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("1000"), _ZERO),
        (400101, _ZERO, Decimal("1000")),
    ])
    await _post_journal_lines(session_factory, period, [
        (100101, Decimal("500"), _ZERO),
        (400107, _ZERO, Decimal("500")),
    ])
    await _post_journal_lines(session_factory, period, [
        (520101, Decimal("300"), _ZERO),
        (100101, _ZERO, Decimal("300")),
    ])

    # 1) Income statement: the new account aggregates into totals and shows as a
    #    line under its own sub-category section.
    async with session_factory() as s:
        inc = await statements_service.compute_income_statement(
            s, [period.period_id], "May 2026"
        )
    assert inc.total_income == Decimal("1500")   # 1000 salary + 500 other income
    assert inc.total_expenses == Decimal("300")
    assert inc.net_income == Decimal("1200")
    other_line = next(
        (ln for sec in inc.income for ln in sec.lines if ln.account_code == 400107),
        None,
    )
    assert other_line is not None, "new income account missing from income statement"
    assert other_line.amount == Decimal("500")
    assert any(sec.label == "Other Income" for sec in inc.income)

    # 2) Period close sweeps the new account into equity (300103).
    async with session_factory() as s:
        entry = await recon_service.post_closing_entries(s, period.period_id)

    async with session_factory() as s:
        closing_lines = (await s.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()
    by_account = {ln.account_code: ln for ln in closing_lines}
    assert 400107 in by_account, "new income account was not closed out"
    assert by_account[400107].debit_amount == Decimal("500")  # zero its credit balance
    assert by_account[400107].credit_amount == _ZERO
    assert by_account[300103].credit_amount == Decimal("1200")  # net income to equity
    assert sum(ln.debit_amount for ln in closing_lines) == sum(
        ln.credit_amount for ln in closing_lines
    )

    # 3) After closing, the new account's net balance is back to zero.
    async with session_factory() as s:
        acct_lines = (await s.scalars(
            select(JournalLine).where(JournalLine.account_code == 400107)
        )).all()
    assert sum(ln.credit_amount - ln.debit_amount for ln in acct_lines) == _ZERO
