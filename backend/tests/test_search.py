"""Tests for the /search global command-palette endpoint."""

import uuid
from datetime import date

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
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
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
async def seeded(session_factory):
    async with session_factory() as session:
        period = Period(period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), status="open")
        session.add(period)
        session.add(Account(
            account_code=600101, account_name="Groceries", account_type="Expense",
            sub_category="Food", normal_balance="debit", is_memo=False, is_active=True,
        ))
        await session.flush()

        doc = Document(
            document_id=uuid.uuid4(), period_id=period.period_id,
            document_type="bank_statement", file_name="chase-jan.csv",
            file_path="/tmp/chase-jan.csv", parse_status="complete",
        )
        session.add(doc)
        await session.flush()

        session.add_all([
            RawTransaction(
                document_id=doc.document_id, period_id=period.period_id,
                txn_date=date(2026, 1, 5), description="AMAZON.COM purchase",
                amount="-42.50", status="staged",
            ),
            RawTransaction(
                document_id=doc.document_id, period_id=period.period_id,
                txn_date=date(2026, 1, 10), description="AMAZON refund credit",
                amount="15.00", status="staged",
            ),
        ])

        entry = JournalEntry(
            period_id=period.period_id, entry_date=date(2026, 1, 12),
            description="Monthly rent payment", source_type="manual",
        )
        session.add(entry)
        await session.flush()
        session.add(JournalLine(
            entry_id=entry.entry_id, account_code=600101,
            debit_amount="42.50", credit_amount="0", memo="landlord wire",
        ))

        await session.commit()
        return period.period_id


@pytest.mark.asyncio
async def test_search_matches_transactions_and_accounts(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=amazon")
    assert response.status_code == 200
    body = response.json()
    titles = [h["title"] for h in body["hits"] if h["type"] == "transaction"]
    assert "AMAZON.COM purchase" in titles
    assert "AMAZON refund credit" in titles


@pytest.mark.asyncio
async def test_search_account_by_name(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=grocer")
    hits = [h for h in response.json()["hits"] if h["type"] == "account"]
    assert len(hits) == 1
    assert hits[0]["title"] == "Groceries"
    assert hits[0]["id"] == "600101"


@pytest.mark.asyncio
async def test_search_multiword_narrows_results(client: AsyncClient, seeded):
    # Both terms must match the same transaction (AND semantics).
    response = await client.get("/api/v1/search?q=amazon%20refund")
    txns = [h for h in response.json()["hits"] if h["type"] == "transaction"]
    assert [h["title"] for h in txns] == ["AMAZON refund credit"]


@pytest.mark.asyncio
async def test_search_journal_entry_by_line_memo(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=landlord")
    entries = [h for h in response.json()["hits"] if h["type"] == "journal_entry"]
    assert [h["title"] for h in entries] == ["Monthly rent payment"]


@pytest.mark.asyncio
async def test_search_document_by_filename(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=chase")
    docs = [h for h in response.json()["hits"] if h["type"] == "document"]
    assert [h["title"] for h in docs] == ["chase-jan.csv"]


@pytest.mark.asyncio
async def test_search_period_by_month_name(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=january%202026")
    periods = [h for h in response.json()["hits"] if h["type"] == "period"]
    assert [h["title"] for h in periods] == ["January 2026"]


@pytest.mark.asyncio
async def test_search_empty_query_is_422(client: AsyncClient, seeded):
    response = await client.get("/api/v1/search?q=")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_requires_auth(session_factory):
    """Without the auth override, the endpoint rejects unauthenticated calls."""
    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/v1/search?q=amazon")
    app.dependency_overrides.clear()
    assert response.status_code == 401
