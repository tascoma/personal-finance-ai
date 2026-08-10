"""Tests for the StatedBalance resource — service + HTTP routes."""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.models.account import Account
from app.models.stated_balance import StatedBalance
from app.services import period as period_service
from app.services import stated_balance as stated_balance_service

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Account(
                    account_code=100101,
                    account_name="Checking",
                    account_type="Asset",
                    sub_category="Cash",
                    normal_balance="debit",
                    is_memo=False,
                    is_active=True,
                ),
                Account(
                    account_code=200101,
                    account_name="Credit Card",
                    account_type="Liability",
                    sub_category="Credit Cards",
                    normal_balance="credit",
                    is_memo=False,
                    is_active=True,
                ),
                Account(
                    account_code=400101,
                    account_name="Salary",
                    account_type="Income",
                    sub_category="Earned",
                    normal_balance="credit",
                    is_memo=False,
                    is_active=True,
                ),
                Account(
                    account_code=112102,
                    account_name="RSUs Unvested",
                    account_type="Memo Asset*",
                    sub_category="Equity",
                    normal_balance="debit",
                    is_memo=True,
                    is_active=True,
                ),
            ]
        )
        await session.commit()
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def open_period(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 4)
    return period


# ── Service-level tests ──────────────────────────────────────────────────────


async def test_list_balance_accounts_filters_to_assets_and_liabilities(
    session_factory,
):
    async with session_factory() as session:
        accounts = await stated_balance_service.list_balance_accounts(session)
    codes = {a.account_code for a in accounts}
    # Income excluded; non-memo Asset/Liability + memo accounts included.
    assert codes == {100101, 200101, 112102}


async def test_upsert_creates_balance(session_factory, open_period):
    async with session_factory() as session:
        balance = await stated_balance_service.upsert_balance(
            session,
            period_id=open_period.period_id,
            account_code=100101,
            stated_balance=Decimal("1234.56"),
        )
    assert balance.stated_balance == Decimal("1234.56")

    async with session_factory() as session:
        rows = await session.scalars(select(StatedBalance))
        assert len(list(rows)) == 1


async def test_upsert_updates_existing_balance(session_factory, open_period):
    async with session_factory() as session:
        await stated_balance_service.upsert_balance(
            session,
            period_id=open_period.period_id,
            account_code=100101,
            stated_balance=Decimal("100.00"),
        )
        await stated_balance_service.upsert_balance(
            session,
            period_id=open_period.period_id,
            account_code=100101,
            stated_balance=Decimal("250.00"),
        )

    async with session_factory() as session:
        rows = (await session.scalars(select(StatedBalance))).all()
    assert len(rows) == 1
    assert rows[0].stated_balance == Decimal("250.00")


async def test_upsert_allowed_on_pending_close_period(session_factory, open_period):
    async with session_factory() as session:
        await period_service.update_status(
            session, open_period.period_id, "pending_review"
        )
        await period_service.update_status(
            session, open_period.period_id, "pending_close"
        )

    async with session_factory() as session:
        balance = await stated_balance_service.upsert_balance(
            session,
            period_id=open_period.period_id,
            account_code=100101,
            stated_balance=Decimal("1.00"),
        )
    assert balance.stated_balance == Decimal("1.00")


async def test_upsert_blocked_on_closed_period(session_factory, open_period):
    async with session_factory() as session:
        await period_service.update_status(
            session, open_period.period_id, "pending_review"
        )
        await period_service.update_status(
            session, open_period.period_id, "pending_close"
        )
        await period_service.update_status(
            session, open_period.period_id, "closed"
        )

    async with session_factory() as session:
        with pytest.raises(stated_balance_service.BalanceError):
            await stated_balance_service.upsert_balance(
                session,
                period_id=open_period.period_id,
                account_code=100101,
                stated_balance=Decimal("1.00"),
            )


# ── HTTP route tests ─────────────────────────────────────────────────────────


async def test_post_balances_json(client: AsyncClient, session_factory, open_period):
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/balances",
        json=[
            {"account_code": 100101, "stated_balance": "999.99"},
            {"account_code": 400101, "stated_balance": "5000.00"},  # Income — ignored by service
        ],
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with session_factory() as session:
        rows = (await session.scalars(select(StatedBalance))).all()
    by_code = {r.account_code: r.stated_balance for r in rows}
    assert by_code == {100101: Decimal("999.99")}  # 400101 ignored (Income)


async def test_period_detail_includes_stated_balances(
    client: AsyncClient, session_factory, open_period
):
    await client.post(
        f"/api/v1/periods/{open_period.period_id}/balances",
        json=[{"account_code": 100101, "stated_balance": "777.77"}],
    )
    response = await client.get(f"/api/v1/periods/{open_period.period_id}")
    assert response.status_code == 200
    data = response.json()
    assert "stated_balances" in data
    assert data["stated_balances"].get("100101") == "777.77"


async def test_balance_invalid_amount_returns_400(
    client: AsyncClient, open_period
):
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/balances",
        json=[{"account_code": 100101, "stated_balance": "not-a-number"}],
    )
    assert response.status_code == 400
    assert "Invalid balance" in response.json()["detail"]
