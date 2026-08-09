"""Tests for the /dashboard route.

Empty/active-period coverage exists in test_periods.py — these focus on the
aggregation paths once journal entries are present.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.main import app
from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.user import User

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    async def _mock_user() -> User:
        return User(user_id=uuid.uuid4(), email="test@test.com", hashed_password="", is_active=True)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = _mock_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def closed_period_with_entries(session_factory):
    """Seed one closed period with a salary deposit and a grocery expense.

    Returns (period_id, year).
    """
    async with session_factory() as session:
        period = Period(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status="closed",
            closed_at=datetime(2026, 2, 1),
        )
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=600101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()

        salary_entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=period.period_id,
            entry_date=date(2026, 1, 15),
            description="Paycheck",
            source_type="manual",
        )
        grocery_entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=period.period_id,
            entry_date=date(2026, 1, 20),
            description="Whole Foods",
            source_type="manual",
        )
        session.add_all([salary_entry, grocery_entry])
        await session.flush()

        session.add_all([
            JournalLine(line_id=uuid.uuid4(), entry_id=salary_entry.entry_id,
                        account_code=100101, debit_amount=Decimal("3000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=salary_entry.entry_id,
                        account_code=400101, debit_amount=Decimal("0"), credit_amount=Decimal("3000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=grocery_entry.entry_id,
                        account_code=600101, debit_amount=Decimal("125"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=grocery_entry.entry_id,
                        account_code=100101, debit_amount=Decimal("0"), credit_amount=Decimal("125")),
        ])
        await session.commit()

        return period.period_id, 2026


@pytest.mark.asyncio
async def test_dashboard_empty_returns_no_data(client: AsyncClient):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["has_data"] is False
    assert body["active_period"] is None
    assert body["period_bars"] == []
    assert body["net_worth_series"] == []
    assert body["top_expense_categories"] == []


@pytest.mark.asyncio
async def test_dashboard_aggregates_closed_period_entries(
    client: AsyncClient, closed_period_with_entries
):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert body["has_data"] is True
    assert Decimal(body["total_income"]) == Decimal("3000.00")
    assert Decimal(body["total_expenses"]) == Decimal("125.00")
    assert Decimal(body["net_income"]) == Decimal("2875.00")
    assert Decimal(body["total_assets"]) == Decimal("2875.00")  # 3000 - 125 in checking
    assert Decimal(body["net_worth"]) == Decimal("2875.00")
    assert body["period_count"] == 1
    assert len(body["period_bars"]) == 1
    # top_expense_categories aggregates by sub_category, not account_name
    assert body["top_expense_categories"][0]["category"] == "Food"
    assert Decimal(body["top_expense_categories"][0]["amount"]) == Decimal("125.00")


@pytest.mark.asyncio
async def test_dashboard_year_filter(client: AsyncClient, closed_period_with_entries):
    _, year = closed_period_with_entries

    in_year = await client.get("/api/v1/dashboard", params={"year": year})
    assert Decimal(in_year.json()["total_income"]) == Decimal("3000.00")

    # Filtering to a year with no closed periods zeroes out income but
    # has_data stays true because the underlying balance-sheet lines exist.
    other = await client.get("/api/v1/dashboard", params={"year": year + 5})
    assert other.status_code == 200
    assert Decimal(other.json()["total_income"]) == Decimal("0")
    assert other.json()["period_bars"] == []


@pytest.mark.asyncio
async def test_dashboard_unknown_period_filter_returns_empty_aggregates(
    client: AsyncClient, closed_period_with_entries
):
    bogus = uuid.uuid4()
    response = await client.get("/api/v1/dashboard", params={"period_id": str(bogus)})
    assert response.status_code == 200
    assert Decimal(response.json()["total_income"]) == Decimal("0")
    assert response.json()["period_bars"] == []


@pytest_asyncio.fixture
async def closed_period_with_lifestyle(session_factory):
    """Seed one closed period with salary + bonus, groceries, travel, and dining out.

    Travel (sub_category="Lifestyle") and Dining Out (acct 520102) should both
    count as lifestyle; Groceries should not.
    """
    async with session_factory() as session:
        period = Period(
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            status="closed",
            closed_at=datetime(2026, 3, 1),
        )
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400102, account_name="Bonus", account_type="Income",
                    sub_category="Variable Compensation", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=520102, account_name="Dining Out", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=550101, account_name="Travel", account_type="Expense",
                    sub_category="Lifestyle", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()

        entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=period.period_id,
            entry_date=date(2026, 2, 15),
            description="Period activity",
            source_type="manual",
        )
        session.add(entry)
        await session.flush()

        session.add_all([
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=100101, debit_amount=Decimal("8400"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=400101, debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=400102, debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=520101, debit_amount=Decimal("400"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=520102, debit_amount=Decimal("200"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=550101, debit_amount=Decimal("1000"), credit_amount=Decimal("0")),
        ])
        await session.commit()

        return period.period_id


@pytest.mark.asyncio
async def test_dashboard_lifestyle_and_category_series(
    client: AsyncClient, closed_period_with_lifestyle
):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    # Travel (1000) + Dining Out (200); Groceries excluded.
    assert Decimal(body["lifestyle_expenses"]) == Decimal("1200.00")
    assert Decimal(body["compensation_income"]) == Decimal("10000.00")

    series = body["expense_category_series"]
    by_cat = {row["category"]: Decimal(row["amount"]) for row in series}
    # Food = Groceries (400) + Dining Out (200); Lifestyle = Travel (1000).
    assert by_cat["Food"] == Decimal("600.00")
    assert by_cat["Lifestyle"] == Decimal("1000.00")
    assert all(row["period_label"] == "Feb 2026" for row in series)


@pytest_asyncio.fixture
async def two_closed_periods_with_assets(session_factory):
    """Seed two closed periods with Cash + Brokerage assets and one memo asset.

    Period 1 (Jan 2026): +1000 Cash, +500 Brokerage, +200 memo.
    Period 2 (Feb 2026): +300 Cash, +700 Brokerage.

    Memo asset should never appear in asset_composition or asset_series.
    """
    async with session_factory() as session:
        p1 = Period(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status="closed",
            closed_at=datetime(2026, 2, 1),
        )
        p2 = Period(
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            status="closed",
            closed_at=datetime(2026, 3, 1),
        )
        session.add_all([p1, p2])
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=111101, account_name="Brokerage", account_type="Asset",
                    sub_category="Brokerage", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=199101, account_name="Future Vehicle", account_type="Asset",
                    sub_category="Memo Vehicles", normal_balance="debit", is_memo=True, is_active=True),
            Account(account_code=300101, account_name="Opening Equity", account_type="Equity",
                    sub_category="Equity", normal_balance="credit", is_memo=False, is_active=True),
        ])
        await session.flush()

        def add_entry(period_id, entry_date, lines):
            entry = JournalEntry(
                entry_id=uuid.uuid4(),
                period_id=period_id,
                entry_date=entry_date,
                description="seed",
                source_type="manual",
            )
            session.add(entry)
            return entry

        e1 = add_entry(p1.period_id, date(2026, 1, 15), None)
        e2 = add_entry(p2.period_id, date(2026, 2, 15), None)
        await session.flush()

        session.add_all([
            # Period 1 — Cash +1000, Brokerage +500, Memo +200 (offset by Equity)
            JournalLine(line_id=uuid.uuid4(), entry_id=e1.entry_id,
                        account_code=100101, debit_amount=Decimal("1000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=e1.entry_id,
                        account_code=111101, debit_amount=Decimal("500"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=e1.entry_id,
                        account_code=199101, debit_amount=Decimal("200"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=e1.entry_id,
                        account_code=300101, debit_amount=Decimal("0"), credit_amount=Decimal("1700")),
            # Period 2 — Cash +300, Brokerage +700 (offset by Equity)
            JournalLine(line_id=uuid.uuid4(), entry_id=e2.entry_id,
                        account_code=100101, debit_amount=Decimal("300"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=e2.entry_id,
                        account_code=111101, debit_amount=Decimal("700"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=e2.entry_id,
                        account_code=300101, debit_amount=Decimal("0"), credit_amount=Decimal("1000")),
        ])
        await session.commit()
        return p1.period_id, p2.period_id


@pytest.mark.asyncio
async def test_dashboard_asset_composition_excludes_memo(
    client: AsyncClient, two_closed_periods_with_assets
):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    comp = body["asset_composition"]
    by_subcat = {row["sub_category"]: Decimal(row["amount"]) for row in comp}

    # Cumulative through Feb: Cash 1300, Brokerage 1200.
    assert by_subcat == {
        "Cash": Decimal("1300.00"),
        "Brokerage": Decimal("1200.00"),
    }
    assert "Memo Vehicles" not in by_subcat
    # Sorted descending by amount.
    assert comp[0]["sub_category"] == "Cash"


@pytest.mark.asyncio
async def test_dashboard_asset_series_per_period_per_subcat(
    client: AsyncClient, two_closed_periods_with_assets
):
    response = await client.get("/api/v1/dashboard")
    body = response.json()

    series = body["asset_series"]
    # Two periods × two non-memo sub_categories = 4 points; memo excluded.
    assert len(series) == 4
    indexed = {(r["period_label"], r["sub_category"]): Decimal(r["amount"]) for r in series}
    assert indexed[("Jan 2026", "Cash")] == Decimal("1000.00")
    assert indexed[("Jan 2026", "Brokerage")] == Decimal("500.00")
    assert indexed[("Feb 2026", "Cash")] == Decimal("1300.00")
    assert indexed[("Feb 2026", "Brokerage")] == Decimal("1200.00")
    assert not any(r["sub_category"] == "Memo Vehicles" for r in series)


@pytest_asyncio.fixture
async def open_seed_then_closed_period(session_factory):
    """Open seed period (Mar) with an opening-balance entry, then closed Apr.

    Mar opening: Checking +5000 (debit), offset by Equity. Period left status='open'.
    Apr closed: paycheck +3000 to Checking, no expenses.

    The seed period is never formally closed, but its entries must still
    roll into later cumulative balance-sheet figures.
    """
    async with session_factory() as session:
        seed = Period(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            status="open",
        )
        closed = Period(
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            status="closed",
            closed_at=datetime(2026, 5, 1),
        )
        session.add_all([seed, closed])
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=300101, account_name="Opening Equity", account_type="Equity",
                    sub_category="Equity", normal_balance="credit", is_memo=False, is_active=True),
        ])
        await session.flush()

        seed_entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=seed.period_id,
            entry_date=date(2026, 3, 31),
            description="Opening balances",
            source_type="adjusting",
        )
        apr_entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=closed.period_id,
            entry_date=date(2026, 4, 15),
            description="Paycheck",
            source_type="manual",
        )
        session.add_all([seed_entry, apr_entry])
        await session.flush()

        session.add_all([
            JournalLine(line_id=uuid.uuid4(), entry_id=seed_entry.entry_id,
                        account_code=100101, debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=seed_entry.entry_id,
                        account_code=300101, debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=apr_entry.entry_id,
                        account_code=100101, debit_amount=Decimal("3000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=apr_entry.entry_id,
                        account_code=400101, debit_amount=Decimal("0"), credit_amount=Decimal("3000")),
        ])
        await session.commit()
        return seed.period_id, closed.period_id


@pytest.mark.asyncio
async def test_dashboard_includes_open_seed_period_in_balance_sheet(
    client: AsyncClient, open_seed_then_closed_period
):
    response = await client.get("/api/v1/dashboard")
    body = response.json()

    # Cumulative through Apr = 5000 (seed) + 3000 (paycheck) = 8000 Cash.
    assert Decimal(body["total_assets"]) == Decimal("8000.00")
    assert Decimal(body["liquid_assets"]) == Decimal("8000.00")
    # Operating income for Apr stays scoped to Apr — seed doesn't pollute it.
    assert Decimal(body["total_income"]) == Decimal("3000.00")


@pytest_asyncio.fixture
async def closed_period_with_mixed_income(session_factory):
    """Seed a closed period exercising every income edge case.

    Earned Income 6000, Variable Compensation 2000, and an Investment Income
    bucket holding a realized gain (1500) net of a debit-normal capital loss
    (500). Account 410103 is OCI and must not appear as a source at all.
    """
    async with session_factory() as session:
        period = Period(
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status="closed",
            closed_at=datetime(2026, 7, 1),
        )
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400102, account_name="Bonus", account_type="Income",
                    sub_category="Variable Compensation", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=410101, account_name="Capital Gains", account_type="Income",
                    sub_category="Investment Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=410102, account_name="Capital Losses", account_type="Income",
                    sub_category="Investment Income", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=410103, account_name="Unrealized Gain/Loss", account_type="Income",
                    sub_category="Investment Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=110101, account_name="Brokerage", account_type="Asset",
                    sub_category="Investments", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()

        entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=period.period_id,
            entry_date=date(2026, 6, 15),
            description="Period activity",
            source_type="manual",
        )
        # Unrealized marks post as their own standalone entry, matching production.
        # Keeping them out of the activity entry matters: the money-flow model drops
        # OCI-touching entries whole, which would take the real income with them.
        oci_entry = JournalEntry(
            entry_id=uuid.uuid4(),
            period_id=period.period_id,
            entry_date=date(2026, 6, 30),
            description="Unrealized market gain/loss adjustment",
            source_type="adjusting",
        )
        session.add_all([entry, oci_entry])
        await session.flush()

        session.add_all([
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=100101, debit_amount=Decimal("9000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=400101, debit_amount=Decimal("0"), credit_amount=Decimal("6000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=400102, debit_amount=Decimal("0"), credit_amount=Decimal("2000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=410101, debit_amount=Decimal("0"), credit_amount=Decimal("1500")),
            JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id,
                        account_code=410102, debit_amount=Decimal("500"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=oci_entry.entry_id,
                        account_code=110101, debit_amount=Decimal("900"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=oci_entry.entry_id,
                        account_code=410103, debit_amount=Decimal("0"), credit_amount=Decimal("900")),
        ])
        await session.commit()

        return period.period_id


def _buckets(section: list[dict]) -> dict[str, Decimal]:
    return {b["category"]: Decimal(b["amount"]) for b in section}


@pytest.mark.asyncio
async def test_money_flow_income_grouped_and_sorted(
    client: AsyncClient, closed_period_with_mixed_income
):
    body = (await client.get("/api/v1/dashboard")).json()
    income = body["money_flow"]["income"]

    assert [b["category"] for b in income] == [
        "Earned Income",
        "Variable Compensation",
        "Investment Income",
    ]
    amounts = [Decimal(b["amount"]) for b in income]
    assert amounts == sorted(amounts, reverse=True)


@pytest.mark.asyncio
async def test_money_flow_income_sums_to_total_income(
    client: AsyncClient, closed_period_with_mixed_income
):
    """Also proves the excluded OCI entry carried no real income."""
    body = (await client.get("/api/v1/dashboard")).json()
    total = sum(Decimal(b["amount"]) for b in body["money_flow"]["income"])
    assert total == Decimal(body["total_income"]) == Decimal("9000.00")


@pytest.mark.asyncio
async def test_money_flow_excludes_oci_entry_whole(
    client: AsyncClient, closed_period_with_mixed_income
):
    body = (await client.get("/api/v1/dashboard")).json()
    flow = body["money_flow"]

    # The 900 unrealized gain is still reported as OCI...
    assert Decimal(body["oci"]) == Decimal("900.00")
    # ...but neither its income leg nor its paired asset debit reaches the flow.
    assert _buckets(flow["income"])["Investment Income"] == Decimal("1000.00")
    assert "Investments" not in _buckets(flow["fund_flows"])


@pytest.mark.asyncio
async def test_money_flow_nets_contra_income(
    client: AsyncClient, closed_period_with_mixed_income
):
    body = (await client.get("/api/v1/dashboard")).json()

    # Realized gain 1500 less the debit-normal capital loss 500 — not 2000.
    assert _buckets(body["money_flow"]["income"])["Investment Income"] == Decimal("1000.00")


@pytest.mark.asyncio
async def test_money_flow_empty_without_activity(client: AsyncClient):
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["money_flow"] == {"income": [], "expenses": [], "fund_flows": []}


@pytest.mark.asyncio
async def test_money_flow_scoped_by_year(
    client: AsyncClient, closed_period_with_entries
):
    _period_id, year = closed_period_with_entries

    flow = (await client.get(f"/api/v1/dashboard?year={year}")).json()["money_flow"]
    assert [b["category"] for b in flow["income"]] == ["Earned"]
    assert Decimal(flow["income"][0]["amount"]) == Decimal("3000.00")

    empty = (await client.get(f"/api/v1/dashboard?year={year - 1}")).json()["money_flow"]
    assert empty["income"] == []


@pytest_asyncio.fixture
async def closed_period_with_full_flows(session_factory):
    """Seed a period exercising every money-flow path.

    Income 9500 (of which 500 is a non-cash employer match) funds expenses 400,
    a 1500 retirement build, 1200 of mortgage principal, and a 7000 brokerage
    buy — which overdraws cash by 600. Plus an opening-balance entry and a memo
    entry, both of which must be dropped whole.
    """
    async with session_factory() as session:
        period = Period(
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status="closed",
            closed_at=datetime(2026, 10, 1),
        )
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash & Cash Equivalents", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=110101, account_name="Brokerage", account_type="Asset",
                    sub_category="Investments", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=111102, account_name="Roth 401(k)", account_type="Asset",
                    sub_category="Retirement & Tax-Advantaged Accounts", normal_balance="debit",
                    is_memo=False, is_active=True),
            Account(account_code=112102, account_name="Unvested RSUs", account_type="Memo Asset*",
                    sub_category="Memo", normal_balance="debit", is_memo=True, is_active=True),
            Account(account_code=210102, account_name="Mortgage Payable", account_type="Liability",
                    sub_category="Long-Term Debt", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=300101, account_name="Owner's Equity", account_type="Equity",
                    sub_category="Contributed Capital", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400106, account_name="Employer 401(k) Match", account_type="Income",
                    sub_category="Employer Benefits", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()

        def mk_entry(desc: str, day: int, source: str = "manual") -> JournalEntry:
            return JournalEntry(
                entry_id=uuid.uuid4(), period_id=period.period_id,
                entry_date=date(2026, 9, day), description=desc, source_type=source,
            )

        paycheck = mk_entry("Paycheck", 15)
        match = mk_entry("Employer 401(k) match", 15)
        groceries = mk_entry("Groceries", 16)
        mortgage = mk_entry("Mortgage principal", 17)
        buy = mk_entry("Brokerage purchase", 18)
        opening = mk_entry("Opening balances", 1, "adjusting")
        memo = mk_entry("RSU grant (memo)", 20, "adjusting")
        session.add_all([paycheck, match, groceries, mortgage, buy, opening, memo])
        await session.flush()

        def line(entry: JournalEntry, code: int, debit: str = "0", credit: str = "0") -> JournalLine:
            return JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id, account_code=code,
                               debit_amount=Decimal(debit), credit_amount=Decimal(credit))

        session.add_all([
            # Gross 9000 split between net cash and a payroll-deducted contribution.
            line(paycheck, 100101, debit="8000"),
            line(paycheck, 111102, debit="1000"),
            line(paycheck, 400101, credit="9000"),
            # Employer match — income with no cash leg at all.
            line(match, 111102, debit="500"),
            line(match, 400106, credit="500"),
            line(groceries, 520101, debit="400"),
            line(groceries, 100101, credit="400"),
            # Principal only; interest would be a separate expense line.
            line(mortgage, 210102, debit="1200"),
            line(mortgage, 100101, credit="1200"),
            line(buy, 110101, debit="7000"),
            line(buy, 100101, credit="7000"),
            # Excluded: touches Equity.
            line(opening, 100101, debit="5000"),
            line(opening, 300101, credit="5000"),
            # Excluded: touches an account outside the four flow types.
            line(memo, 112102, debit="300"),
            line(memo, 100101, credit="300"),
        ])
        await session.commit()

        return period.period_id


@pytest.mark.asyncio
async def test_money_flow_balances(client: AsyncClient, closed_period_with_full_flows):
    """The identity the whole model exists to guarantee. Exact, not approximate."""
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]

    income = sum(Decimal(b["amount"]) for b in flow["income"])
    expenses = sum(Decimal(b["amount"]) for b in flow["expenses"])
    fund_flows = sum(Decimal(b["amount"]) for b in flow["fund_flows"])

    assert income == expenses + fund_flows
    assert income == Decimal("9500.00")


@pytest.mark.asyncio
async def test_money_flow_includes_noncash_income(
    client: AsyncClient, closed_period_with_full_flows
):
    """The employer match has no cash leg, so the old cash-gated logic missed it."""
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]

    assert _buckets(flow["income"])["Employer Benefits"] == Decimal("500.00")
    # 1000 payroll deduction + 500 match, both landing in the same asset.
    assert _buckets(flow["fund_flows"])["Retirement & Tax-Advantaged Accounts"] == Decimal("1500.00")


@pytest.mark.asyncio
async def test_money_flow_includes_debt_principal(
    client: AsyncClient, closed_period_with_full_flows
):
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]
    assert _buckets(flow["fund_flows"])["Long-Term Debt"] == Decimal("1200.00")


@pytest.mark.asyncio
async def test_money_flow_cash_decrease_is_negative(
    client: AsyncClient, closed_period_with_full_flows
):
    """Spending past income makes cash a source, not a use — a negative bucket."""
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]

    # 8000 in, less 400 groceries, 1200 principal and a 7000 buy.
    assert _buckets(flow["fund_flows"])["Cash & Cash Equivalents"] == Decimal("-600.00")


@pytest.mark.asyncio
async def test_money_flow_excludes_opening_balance_entry(
    client: AsyncClient, closed_period_with_full_flows
):
    """The 5000 equity seed would otherwise inflate cash and unbalance the model."""
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]

    assert _buckets(flow["fund_flows"])["Cash & Cash Equivalents"] == Decimal("-600.00")
    assert "Contributed Capital" not in _buckets(flow["fund_flows"])


@pytest.mark.asyncio
async def test_money_flow_excludes_memo_entry(
    client: AsyncClient, closed_period_with_full_flows
):
    flow = (await client.get("/api/v1/dashboard")).json()["money_flow"]
    assert "Memo" not in _buckets(flow["fund_flows"])


@pytest.mark.asyncio
async def test_dashboard_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/v1/dashboard")
    assert response.status_code == 401


# ── Paycheck flow ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def closed_period_with_paystub(session_factory):
    """One closed period with a full paystub plus downstream spending.

    Paystub (source_type="paystub"): gross 9000 employee earnings (Regular 6000,
    Bonus 2000, RSU 1000) + a 500 employer 401(k) match + 400 employer stock.
    Withheld: 1500 tax, 300 benefits, 700 employee 401(k), 200 HSA, plus the
    employer match's paired 401(k) debit (500, merging with the employee
    deferral) and the employer stock's paired ASPP debit (400). Net pay to
    checking is therefore 6300.

    Then non-paystub activity: 2000 rent, 300 investment income deposited, and a
    1000 post-tax brokerage buy. Net checking change = +3600 (cash saved).
    """
    async with session_factory() as session:
        period = Period(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            status="closed",
            closed_at=datetime(2026, 4, 1),
        )
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash & Cash Equivalents", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=100201, account_name="HSA Cash", account_type="Asset",
                    sub_category="Restricted Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400102, account_name="Bonus", account_type="Income",
                    sub_category="Variable Compensation", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400103, account_name="RSU", account_type="Income",
                    sub_category="Equity Compensation", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400106, account_name="Employer 401k Match", account_type="Income",
                    sub_category="Employer Benefits", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400104, account_name="Employer Stock Contribution", account_type="Income",
                    sub_category="Equity Compensation", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=410101, account_name="Capital Gains", account_type="Income",
                    sub_category="Investment Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=570101, account_name="Federal Tax", account_type="Expense",
                    sub_category="Payroll Taxes", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=580101, account_name="Health Insurance", account_type="Expense",
                    sub_category="Employee Benefits", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=510101, account_name="Rent", account_type="Expense",
                    sub_category="Housing", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=111102, account_name="Roth 401k", account_type="Asset",
                    sub_category="Retirement & Tax-Advantaged Accounts", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=110101, account_name="Brokerage", account_type="Asset",
                    sub_category="Investments", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=110102, account_name="Computer Share – ASPP", account_type="Asset",
                    sub_category="Investments", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()

        paystub = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                               entry_date=date(2026, 3, 15), description="Paystub", source_type="paystub")
        rent = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                            entry_date=date(2026, 3, 1), description="Rent", source_type="manual")
        divs = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                            entry_date=date(2026, 3, 10), description="Dividends", source_type="manual")
        invest = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                              entry_date=date(2026, 3, 20), description="Brokerage buy", source_type="manual")
        session.add_all([paystub, rent, divs, invest])
        await session.flush()

        def line(entry, code, debit, credit):
            return JournalLine(line_id=uuid.uuid4(), entry_id=entry.entry_id, account_code=code,
                               debit_amount=Decimal(debit), credit_amount=Decimal(credit))

        session.add_all([
            # Paystub: earning credits, withholding debits, employer match/stock
            # with their paired asset debits, and net pay to checking.
            line(paystub, 400101, "0", "6000"),
            line(paystub, 400102, "0", "2000"),
            line(paystub, 400103, "0", "1000"),
            line(paystub, 400106, "0", "500"),
            line(paystub, 400104, "0", "400"),
            line(paystub, 570101, "1500", "0"),
            line(paystub, 580101, "300", "0"),
            line(paystub, 111102, "700", "0"),   # employee 401(k)
            line(paystub, 100201, "200", "0"),   # HSA (restricted cash — a deduction, not take-home)
            line(paystub, 111102, "500", "0"),   # employer match → same 401(k) account
            line(paystub, 110102, "400", "0"),   # employer stock → ASPP
            line(paystub, 100101, "6300", "0"),  # net pay = take-home
            # Downstream non-paystub activity, all against checking.
            line(rent, 510101, "2000", "0"),
            line(rent, 100101, "0", "2000"),
            line(divs, 100101, "300", "0"),
            line(divs, 410101, "0", "300"),
            line(invest, 110101, "1000", "0"),
            line(invest, 100101, "0", "1000"),
        ])
        await session.commit()
        return period.period_id


def _sum(section: list[dict]) -> Decimal:
    return sum((Decimal(b["amount"]) for b in section), Decimal("0"))


@pytest.mark.asyncio
async def test_paycheck_flow_balances(client: AsyncClient, closed_period_with_paystub):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]
    take_home = Decimal(flow["take_home"])

    # All paystub income (employee + employer) == take-home + everything withheld.
    assert _sum(flow["earnings"]) + _sum(flow["employer"]) == take_home + _sum(flow["deductions"])
    # Take-home + other income + drawdowns == everything spent/saved downstream.
    assert take_home + _sum(flow["other_income"]) + _sum(flow["drawdowns"]) == _sum(flow["uses"])


@pytest.mark.asyncio
async def test_paycheck_take_home_is_net_cash(client: AsyncClient, closed_period_with_paystub):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]

    assert Decimal(flow["take_home"]) == Decimal("6300.00")
    # Gross is the 9000 employee earnings only — employer match/stock are listed
    # separately in the employer buckets.
    assert _sum(flow["earnings"]) == Decimal("9000.00")
    assert _buckets(flow["earnings"]) == {
        "Earned Income": Decimal("6000.00"),
        "Variable Compensation": Decimal("2000.00"),
        "Equity Compensation": Decimal("1000.00"),
    }


@pytest.mark.asyncio
async def test_paycheck_hsa_is_a_deduction_not_take_home(
    client: AsyncClient, closed_period_with_paystub
):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]
    ded = _buckets(flow["deductions"])

    # HSA cash withheld pre-tax, so it lowers take-home like any tax; labeled
    # per-account rather than by its "Restricted Cash" sub_category.
    assert ded["HSA"] == Decimal("200.00")
    assert ded["Payroll Taxes"] == Decimal("1500.00")
    assert ded["Employee Benefits"] == Decimal("300.00")


@pytest.mark.asyncio
async def test_paycheck_employer_contribs_flow_through_deductions(
    client: AsyncClient, closed_period_with_paystub
):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]

    # Employer money is its own income inflow, keyed by savings destination...
    assert _buckets(flow["employer"]) == {
        "Retirement & Tax-Advantaged Accounts": Decimal("500.00"),
        "Investments": Decimal("400.00"),
    }
    # ...and its paired asset debit stays a withholding: the 401(k) bucket merges
    # the 700 employee deferral with the 500 match, per-account labeled.
    ded = _buckets(flow["deductions"])
    assert ded["401(k)"] == Decimal("1200.00")
    assert ded["ComputerShare – ASPP"] == Decimal("400.00")


@pytest.mark.asyncio
async def test_paycheck_cash_saved_is_a_use(client: AsyncClient, closed_period_with_paystub):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]
    uses = _buckets(flow["uses"])

    assert uses["Housing"] == Decimal("2000.00")
    assert uses["Investments"] == Decimal("1000.00")
    assert uses["Cash & Cash Equivalents"] == Decimal("3600.00")  # net checking growth
    assert not flow["drawdowns"]


@pytest_asyncio.fixture
async def closed_period_with_overspend(session_factory):
    """Take-home 3000 but 5000 of rent — checking is drawn down 2000."""
    async with session_factory() as session:
        period = Period(period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
                        status="closed", closed_at=datetime(2026, 6, 1))
        session.add(period)
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash & Cash Equivalents", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned Income", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=510101, account_name="Rent", account_type="Expense",
                    sub_category="Housing", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.flush()
        paystub = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                               entry_date=date(2026, 5, 15), description="Paystub", source_type="paystub")
        rent = JournalEntry(entry_id=uuid.uuid4(), period_id=period.period_id,
                            entry_date=date(2026, 5, 1), description="Rent", source_type="manual")
        session.add_all([paystub, rent])
        await session.flush()
        session.add_all([
            JournalLine(line_id=uuid.uuid4(), entry_id=paystub.entry_id, account_code=100101,
                        debit_amount=Decimal("3000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=paystub.entry_id, account_code=400101,
                        debit_amount=Decimal("0"), credit_amount=Decimal("3000")),
            JournalLine(line_id=uuid.uuid4(), entry_id=rent.entry_id, account_code=510101,
                        debit_amount=Decimal("5000"), credit_amount=Decimal("0")),
            JournalLine(line_id=uuid.uuid4(), entry_id=rent.entry_id, account_code=100101,
                        debit_amount=Decimal("0"), credit_amount=Decimal("5000")),
        ])
        await session.commit()
        return period.period_id


@pytest.mark.asyncio
async def test_paycheck_drawdown_when_overspending(
    client: AsyncClient, closed_period_with_overspend
):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]

    assert Decimal(flow["take_home"]) == Decimal("3000.00")
    assert _buckets(flow["drawdowns"]) == {"Cash & Cash Equivalents": Decimal("2000.00")}
    assert _buckets(flow["uses"]) == {"Housing": Decimal("5000.00")}
    # Hub still balances: 3000 take-home + 2000 drawn == 5000 spent.
    assert Decimal(flow["take_home"]) + _sum(flow["drawdowns"]) == _sum(flow["uses"])


@pytest.mark.asyncio
async def test_paycheck_flow_empty_without_activity(client: AsyncClient):
    flow = (await client.get("/api/v1/dashboard")).json()["paycheck_flow"]
    assert flow == {
        "earnings": [], "deductions": [], "employer": [],
        "take_home": "0", "other_income": [], "drawdowns": [], "uses": [],
    }
