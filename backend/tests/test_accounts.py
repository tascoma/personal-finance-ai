"""Tests for the /accounts route."""

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
async def seeded_accounts(session_factory):
    async with session_factory() as session:
        session.add_all([
            Account(account_code=100101, account_name="Checking", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary", account_type="Income",
                    sub_category="Earned", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=900999, account_name="Retired", account_type="Equity",
                    sub_category="Misc", normal_balance="credit", is_memo=False, is_active=False),
        ])
        await session.commit()


@pytest.mark.asyncio
async def test_list_accounts_empty(client: AsyncClient):
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_accounts_excludes_inactive_and_orders_by_code(
    client: AsyncClient, seeded_accounts
):
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 200
    body = response.json()

    codes = [a["account_code"] for a in body]
    assert codes == [100101, 400101]  # 900999 inactive — filtered out
    assert body[0]["account_name"] == "Checking"


@pytest.mark.asyncio
async def test_list_accounts_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/v1/accounts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_accounts_include_inactive(client: AsyncClient, seeded_accounts):
    response = await client.get("/api/v1/accounts?include_inactive=true")
    assert response.status_code == 200
    codes = [a["account_code"] for a in response.json()]
    assert codes == [100101, 400101, 900999]  # 900999 inactive now included


@pytest.mark.asyncio
async def test_create_account_success(client: AsyncClient):
    payload = {
        "account_code": 100200,
        "account_name": "Savings",
        "account_type": "Asset",
        "sub_category": "Cash",
        "normal_balance": "debit",
    }
    response = await client.post("/api/v1/accounts", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["account_code"] == 100200
    assert body["is_active"] is True
    assert body["is_memo"] is False

    listing = await client.get("/api/v1/accounts")
    assert 100200 in [a["account_code"] for a in listing.json()]


@pytest.mark.asyncio
async def test_create_account_duplicate_code_conflict(client: AsyncClient, seeded_accounts):
    payload = {
        "account_code": 100101,  # already seeded
        "account_name": "Dup",
        "account_type": "Asset",
        "sub_category": "Cash",
        "normal_balance": "debit",
    }
    response = await client.post("/api/v1/accounts", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_account_invalid_type_rejected(client: AsyncClient):
    payload = {
        "account_code": 100300,
        "account_name": "Bad",
        "account_type": "Nonsense",
        "sub_category": "Cash",
        "normal_balance": "debit",
    }
    response = await client.post("/api/v1/accounts", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_account_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.post("/api/v1/accounts", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_archive_account_hides_from_default_list(client: AsyncClient, seeded_accounts):
    response = await client.patch("/api/v1/accounts/100101", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    default = await client.get("/api/v1/accounts")
    assert 100101 not in [a["account_code"] for a in default.json()]

    with_inactive = await client.get("/api/v1/accounts?include_inactive=true")
    assert 100101 in [a["account_code"] for a in with_inactive.json()]


@pytest.mark.asyncio
async def test_restore_account(client: AsyncClient, seeded_accounts):
    response = await client.patch("/api/v1/accounts/900999", json={"is_active": True})
    assert response.status_code == 200
    default = await client.get("/api/v1/accounts")
    assert 900999 in [a["account_code"] for a in default.json()]


@pytest.mark.asyncio
async def test_update_account_fields(client: AsyncClient, seeded_accounts):
    response = await client.patch(
        "/api/v1/accounts/100101",
        json={"account_name": "Primary Checking", "sub_category": "Operating Cash"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["account_name"] == "Primary Checking"
    assert body["sub_category"] == "Operating Cash"
    assert body["normal_balance"] == "debit"  # untouched fields preserved


@pytest.mark.asyncio
async def test_update_account_not_found(client: AsyncClient):
    response = await client.patch("/api/v1/accounts/999999", json={"account_name": "X"})
    assert response.status_code == 404


async def _seed_line_in_period(session_factory, account_code: int, period_status: str) -> None:
    """Add one journal line on account_code inside a period with the given status."""
    period_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    async with session_factory() as session:
        session.add_all([
            Period(period_id=period_id, period_start=date(2026, 1, 1),
                   period_end=date(2026, 1, 31), status=period_status),
            JournalEntry(entry_id=entry_id, period_id=period_id, entry_date=date(2026, 1, 15),
                         description="Test", source_type="manual", created_by="user"),
            JournalLine(entry_id=entry_id, account_code=account_code,
                        debit_amount=Decimal("100.00"), credit_amount=Decimal("0")),
        ])
        await session.commit()


@pytest.mark.asyncio
async def test_archive_blocked_with_open_period_activity(client, session_factory, seeded_accounts):
    await _seed_line_in_period(session_factory, 100101, "open")
    response = await client.patch("/api/v1/accounts/100101", json={"is_active": False})
    assert response.status_code == 409
    assert "open period" in response.json()["detail"]
    # Account is left active.
    listing = await client.get("/api/v1/accounts")
    assert 100101 in [a["account_code"] for a in listing.json()]


@pytest.mark.asyncio
async def test_archive_allowed_when_activity_only_in_closed_period(
    client, session_factory, seeded_accounts
):
    await _seed_line_in_period(session_factory, 100101, "closed")
    response = await client.patch("/api/v1/accounts/100101", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_edit_other_fields_allowed_with_open_period_activity(
    client, session_factory, seeded_accounts
):
    """The guard only blocks archiving — editing other fields stays allowed."""
    await _seed_line_in_period(session_factory, 100101, "open")
    response = await client.patch("/api/v1/accounts/100101", json={"account_name": "Renamed"})
    assert response.status_code == 200
    assert response.json()["account_name"] == "Renamed"
