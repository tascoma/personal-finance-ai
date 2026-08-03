"""Tests for the Journal phase — classify service + HTTP routes."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.classifier import ClassifierOutput, TxnInput, TxnSuggestion
from app.core.config import settings
from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.models.user import User
from app.main import app
from app.models.account import Account
from app.models.document import Document
from app.models.raw_transaction import RawTransaction
from app.services import classify as classify_service
from app.services import period as period_service

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ── fixtures ──────────────────────────────────────────────────────────────────


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
            Account(account_code=200101, account_name="Mastercard", account_type="Liability",
                    sub_category="Credit Cards", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=400101, account_name="Salary - Regular", account_type="Income",
                    sub_category="Earned", normal_balance="credit", paystub_mapping="REGULAR EARNING",
                    is_memo=False, is_active=True),
        ])
        await session.commit()
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def open_period(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
    return period


@pytest_asyncio.fixture
async def journal_period(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 1)
    async with session_factory() as session:
        await period_service.update_status(session, period.period_id, "pending_review")
    async with session_factory() as session:
        period = await period_service.update_status(session, period.period_id, "pending_close")
    return period


@pytest_asyncio.fixture
async def statement_doc(session_factory, open_period):
    async with session_factory() as session:
        doc = Document(
            period_id=open_period.period_id,
            document_type="bank_statement",
            file_name="bank.csv",
            file_path="/tmp/bank.csv",
            source_account_code=100101,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def paystub_doc(session_factory, open_period):
    async with session_factory() as session:
        doc = Document(
            period_id=open_period.period_id,
            document_type="paystub",
            file_name="paystub.pdf",
            file_path="/tmp/paystub.pdf",
            source_account_code=100101,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
    return doc


async def _add_staged_txn(
    session_factory,
    doc: Document,
    description: str,
    amount: Decimal,
    confidence: Decimal = Decimal("0"),
    is_duplicate: bool = False,
) -> RawTransaction:
    async with session_factory() as session:
        txn = RawTransaction(
            document_id=doc.document_id,
            period_id=doc.period_id,
            txn_date=date(2026, 1, 10),
            description=description,
            amount=amount,
            classifier_confidence=confidence,
            is_flagged=False,
            is_duplicate=is_duplicate,
            status="staged",
        )
        session.add(txn)
        await session.commit()
        await session.refresh(txn)
    return txn


# ── service-level tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_updates_suggestion(session_factory, statement_doc, open_period, monkeypatch):
    txn = await _add_staged_txn(session_factory, statement_doc, "GROCERY STORE", Decimal("-45.00"))
    short_id = txn.raw_txn_id.hex[:8]
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[
        TxnSuggestion(id=short_id, account_code=520101, confidence=0.95, reasoning="Grocery store"),
    ]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        count = await classify_service.classify_period(session, open_period.period_id)

    assert count == 1
    async with session_factory() as session:
        updated = await session.get(RawTransaction, txn.raw_txn_id)
    assert updated.suggested_account_code == 520101
    assert updated.classifier_confidence == Decimal("0.95")
    assert updated.is_flagged is False


@pytest.mark.asyncio
async def test_classify_flags_low_confidence(session_factory, statement_doc, open_period, monkeypatch):
    txn = await _add_staged_txn(session_factory, statement_doc, "MYSTERY CHARGE", Decimal("-10.00"))
    short_id = txn.raw_txn_id.hex[:8]
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[
        TxnSuggestion(id=short_id, account_code=520101, confidence=0.5, reasoning="Unclear"),
    ]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        await classify_service.classify_period(session, open_period.period_id)

    async with session_factory() as session:
        updated = await session.get(RawTransaction, txn.raw_txn_id)
    assert updated.is_flagged is True


@pytest.mark.asyncio
async def test_classify_skips_paystub_txns(session_factory, paystub_doc, open_period, monkeypatch):
    await _add_staged_txn(session_factory, paystub_doc, "REGULAR EARNING", Decimal("3000.00"),
                          confidence=Decimal("1.000"))
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        count = await classify_service.classify_period(session, open_period.period_id)

    assert count == 0
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_classify_skips_already_classified(session_factory, statement_doc, open_period, monkeypatch):
    await _add_staged_txn(session_factory, statement_doc, "COFFEE", Decimal("-5.00"),
                          confidence=Decimal("0.90"))
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        count = await classify_service.classify_period(session, open_period.period_id)

    assert count == 0
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_classify_skips_duplicates(session_factory, statement_doc, open_period, monkeypatch):
    await _add_staged_txn(session_factory, statement_doc, "DUP CHARGE", Decimal("-5.00"),
                          is_duplicate=True)
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        count = await classify_service.classify_period(session, open_period.period_id)

    assert count == 0


@pytest.mark.asyncio
async def test_classify_ignores_unknown_account_code(session_factory, statement_doc, open_period, monkeypatch):
    txn = await _add_staged_txn(session_factory, statement_doc, "UNKNOWN MERCHANT", Decimal("-20.00"))
    short_id = txn.raw_txn_id.hex[:8]
    mock_run = AsyncMock(return_value=ClassifierOutput(suggestions=[
        TxnSuggestion(id=short_id, account_code=999999, confidence=0.8, reasoning="?"),
    ]))
    monkeypatch.setattr("app.services.classify.run_classifier", mock_run)

    async with session_factory() as session:
        count = await classify_service.classify_period(session, open_period.period_id)

    assert count == 0
    async with session_factory() as session:
        unchanged = await session.get(RawTransaction, txn.raw_txn_id)
    assert unchanged.suggested_account_code is None
    assert unchanged.is_flagged is True


# ── HTTP route tests ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    async def override_db():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(
        "app.services.classify.run_classifier",
        AsyncMock(return_value=ClassifierOutput(suggestions=[])),
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
async def test_journal_page_renders(client, journal_period):
    response = await client.get(f"/api/v1/periods/{journal_period.period_id}/journal")
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "staged" in data
    assert "approved" in data


@pytest.mark.asyncio
async def test_classify_route_returns_count(client, journal_period):
    response = await client.post(f"/api/v1/periods/{journal_period.period_id}/classify")
    assert response.status_code == 200
    assert "count" in response.json()


@pytest.mark.asyncio
async def test_classify_route_returns_zero_when_nothing_to_classify(client, open_period):
    response = await client.post(f"/api/v1/periods/{open_period.period_id}/classify")
    assert response.status_code == 200
    assert response.json() == {"count": 0}


@pytest.mark.asyncio
async def test_approve_reject_route(client, journal_period, session_factory):
    async with session_factory() as session:
        doc = Document(
            period_id=journal_period.period_id,
            document_type="bank_statement",
            file_name="bank.csv",
            file_path="/tmp/bank.csv",
            source_account_code=100101,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

    txn = await _add_staged_txn(session_factory, doc, "MARKET", Decimal("-30.00"))

    response = await client.post(
        f"/api/v1/periods/{journal_period.period_id}/transactions/{txn.raw_txn_id}/approve"
    )
    assert response.status_code == 200
    async with session_factory() as session:
        updated = await session.get(RawTransaction, txn.raw_txn_id)
    assert updated.status == "approved"

    response = await client.delete(
        f"/api/v1/periods/{journal_period.period_id}/transactions/{txn.raw_txn_id}"
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    async with session_factory() as session:
        remaining = await session.get(RawTransaction, txn.raw_txn_id)
    assert remaining is None


@pytest.mark.asyncio
async def test_update_account_route(client, journal_period, session_factory):
    async with session_factory() as session:
        doc = Document(
            period_id=journal_period.period_id,
            document_type="bank_statement",
            file_name="bank.csv",
            file_path="/tmp/bank.csv",
            source_account_code=100101,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

    txn = await _add_staged_txn(session_factory, doc, "SHOP", Decimal("-12.00"))

    response = await client.patch(
        f"/api/v1/periods/{journal_period.period_id}/transactions/{txn.raw_txn_id}/account",
        json={"account_code": 520101},
    )
    assert response.status_code == 200
    async with session_factory() as session:
        updated = await session.get(RawTransaction, txn.raw_txn_id)
    assert updated.suggested_account_code == 520101
    assert updated.is_flagged is False


# ── scrubbing at the classifier boundary ─────────────────────────────────────
#
# This is where transaction descriptions actually reach an LLM, so it is the
# boundary the scrubber exists to protect. The prompt is redacted; the row in the
# database is not — dedup hashes and the audit trail depend on verbatim text.


def _txn_input(description: str) -> TxnInput:
    return TxnInput(
        id="abcd1234",
        description=description,
        amount=Decimal("-160.00"),
        source_account_name="Checking",
        source_account_type="Asset",
    )


def test_classifier_prompt_redacts_a_p2p_counterparty_name():
    prompt = classify_service._format_txn_inputs(
        [_txn_input("XX3178 MT DDA DEBIT VENMO  Zach John New York NY CNP TX 327676")]
    )
    assert "Zach John" not in prompt
    assert "[NAME]" in prompt
    # The rail survives — it is how the classifier recognizes a P2P transfer.
    assert "VENMO" in prompt


def test_classifier_prompt_redacts_account_numbers():
    prompt = classify_service._format_txn_inputs([_txn_input("ACH XFER ACCT 1234567890")])
    assert "1234567890" not in prompt
    assert "••7890" in prompt


def test_classifier_prompt_keeps_merchant_names_and_amounts():
    # Over-redacting here costs the classifier the only signal it has.
    prompt = classify_service._format_txn_inputs([_txn_input("WAL-MART #5837  ROGERS  AR")])
    assert "WAL-MART #5837  ROGERS  AR" in prompt
    assert "-160.00" in prompt
    assert "Checking" in prompt


def test_classifier_prompt_is_raw_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "scrub_before_llm", False)
    prompt = classify_service._format_txn_inputs([_txn_input("VENMO  Zach John New York NY")])
    assert "Zach John" in prompt


@pytest.mark.asyncio
async def test_classify_scrubs_the_prompt_but_stores_the_verbatim_description(
    session_factory, journal_period, monkeypatch
):
    raw = "XX3178 MT DDA DEBIT VENMO  Zach John New York NY CNP TX 327676"
    async with session_factory() as session:
        doc = Document(
            period_id=journal_period.period_id,
            document_type="bank_statement",
            file_name="bank.csv",
            file_path="/tmp/bank.csv",
            source_account_code=100101,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

    txn = await _add_staged_txn(session_factory, doc, raw, Decimal("-160.00"))

    seen = {}

    async def fake_classifier(prompt: str) -> ClassifierOutput:
        seen["prompt"] = prompt
        return ClassifierOutput(
            suggestions=[
                TxnSuggestion(
                    id=txn.raw_txn_id.hex[:8],
                    account_code=520101,
                    confidence=Decimal("0.9"),
                    reasoning="p2p",
                )
            ]
        )

    monkeypatch.setattr(classify_service, "run_classifier", fake_classifier)
    async with session_factory() as session:
        await classify_service.classify_period(session, journal_period.period_id)

    assert "Zach John" not in seen["prompt"]
    async with session_factory() as session:
        stored = await session.get(RawTransaction, txn.raw_txn_id)
    # Verbatim in the database — the dedup hash in `parse` is computed from it.
    assert stored.description == raw
