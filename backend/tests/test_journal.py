"""Tests for the Journal phase — posting service + HTTP routes.

All posting logic is deterministic Python, so no LLM stubs are needed for
service-level tests. HTTP route tests stub the classifier dependency to prevent
API calls during the full app test client setup.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.models.user import User
from app.main import app
from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.raw_transaction import RawTransaction
from app.services import journal as journal_service
from app.services import period as period_service
from app.services.journal import JournalError

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
            Account(account_code=400101, account_name="Salary - Regular", account_type="Income",
                    sub_category="Earned", normal_balance="credit", paystub_mapping="REGULAR EARNING",
                    is_memo=False, is_active=True),
            Account(account_code=520101, account_name="Groceries", account_type="Expense",
                    sub_category="Food", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=570101, account_name="Federal Income Tax", account_type="Expense",
                    sub_category="Payroll Taxes", normal_balance="debit", paystub_mapping="FEDERAL TAX",
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


async def _make_doc(session_factory, period_id, doc_type="bank_statement", source_code=100101):
    async with session_factory() as session:
        doc = Document(
            period_id=period_id,
            document_type=doc_type,
            file_name="test.csv",
            file_path="/tmp/test.csv",
            source_account_code=source_code,
            parse_status="complete",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
    return doc


async def _make_txn(
    session_factory,
    doc: Document,
    description: str,
    amount: Decimal,
    suggested_account_code: int | None,
    txn_status: str = "approved",
) -> RawTransaction:
    async with session_factory() as session:
        txn = RawTransaction(
            document_id=doc.document_id,
            period_id=doc.period_id,
            txn_date=date(2026, 1, 10),
            description=description,
            amount=amount,
            suggested_account_code=suggested_account_code,
            classifier_confidence=Decimal("0.95"),
            is_flagged=False,
            is_duplicate=False,
            status=txn_status,
        )
        session.add(txn)
        await session.commit()
        await session.refresh(txn)
    return txn


# ── service-level tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_statement_outflow_debits_category(session_factory, open_period):
    """Expense (amount < 0): debit category, credit source."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERY STORE", Decimal("-45.00"), 520101)

    async with session_factory() as session:
        count = await journal_service.post_period(session, open_period.period_id)

    assert count == 1
    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
        lines = (await session.scalars(select(JournalLine))).all()

    assert len(entries) == 1
    assert len(lines) == 2
    by_account = {line.account_code: line for line in lines}
    assert by_account[520101].debit_amount == Decimal("45.00")   # Groceries debit
    assert by_account[520101].credit_amount == Decimal("0")
    assert by_account[100101].credit_amount == Decimal("45.00")  # Checking credit
    assert by_account[100101].debit_amount == Decimal("0")


@pytest.mark.asyncio
async def test_post_statement_inflow_debits_source(session_factory, open_period):
    """Income (amount > 0): debit source, credit category."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "DIRECT DEPOSIT", Decimal("2000.00"), 400101)

    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        lines = (await session.scalars(select(JournalLine))).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[100101].debit_amount == Decimal("2000.00")  # Checking debit
    assert by_account[400101].credit_amount == Decimal("2000.00")  # Income credit


@pytest.mark.asyncio
async def test_post_cc_charge_credits_liability(session_factory, open_period):
    """CC charge (Liability source, amount < 0): debit expense, credit liability."""
    doc = await _make_doc(session_factory, open_period.period_id,
                          doc_type="credit_card", source_code=200101)
    await _make_txn(session_factory, doc, "AMAZON", Decimal("-30.00"), 520101)

    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        lines = (await session.scalars(select(JournalLine))).all()

    by_account = {line.account_code: line for line in lines}
    assert by_account[520101].debit_amount == Decimal("30.00")   # Groceries debit
    assert by_account[200101].credit_amount == Decimal("30.00")  # Mastercard credit


@pytest.mark.asyncio
async def test_post_paystub_balanced_entry(session_factory, open_period):
    """Paystub: earning (+) credits income; tax (-) debits expense; net debits checking."""
    doc = await _make_doc(session_factory, open_period.period_id,
                          doc_type="paystub", source_code=100101)
    await _make_txn(session_factory, doc, "REGULAR EARNING", Decimal("4500.00"), 400101)
    await _make_txn(session_factory, doc, "FEDERAL TAX", Decimal("-800.00"), 570101)

    async with session_factory() as session:
        count = await journal_service.post_period(session, open_period.period_id)

    assert count == 1  # one entry for the whole paystub doc

    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
        lines = (await session.scalars(select(JournalLine))).all()

    assert len(entries) == 1
    assert entries[0].source_type == "paystub"
    assert len(lines) == 3  # income credit, tax debit, net pay debit

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    assert total_debits == total_credits  # balanced

    by_account = {line.account_code: line for line in lines}
    assert by_account[400101].credit_amount == Decimal("4500.00")
    assert by_account[570101].debit_amount == Decimal("800.00")
    assert by_account[100101].debit_amount == Decimal("3700.00")  # net pay


@pytest.mark.asyncio
async def test_post_mortgage_single_balanced_entry(session_factory, open_period):
    """Mortgage statement: all components post as ONE balanced entry.

    Expected lines for the May statement:
      Debit  Mortgage Interest   1,722.97
      Debit  Mortgage Payable      267.62
      Debit  Escrow Account        316.97
      Credit Checking             2,307.56
    """
    async with session_factory() as session:
        session.add_all([
            Account(account_code=210102, account_name="Mortgage Payable", account_type="Liability",
                    sub_category="Long-term Debt", normal_balance="credit", is_memo=False, is_active=True),
            Account(account_code=510101, account_name="Mortgage Interest", account_type="Expense",
                    sub_category="Housing", normal_balance="debit", is_memo=False, is_active=True),
            Account(account_code=100202, account_name="Escrow Account", account_type="Asset",
                    sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True),
        ])
        await session.commit()

    doc = await _make_doc(session_factory, open_period.period_id,
                          doc_type="mortgage_statement", source_code=100101)
    # Parse stores components as negative outflows from checking.
    await _make_txn(session_factory, doc, "Mortgage Principal", Decimal("-267.62"), 210102)
    await _make_txn(session_factory, doc, "Mortgage Interest", Decimal("-1722.97"), 510101)
    await _make_txn(session_factory, doc, "Escrow Deposit", Decimal("-316.97"), 100202)

    async with session_factory() as session:
        count = await journal_service.post_period(session, open_period.period_id)

    assert count == 1  # one entry for the whole mortgage statement

    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
        lines = (await session.scalars(select(JournalLine))).all()

    assert len(entries) == 1
    assert entries[0].source_type == "statement"
    assert entries[0].source_document_id == doc.document_id
    assert len(lines) == 4

    by_account = {line.account_code: line for line in lines}
    assert by_account[510101].debit_amount == Decimal("1722.97")  # Mortgage Interest
    assert by_account[210102].debit_amount == Decimal("267.62")   # Mortgage Payable
    assert by_account[100202].debit_amount == Decimal("316.97")   # Escrow
    assert by_account[100101].credit_amount == Decimal("2307.56") # Checking

    total_debits = sum(line.debit_amount for line in lines)
    total_credits = sum(line.credit_amount for line in lines)
    assert total_debits == total_credits == Decimal("2307.56")


@pytest.mark.asyncio
async def test_post_paystub_no_source_skipped(session_factory, open_period):
    """Paystub with no source_account_code is skipped — no entry created."""
    doc = await _make_doc(session_factory, open_period.period_id,
                          doc_type="paystub", source_code=None)
    async with session_factory() as session:
        d = await session.get(Document, doc.document_id)
        d.source_account_code = None
        await session.commit()

    await _make_txn(session_factory, doc, "REGULAR EARNING", Decimal("3000.00"), 400101)

    async with session_factory() as session:
        count = await journal_service.post_period(session, open_period.period_id)

    assert count == 0


@pytest.mark.asyncio
async def test_post_skips_staged_txns(session_factory, open_period):
    """Only 'approved' transactions are posted; staged ones are ignored."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "STAGED TXN", Decimal("-10.00"), 520101, txn_status="staged")

    async with session_factory() as session:
        count = await journal_service.post_period(session, open_period.period_id)

    assert count == 0


@pytest.mark.asyncio
async def test_post_marks_txn_posted(session_factory, open_period):
    """After posting, raw_txn.status='posted' and journal_entry_id is set."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    txn = await _make_txn(session_factory, doc, "COFFEE", Decimal("-5.00"), 520101)

    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        updated = await session.get(RawTransaction, txn.raw_txn_id)

    assert updated.status == "posted"
    assert updated.journal_entry_id is not None


@pytest.mark.asyncio
async def test_post_entry_balance_is_verified():
    """_build_paystub_entry raises JournalError when net pay <= 0."""
    checking = Account(account_code=100101, account_name="Checking", account_type="Asset",
                       sub_category="Cash", normal_balance="debit", is_memo=False, is_active=True)
    income = Account(account_code=400101, account_name="Salary", account_type="Income",
                     sub_category="Earned", normal_balance="credit", is_memo=False, is_active=True)
    accounts = {100101: checking, 400101: income}

    doc = Document(
        document_id=uuid.uuid4(),
        period_id=uuid.uuid4(),
        document_type="paystub",
        file_name="p.pdf",
        file_path="/tmp/p.pdf",
        source_account_code=100101,
        parse_status="complete",
    )

    txns = [RawTransaction(
        raw_txn_id=uuid.uuid4(),
        document_id=doc.document_id,
        period_id=doc.period_id,
        txn_date=date(2026, 1, 10),
        description="TAX",
        amount=Decimal("-500"),
        suggested_account_code=400101,
        classifier_confidence=Decimal("1.000"),
        is_flagged=False,
        is_duplicate=False,
        status="approved",
    )]

    with pytest.raises(JournalError, match="net pay"):
        journal_service._build_paystub_entries(doc, txns, accounts)


# ── HTTP route tests ──────────────────────────────────────────────────────────


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
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_journal_page_renders(client, journal_period):
    response = await client.get(f"/api/v1/periods/{journal_period.period_id}/journal")
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "staged" in data
    assert "entries" in data


@pytest.mark.asyncio
async def test_post_route_creates_entries(client, journal_period, session_factory):
    doc = await _make_doc(session_factory, journal_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERIES", Decimal("-40.00"), 520101)

    response = await client.post(f"/api/v1/periods/{journal_period.period_id}/post")
    assert response.status_code == 200
    assert response.json()["count"] == 1

    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_post_route_blocked_outside_journal_phase(client, open_period):
    """POST /post is blocked when period is not pending_close."""
    response = await client.post(f"/api/v1/periods/{open_period.period_id}/post")
    assert response.status_code == 400
    assert "journal phase" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_journal_page_shows_posted_entries(client, journal_period, session_factory):
    doc = await _make_doc(session_factory, journal_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "COFFEE", Decimal("-5.00"), 520101)

    await client.post(f"/api/v1/periods/{journal_period.period_id}/post")

    response = await client.get(f"/api/v1/periods/{journal_period.period_id}/journal")
    assert response.status_code == 200
    data = response.json()
    assert any("COFFEE" in e["description"] for e in data["entries"])


# ── manual journal entry service tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_manual_entry_balanced(session_factory, open_period):
    """A balanced manual entry creates one JournalEntry and matching lines."""
    async with session_factory() as session:
        entry = await journal_service.create_manual_entry(
            session,
            period_id=open_period.period_id,
            entry_date=date(2026, 1, 15),
            description="Depreciation",
            source_type="adjusting",
            lines=[
                (570101, Decimal("100.00"), Decimal("0"), None),
                (520101, Decimal("0"), Decimal("100.00"), "contra"),
            ],
        )

    assert entry.source_type == "adjusting"
    assert entry.is_adjusting is True
    assert entry.created_by == "user"

    async with session_factory() as session:
        lines = (await session.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()

    assert len(lines) == 2
    total_debits = sum(l.debit_amount for l in lines)
    total_credits = sum(l.credit_amount for l in lines)
    assert total_debits == total_credits == Decimal("100.00")


@pytest.mark.asyncio
async def test_create_manual_entry_unbalanced_raises(session_factory, open_period):
    async with session_factory() as session:
        with pytest.raises(journal_service.JournalError, match="balance"):
            await journal_service.create_manual_entry(
                session,
                period_id=open_period.period_id,
                entry_date=date(2026, 1, 15),
                description="Bad entry",
                source_type="manual",
                lines=[
                    (520101, Decimal("50.00"), Decimal("0"), None),
                    (100101, Decimal("0"), Decimal("40.00"), None),
                ],
            )


@pytest.mark.asyncio
async def test_create_manual_entry_empty_raises(session_factory, open_period):
    async with session_factory() as session:
        with pytest.raises(journal_service.JournalError, match="at least one"):
            await journal_service.create_manual_entry(
                session,
                period_id=open_period.period_id,
                entry_date=date(2026, 1, 15),
                description="Empty",
                source_type="manual",
                lines=[],
            )


@pytest.mark.asyncio
async def test_delete_manual_entry(session_factory, open_period):
    async with session_factory() as session:
        entry = await journal_service.create_manual_entry(
            session,
            period_id=open_period.period_id,
            entry_date=date(2026, 1, 15),
            description="To delete",
            source_type="manual",
            lines=[
                (100101, Decimal("200.00"), Decimal("0"), None),
                (520101, Decimal("0"), Decimal("200.00"), None),
            ],
        )

    async with session_factory() as session:
        await journal_service.delete_manual_entry(session, entry.entry_id, open_period.period_id)

    async with session_factory() as session:
        assert await session.get(JournalEntry, entry.entry_id) is None
        lines = (await session.scalars(
            select(JournalLine).where(JournalLine.entry_id == entry.entry_id)
        )).all()
        assert lines == []


@pytest.mark.asyncio
async def test_delete_non_user_entry_raises(session_factory, open_period):
    """Entries created by 'python' (auto-posted) cannot be deleted."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERIES", Decimal("-30.00"), 520101)
    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)
    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
        assert len(entries) == 1
        entry_id = entries[0].entry_id
    async with session_factory() as session:
        with pytest.raises(journal_service.JournalError, match="manually-created"):
            await journal_service.delete_manual_entry(session, entry_id, open_period.period_id)


# ── manual journal entry HTTP route tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_manual_entry_route(client, open_period, session_factory):
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/journal/entries",
        json={
            "entry_date": "2026-01-20",
            "description": "Prepaid Insurance",
            "source_type": "adjusting",
            "lines": [
                {"account_code": 100101, "debit": "500.00", "credit": "0", "memo": None},
                {"account_code": 520101, "debit": "0", "credit": "500.00", "memo": "insurance"},
            ],
        },
    )
    assert response.status_code == 201

    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
    assert len(entries) == 1
    assert entries[0].description == "Prepaid Insurance"
    assert entries[0].created_by == "user"


@pytest.mark.asyncio
async def test_create_manual_entry_route_unbalanced(client, open_period):
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/journal/entries",
        json={
            "entry_date": "2026-01-20",
            "description": "Bad",
            "source_type": "manual",
            "lines": [
                {"account_code": 100101, "debit": "100.00", "credit": "0", "memo": None},
                {"account_code": 520101, "debit": "0", "credit": "50.00", "memo": None},
            ],
        },
    )
    assert response.status_code == 400
    assert "balance" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_manual_entry_route(client, open_period, session_factory):
    async with session_factory() as session:
        entry = await journal_service.create_manual_entry(
            session,
            period_id=open_period.period_id,
            entry_date=date(2026, 1, 20),
            description="To delete via route",
            source_type="manual",
            lines=[
                (100101, Decimal("75.00"), Decimal("0"), None),
                (520101, Decimal("0"), Decimal("75.00"), None),
            ],
        )

    response = await client.delete(
        f"/api/v1/periods/{open_period.period_id}/journal/entries/{entry.entry_id}"
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with session_factory() as session:
        assert await session.get(JournalEntry, entry.entry_id) is None


# ── unpost_document tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unpost_document_resets_transactions(session_factory, open_period):
    """unpost_document sets posted txns back to approved and clears journal_entry_id."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERY STORE", Decimal("-45.00"), 520101)
    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        count = await journal_service.unpost_document(session, doc.document_id, open_period.period_id)

    assert count == 1
    async with session_factory() as session:
        txns = (await session.scalars(
            select(RawTransaction).where(RawTransaction.document_id == doc.document_id)
        )).all()
    assert all(t.status == "approved" for t in txns)
    assert all(t.journal_entry_id is None for t in txns)


@pytest.mark.asyncio
async def test_unpost_document_deletes_entries_and_lines(session_factory, open_period):
    """unpost_document removes the JournalEntry and JournalLine rows."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERY STORE", Decimal("-45.00"), 520101)
    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        await journal_service.unpost_document(session, doc.document_id, open_period.period_id)

    async with session_factory() as session:
        entries = (await session.scalars(select(JournalEntry))).all()
        lines = (await session.scalars(select(JournalLine))).all()
    assert entries == []
    assert lines == []


@pytest.mark.asyncio
async def test_unpost_document_noop_when_nothing_posted(session_factory, open_period):
    """unpost_document returns 0 and leaves the DB unchanged when nothing is posted."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    await _make_txn(session_factory, doc, "GROCERY STORE", Decimal("-45.00"), 520101)

    async with session_factory() as session:
        count = await journal_service.unpost_document(session, doc.document_id, open_period.period_id)

    assert count == 0


@pytest.mark.asyncio
async def test_unpost_document_only_affects_target_document(session_factory, open_period):
    """unpost_document leaves transactions from other documents untouched."""
    doc_cc = await _make_doc(session_factory, open_period.period_id, doc_type="credit_card", source_code=200101)
    doc_bank = await _make_doc(session_factory, open_period.period_id, doc_type="bank_statement", source_code=100101)
    await _make_txn(session_factory, doc_cc, "CC CHARGE", Decimal("-30.00"), 520101)
    await _make_txn(session_factory, doc_bank, "ATM WITHDRAWAL", Decimal("-20.00"), 520101)
    async with session_factory() as session:
        await journal_service.post_period(session, open_period.period_id)

    async with session_factory() as session:
        count = await journal_service.unpost_document(session, doc_cc.document_id, open_period.period_id)

    assert count == 1
    async with session_factory() as session:
        bank_txn = (await session.scalars(
            select(RawTransaction).where(RawTransaction.document_id == doc_bank.document_id)
        )).one()
    assert bank_txn.status == "posted"


@pytest.mark.asyncio
async def test_unpost_document_route(client, journal_period, session_factory):
    """POST /unpost removes staged/approved transactions from a document."""
    doc = await _make_doc(session_factory, journal_period.period_id, doc_type="credit_card", source_code=100101)
    await _make_txn(session_factory, doc, "CC CHARGE", Decimal("-50.00"), 520101)
    await client.post(f"/api/v1/periods/{journal_period.period_id}/post")

    response = await client.post(
        f"/api/v1/periods/{journal_period.period_id}/documents/{doc.document_id}/unpost"
    )
    assert response.status_code == 200

    async with session_factory() as session:
        txn = (await session.scalars(
            select(RawTransaction).where(RawTransaction.document_id == doc.document_id)
        )).one()
    assert txn.status == "approved"
    assert txn.journal_entry_id is None


@pytest.mark.asyncio
async def test_unpost_document_route_no_staged_returns_zero(client, open_period, session_factory):
    """Unpost with no staged/approved transactions returns count=0."""
    doc = await _make_doc(session_factory, open_period.period_id, source_code=100101)
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents/{doc.document_id}/unpost"
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0
