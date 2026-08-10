"""Tests for the Statements page — service computations + HTTP route."""

from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.main import app
from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.raw_transaction import RawTransaction
from app.models.stated_balance import StatedBalance
from app.models.user import User
from app.services import journal as journal_service
from app.services import period as period_service
from app.services import statements as statements_service

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=110101, account_name="Brokerage", account_type="Asset",
                    sub_category="Investments", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=200101, account_name="Mastercard", account_type="Liability",
                    sub_category="Credit Cards", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=300101, account_name="Owner Equity", account_type="Equity",
                    sub_category="Capital", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=410103, account_name="Unrealized Market Gain/Loss",
                    account_type="Income", sub_category="Investment Income",
                    normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=112102, account_name="Fidelity – RSUs (Unvested)",
                    account_type="Memo Asset*", sub_category="Equity Compensation (Off-BS)",
                    normal_balance="debit", is_memo=True, is_active=True),
        ])
        await session.commit()
    yield factory
    await eng.dispose()


async def _seed_period_with_entries(session_factory, year: int, month: int):
    """Create a closed period and post a paystub-like + grocery entry."""
    async with session_factory() as session:
        period = await period_service.create_period(session, year, month)

    async with session_factory() as session:
        doc_pay = Document(
            period_id=period.period_id, document_type="paystub",
            file_name="pay.pdf", file_path="/tmp/pay.pdf",
            source_account_code=100101, parse_status="complete",
        )
        doc_groc = Document(
            period_id=period.period_id, document_type="bank_statement",
            file_name="bank.csv", file_path="/tmp/bank.csv",
            source_account_code=100101, parse_status="complete",
        )
        session.add_all([doc_pay, doc_groc])
        await session.commit()
        await session.refresh(doc_pay)
        await session.refresh(doc_groc)

    async with session_factory() as session:
        session.add_all([
            RawTransaction(
                document_id=doc_pay.document_id, period_id=period.period_id,
                txn_date=date(year, month, 5), description="REGULAR EARNING",
                amount=Decimal("3000.00"), suggested_account_code=400101,
                classifier_confidence=Decimal("0.99"),
                is_flagged=False, is_duplicate=False, status="approved",
            ),
            RawTransaction(
                document_id=doc_groc.document_id, period_id=period.period_id,
                txn_date=date(year, month, 12), description="WHOLE FOODS",
                amount=Decimal("-150.00"), suggested_account_code=520101,
                classifier_confidence=Decimal("0.95"),
                is_flagged=False, is_duplicate=False, status="approved",
            ),
        ])
        await session.commit()

    async with session_factory() as session:
        await journal_service.post_period(session, period.period_id)

    async with session_factory() as session:
        p = await session.get(period_service.Period, period.period_id)
        p.status = "closed"
        await session.commit()
        await session.refresh(p)
    return p


# ── service-level tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_balance_sheet_after_paystub_and_expense(session_factory):
    period = await _seed_period_with_entries(session_factory, 2026, 1)

    async with session_factory() as session:
        bs = await statements_service.compute_balance_sheet(
            session, [period.period_id], "January 2026"
        )

    # Net pay 3000 hits checking debit; grocery -150 credits checking.
    # So Checking balance = 3000 - 150 = 2850.
    assert bs.total_assets == Decimal("2850.00")
    cash_section = next(s for s in bs.assets if s.label == "Cash")
    assert cash_section.subtotal == Decimal("2850.00")


@pytest.mark.asyncio
async def test_income_statement_net_income(session_factory):
    period = await _seed_period_with_entries(session_factory, 2026, 1)

    async with session_factory() as session:
        inc = await statements_service.compute_income_statement(
            session, [period.period_id], "January 2026"
        )

    assert inc.total_income == Decimal("3000.00")
    assert inc.total_expenses == Decimal("150.00")
    assert inc.net_income == Decimal("2850.00")
    # No unrealized G/L in this seed — OCI is empty.
    assert inc.other_comprehensive_income == []
    assert inc.total_oci == Decimal("0")
    assert inc.comprehensive_income == Decimal("2850.00")


@pytest.mark.asyncio
async def test_income_statement_separates_oci(session_factory):
    period = await _seed_period_with_entries(session_factory, 2026, 1)

    # Post an unrealized G/L entry: debit Brokerage 500, credit Unrealized G/L 500.
    async with session_factory() as session:
        import uuid
        eid = uuid.uuid4()
        session.add(JournalEntry(
            entry_id=eid, period_id=period.period_id, entry_date=date(2026, 1, 31),
            description="Mark-to-market", source_type="adjusting",
            source_document_id=None, created_by="python",
        ))
        session.add_all([
            JournalLine(entry_id=eid, account_code=110101,
                        debit_amount=Decimal("500.00"), credit_amount=Decimal("0")),
            JournalLine(entry_id=eid, account_code=410103,
                        debit_amount=Decimal("0"), credit_amount=Decimal("500.00")),
        ])
        await session.commit()

    async with session_factory() as session:
        inc = await statements_service.compute_income_statement(
            session, [period.period_id], "January 2026"
        )

    # Net income excludes unrealized G/L; OCI captures it; comprehensive income sums them.
    assert inc.total_income == Decimal("3000.00")
    assert inc.net_income == Decimal("2850.00")
    assert all(
        line.account_code != 410103
        for sec in inc.income for line in sec.lines
    )
    assert len(inc.other_comprehensive_income) == 1
    oci_line = inc.other_comprehensive_income[0].lines[0]
    assert oci_line.account_code == 410103
    assert oci_line.amount == Decimal("500.00")
    assert inc.total_oci == Decimal("500.00")
    assert inc.comprehensive_income == Decimal("3350.00")


@pytest.mark.asyncio
async def test_balance_sheet_pivot_off_balance_sheet_section(session_factory):
    p1 = await _seed_period_with_entries(session_factory, 2026, 1)
    p2 = await _seed_period_with_entries(session_factory, 2026, 2)

    async with session_factory() as session:
        session.add_all([
            StatedBalance(period_id=p1.period_id, account_code=112102,
                          stated_balance=Decimal("16867.36")),
            StatedBalance(period_id=p2.period_id, account_code=112102,
                          stated_balance=Decimal("18114.65")),
        ])
        await session.commit()

    async with session_factory() as session:
        pivot = await statements_service.compute_balance_sheet_pivot(session)

    assert len(pivot.periods) == 2
    assert len(pivot.off_balance_sheet) == 1
    sec = pivot.off_balance_sheet[0]
    assert sec.label == "Equity Compensation (Off-BS)"
    assert len(sec.rows) == 1
    row = sec.rows[0]
    assert row.account_code == 112102
    # Point-in-time snapshots — period 2 value is its own stated balance, not cumulative.
    assert row.balances == [Decimal("16867.36"), Decimal("18114.65")]
    assert pivot.total_off_balance_sheet == [Decimal("16867.36"), Decimal("18114.65")]
    # Memo amounts do not roll into Total Assets.
    assert all(b not in (Decimal("16867.36"), Decimal("18114.65")) for b in pivot.total_assets)


@pytest.mark.asyncio
async def test_balance_sheet_pivot_includes_open_seed_period(session_factory):
    """A still-open earlier period with seed/opening-balance entries should
    contribute to cumulative columns for later closed periods."""
    import uuid

    async with session_factory() as session:
        seed = await period_service.create_period(session, 2026, 3)

    # Post an opening-balance adjusting entry to the seed period (leave it open).
    async with session_factory() as session:
        eid = uuid.uuid4()
        session.add(JournalEntry(
            entry_id=eid, period_id=seed.period_id, entry_date=date(2026, 3, 31),
            description="Opening balances — manual seed", source_type="adjusting",
            source_document_id=None, created_by="python",
        ))
        session.add_all([
            JournalLine(entry_id=eid, account_code=100101,
                        debit_amount=Decimal("5000.00"), credit_amount=Decimal("0")),
            JournalLine(entry_id=eid, account_code=300101,
                        debit_amount=Decimal("0"), credit_amount=Decimal("5000.00")),
        ])
        await session.commit()

    # April period with normal activity, then close it.
    april = await _seed_period_with_entries(session_factory, 2026, 4)

    async with session_factory() as session:
        pivot = await statements_service.compute_balance_sheet_pivot(session)

    assert [p.period_id for p in pivot.periods] == [seed.period_id, april.period_id]
    checking_row = next(
        r for sec in pivot.assets for r in sec.rows if r.account_code == 100101
    )
    # March = seeded opening 5000; April = 5000 + (3000 net pay - 150 groceries) = 7850.
    assert checking_row.balances == [Decimal("5000.00"), Decimal("7850.00")]


@pytest.mark.asyncio
async def test_cashflow_classifies_operating(session_factory):
    period = await _seed_period_with_entries(session_factory, 2026, 1)

    async with session_factory() as session:
        cf = await statements_service.compute_cashflow(
            session, [period.period_id], "January 2026"
        )

    # Indirect method: net income = 3000 - 150 = 2850; no non-cash items; no CC activity.
    assert cf.operating_total == Decimal("2850.00")
    assert cf.investing_total == Decimal("0")
    assert cf.financing_total == Decimal("0")
    assert cf.net_change_in_cash == Decimal("2850.00")


@pytest.mark.asyncio
async def test_aggregate_combines_periods(session_factory):
    p1 = await _seed_period_with_entries(session_factory, 2026, 1)
    p2 = await _seed_period_with_entries(session_factory, 2026, 2)

    async with session_factory() as session:
        bs_all = await statements_service.compute_balance_sheet(
            session, None, "All periods"
        )
        bs_one = await statements_service.compute_balance_sheet(
            session, [p1.period_id], "January 2026"
        )

    # Aggregate should be roughly double a single period (same seed)
    assert bs_all.total_assets == bs_one.total_assets * 2
    # Reference p2 to silence unused-fixture lint
    assert p2.period_id != p1.period_id


# ── HTTP route tests ────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_db():
        async with session_factory() as session:
            yield session

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
async def test_balance_sheet_endpoint_renders_empty(client):
    response = await client.get("/api/v1/statements/balance-sheet")
    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    assert "liabilities" in data
    assert "equity" in data
    assert "off_balance_sheet" in data
    assert "total_off_balance_sheet" in data


@pytest.mark.asyncio
async def test_income_statement_endpoint_renders_with_data(client, session_factory):
    await _seed_period_with_entries(session_factory, 2026, 1)
    response = await client.get("/api/v1/statements/income")
    assert response.status_code == 200
    data = response.json()
    assert data["total_income"] == "3000.00"
    assert data["total_expenses"] == "150.00"
    assert data["net_income"] == "2850.00"
    assert data["other_comprehensive_income"] == []
    assert data["total_oci"] == "0"
    assert data["comprehensive_income"] == "2850.00"


@pytest.mark.asyncio
async def test_income_statement_period_filter(client, session_factory):
    period = await _seed_period_with_entries(session_factory, 2026, 1)
    response = await client.get(f"/api/v1/statements/income?period_id={period.period_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total_income"] == "3000.00"


@pytest.mark.asyncio
async def test_income_statement_aggregate_when_no_period_filter(client, session_factory):
    await _seed_period_with_entries(session_factory, 2026, 1)
    response = await client.get("/api/v1/statements/income")
    assert response.status_code == 200
    data = response.json()
    assert data["range_label"] == "All Periods"


@pytest.mark.asyncio
async def test_cashflow_endpoint_renders(client, session_factory):
    await _seed_period_with_entries(session_factory, 2026, 1)
    response = await client.get("/api/v1/statements/cashflow")
    assert response.status_code == 200
    data = response.json()
    assert "operating_total" in data
    assert "net_change_in_cash" in data
    assert data["net_change_in_cash"] == "2850.00"
