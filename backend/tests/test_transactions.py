"""Tests for the /periods/{period_id}/transactions routes."""

import uuid
from datetime import date

import pytest_asyncio
from httpx import AsyncClient

from app.models.account import Account
from app.models.document import Document
from app.models.period import Period
from app.models.raw_transaction import RawTransaction


@pytest_asyncio.fixture
async def seeded(session_factory):
    """Returns (period_id, account_code, doc_id, [txn_id_a, txn_id_b])."""
    async with session_factory() as session:
        period = Period(period_start=date(2026, 1, 1), period_end=date(2026, 1, 31), status="open")
        session.add(period)
        session.add(Account(
            account_code=600101, account_name="Groceries", account_type="Expense",
            sub_category="Food", normal_balance="debit", is_memo=False, is_active=True,
        ))
        await session.flush()

        doc = Document(
            document_id=uuid.uuid4(),
            period_id=period.period_id,
            document_type="bank_statement",
            file_name="seed.csv",
            file_path="/tmp/seed.csv",
            parse_status="complete",
        )
        session.add(doc)
        await session.flush()

        txn_a = RawTransaction(
            document_id=doc.document_id, period_id=period.period_id,
            txn_date=date(2026, 1, 5), description="Trader Joes", amount="-42.50",
            status="staged",
        )
        txn_b = RawTransaction(
            document_id=doc.document_id, period_id=period.period_id,
            txn_date=date(2026, 1, 10), description="Whole Foods", amount="-31.00",
            status="staged",
        )
        session.add_all([txn_a, txn_b])
        await session.commit()

        return period.period_id, 600101, doc.document_id, [txn_a.raw_txn_id, txn_b.raw_txn_id]


async def test_list_transactions_empty_period(client: AsyncClient, seeded):
    other_period = uuid.uuid4()
    response = await client.get(f"/api/v1/periods/{other_period}/transactions")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_transactions_returns_period_rows_in_order(client: AsyncClient, seeded):
    period_id, _, _, _ = seeded
    response = await client.get(f"/api/v1/periods/{period_id}/transactions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [t["description"] for t in body] == ["Trader Joes", "Whole Foods"]


async def test_list_transactions_pagination(client: AsyncClient, seeded):
    period_id, _, _, _ = seeded
    page1 = await client.get(f"/api/v1/periods/{period_id}/transactions?limit=1")
    assert [t["description"] for t in page1.json()] == ["Trader Joes"]
    page2 = await client.get(f"/api/v1/periods/{period_id}/transactions?limit=1&offset=1")
    assert [t["description"] for t in page2.json()] == ["Whole Foods"]
    # Omitting limit returns all rows (unchanged default behavior).
    all_rows = await client.get(f"/api/v1/periods/{period_id}/transactions")
    assert len(all_rows.json()) == 2


async def test_approve_then_unapprove_transaction(client: AsyncClient, seeded):
    period_id, _, _, txn_ids = seeded
    txn_id = txn_ids[0]

    r1 = await client.post(f"/api/v1/periods/{period_id}/transactions/{txn_id}/approve")
    assert r1.status_code == 200
    assert r1.json()["status"] == "approved"

    r2 = await client.post(f"/api/v1/periods/{period_id}/transactions/{txn_id}/unapprove")
    assert r2.status_code == 200
    assert r2.json()["status"] == "staged"


async def test_approve_404_when_txn_not_in_period(client: AsyncClient, seeded):
    _, _, _, _ = seeded
    bogus_period = uuid.uuid4()
    bogus_txn = uuid.uuid4()
    response = await client.post(
        f"/api/v1/periods/{bogus_period}/transactions/{bogus_txn}/approve"
    )
    assert response.status_code == 404


async def test_update_account_changes_suggested_code(client: AsyncClient, seeded):
    period_id, account_code, _, txn_ids = seeded
    response = await client.patch(
        f"/api/v1/periods/{period_id}/transactions/{txn_ids[0]}/account",
        json={"account_code": account_code},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["suggested_account_code"] == account_code
    assert float(body["classifier_confidence"]) == 1.0


async def test_update_account_400_for_unknown_account(client: AsyncClient, seeded):
    period_id, _, _, txn_ids = seeded
    response = await client.patch(
        f"/api/v1/periods/{period_id}/transactions/{txn_ids[0]}/account",
        json={"account_code": 999999},
    )
    assert response.status_code == 400


async def test_approve_all_staged_returns_count(client: AsyncClient, seeded):
    period_id, _, _, _ = seeded
    response = await client.post(
        f"/api/v1/periods/{period_id}/transactions/approve-all-staged"
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2


async def test_reject_transaction_deletes_row(client: AsyncClient, seeded):
    period_id, _, _, txn_ids = seeded
    response = await client.delete(
        f"/api/v1/periods/{period_id}/transactions/{txn_ids[0]}"
    )
    assert response.status_code == 200

    listing = await client.get(f"/api/v1/periods/{period_id}/transactions")
    assert len(listing.json()) == 1
