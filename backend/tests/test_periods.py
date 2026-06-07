"""Tests for the Period resource — service + HTTP routes."""

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.models.user import User
from app.main import app
from app.models.period import Period
from app.services import period as period_service

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
        import uuid
        return User(user_id=uuid.uuid4(), email="test@test.com", hashed_password="", is_active=True)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_current_user] = _mock_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ── Service-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_month_bounds_handles_leap_year():
    start, end = period_service.month_bounds(2024, 2)
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 29)


@pytest.mark.asyncio
async def test_create_period_service(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
    assert period.period_start == date(2026, 1, 1)
    assert period.period_end == date(2026, 1, 31)
    assert period.status == "open"


@pytest.mark.asyncio
async def test_create_period_duplicate_rejected(session_factory):
    async with session_factory() as session:
        await period_service.create_period(session, 2026, 1)
        with pytest.raises(period_service.PeriodError):
            await period_service.create_period(session, 2026, 1)


@pytest.mark.asyncio
async def test_status_transition_forward_and_close(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        pid = period.period_id

        for target in ("pending_review", "pending_close", "closed"):
            await period_service.update_status(session, pid, target)

        refreshed = await session.get(Period, pid)
        assert refreshed.status == "closed"
        assert refreshed.closed_at is not None


@pytest.mark.asyncio
async def test_status_transition_illegal_skip(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        with pytest.raises(period_service.PeriodError):
            await period_service.update_status(session, period.period_id, "closed")


@pytest.mark.asyncio
async def test_delete_any_status(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        pid = period.period_id
        await period_service.update_status(session, pid, "pending_review")
        await period_service.delete_period(session, pid)
        remaining = await session.scalar(select(Period).where(Period.period_id == pid))
        assert remaining is None


@pytest.mark.asyncio
async def test_delete_open_succeeds(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        pid = period.period_id
        await period_service.delete_period(session, pid)

        remaining = await session.scalar(select(Period).where(Period.period_id == pid))
        assert remaining is None


@pytest.mark.asyncio
async def test_next_status_progression():
    assert period_service.next_status("open") == "pending_review"
    assert period_service.next_status("pending_review") == "pending_close"
    assert period_service.next_status("pending_close") == "closed"
    assert period_service.next_status("closed") is None


@pytest.mark.asyncio
async def test_reopen_period_service(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        pid = period.period_id
        for target in ("pending_review", "pending_close", "closed"):
            await period_service.update_status(session, pid, target)
        reopened = await period_service.reopen_period(session, pid)
        assert reopened.status == "open"
        assert reopened.closed_at is None


@pytest.mark.asyncio
async def test_reopen_non_closed_period_rejected(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
        with pytest.raises(period_service.PeriodError):
            await period_service.reopen_period(session, period.period_id)


# ── HTTP route tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_periods_empty(client: AsyncClient):
    response = await client.get("/api/v1/periods")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_periods_pagination(client: AsyncClient):
    # Three periods, returned newest-first by period_start.
    for month in (1, 2, 3):
        await client.post("/api/v1/periods", json={"year": 2026, "month": month})

    page1 = await client.get("/api/v1/periods?limit=2")
    assert [p["period_start"] for p in page1.json()] == ["2026-03-01", "2026-02-01"]
    page2 = await client.get("/api/v1/periods?limit=2&offset=2")
    assert [p["period_start"] for p in page2.json()] == ["2026-01-01"]
    # Omitting limit returns all rows (unchanged default behavior).
    assert len((await client.get("/api/v1/periods")).json()) == 3


@pytest.mark.asyncio
async def test_create_period_via_api(client: AsyncClient):
    response = await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    assert response.status_code == 201
    data = response.json()
    assert data["period_start"] == "2026-04-01"
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_create_duplicate_period_returns_400(client: AsyncClient):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    response = await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_period_detail_404(client: AsyncClient):
    response = await client.get("/api/v1/periods/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_advance_status_via_api(client: AsyncClient, session_factory):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})

    async with session_factory() as session:
        period = await session.scalar(select(Period))

    response = await client.post(
        f"/api/v1/periods/{period.period_id}/status",
        json={"new_status": "pending_review"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending_review"


@pytest.mark.asyncio
async def test_advance_status_illegal_skip_returns_400(client: AsyncClient, session_factory):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    async with session_factory() as session:
        period = await session.scalar(select(Period))

    response = await client.post(
        f"/api/v1/periods/{period.period_id}/status",
        json={"new_status": "closed"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_period_via_api(client: AsyncClient, session_factory):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    async with session_factory() as session:
        period = await session.scalar(select(Period))
    pid = period.period_id

    response = await client.delete(f"/api/v1/periods/{pid}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with session_factory() as session:
        remaining = await session.scalar(select(Period))
    assert remaining is None


@pytest.mark.asyncio
async def test_reopen_period_via_api(client: AsyncClient, session_factory):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    async with session_factory() as session:
        period = await session.scalar(select(Period))
    pid = period.period_id

    for target in ("pending_review", "pending_close", "closed"):
        await client.post(f"/api/v1/periods/{pid}/status", json={"new_status": target})

    response = await client.post(f"/api/v1/periods/{pid}/reopen")
    assert response.status_code == 200
    assert response.json()["status"] == "open"


@pytest.mark.asyncio
async def test_dashboard_empty_state(client: AsyncClient):
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["active_period"] is None
    assert data["has_data"] is False


@pytest.mark.asyncio
async def test_dashboard_surfaces_current_open_period(client: AsyncClient):
    await client.post("/api/v1/periods", json={"year": 2026, "month": 4})
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["active_period"] is not None
    assert data["active_period"]["period_start"] == "2026-04-01"
