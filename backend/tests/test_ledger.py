"""Tests for the Ledger page — read-only view of journal entries by period."""

import uuid
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
    async with factory() as session:
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=300102, account_name="Prior Period Net Worth",
                    account_type="Equity", sub_category="Retained Equity",
                    normal_balance="credit", is_memo=False, is_active=True),
        ])
        await session.commit()
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    async def _mock_user() -> User:
        import uuid
        return User(user_id=uuid.uuid4(), email="test@test.com", hashed_password="", is_active=True)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = _mock_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ledger_empty_when_no_periods(client: AsyncClient):
    response = await client.get("/api/v1/ledger")
    assert response.status_code == 200
    data = response.json()
    assert data["periods"] == []
    assert data["entries_by_period"] == {}


@pytest.mark.asyncio
async def test_ledger_lists_entries_grouped_by_period(client, session_factory):
    period_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Period(
            period_id=period_id,
            period_start=date(2025, 12, 1),
            period_end=date(2025, 12, 31),
            status="closed",
        ))
        session.add(JournalEntry(
            entry_id=entry_id,
            period_id=period_id,
            entry_date=date(2025, 12, 31),
            description="Opening balances — opening.xlsx",
            source_type="adjusting",
            is_adjusting=True,
            created_by="python",
        ))
        session.add(JournalLine(
            entry_id=entry_id, account_code=100101,
            debit_amount=Decimal("5200.00"), credit_amount=Decimal("0"),
            memo="Opening balance",
        ))
        session.add(JournalLine(
            entry_id=entry_id, account_code=300102,
            debit_amount=Decimal("0"), credit_amount=Decimal("5200.00"),
            memo="Opening balance offset",
        ))
        await session.commit()

    response = await client.get("/api/v1/ledger")
    assert response.status_code == 200
    data = response.json()
    assert len(data["periods"]) == 1
    pid_str = str(period_id)
    assert pid_str in data["entries_by_period"]
    entries = data["entries_by_period"][pid_str]
    assert len(entries) == 1
    assert "Opening balances" in entries[0]["description"]
    lines = entries[0]["lines"]
    amounts = {line["account_code"]: line["debit_amount"] for line in lines}
    assert amounts[100101] == "5200.00"


@pytest.mark.asyncio
async def test_ledger_renders_period_with_no_entries(client, session_factory):
    period_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(Period(
            period_id=period_id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status="open",
        ))
        await session.commit()

    response = await client.get("/api/v1/ledger")
    assert response.status_code == 200
    data = response.json()
    assert len(data["periods"]) == 1
    assert data["periods"][0]["period_start"] == "2026-01-01"
    assert str(period_id) not in data["entries_by_period"] or data["entries_by_period"].get(str(period_id), []) == []
