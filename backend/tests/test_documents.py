"""Tests for the Document resource — service + HTTP routes."""

from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.databases import Base
from app.dependencies import get_current_user, get_db_session
from app.models.user import User
from app.main import app
from app.models.document import Document
from app.services import document as document_service
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


@pytest_asyncio.fixture
async def open_period(session_factory):
    async with session_factory() as session:
        period = await period_service.create_period(session, 2026, 4)
    return period


@pytest.fixture(autouse=True)
def isolate_uploads(tmp_path, monkeypatch):
    """Redirect uploads to a per-test tmp dir so we don't litter the repo."""
    monkeypatch.setattr(document_service, "UPLOAD_ROOT", tmp_path / "uploads")


# ── HTTP route tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient, session_factory, open_period):
    files = {"file": ("statement.pdf", BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
    data = {"document_type": "bank_statement"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["parse_status"] == "pending"
    assert body["file_name"] == "statement.pdf"

    async with session_factory() as session:
        doc = await session.scalar(select(Document))
    assert doc is not None
    assert Path(doc.file_path).exists()


@pytest.mark.asyncio
async def test_upload_without_document_type_defaults_to_unknown(
    client: AsyncClient, session_factory, open_period
):
    """When the client omits document_type, the upload should still succeed
    with document_type='unknown' so the orchestrator can classify it later."""
    files = {"file": ("statement.pdf", BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        files=files,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["document_type"] == "unknown"
    assert body["source_account_code"] is None
    assert body["parse_status"] == "pending"


@pytest.mark.asyncio
async def test_upload_mortgage_statement(client: AsyncClient, session_factory, open_period):
    files = {"file": ("mortgage.pdf", BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
    data = {"document_type": "mortgage_statement"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 201
    assert response.json()["document_type"] == "mortgage_statement"


@pytest.mark.asyncio
async def test_upload_rejects_invalid_extension(
    client: AsyncClient, session_factory, open_period
):
    files = {"file": ("notes.txt", BytesIO(b"hello"), "text/plain")}
    data = {"document_type": "manual"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]

    async with session_factory() as session:
        count = await session.scalar(select(Document))
    assert count is None


@pytest.mark.asyncio
async def test_upload_rejects_invalid_document_type(
    client: AsyncClient, session_factory, open_period
):
    files = {"file": ("statement.pdf", BytesIO(b"%PDF"), "application/pdf")}
    data = {"document_type": "not_a_type"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert "Invalid document_type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_duplicate_filename_gets_suffix(
    client: AsyncClient, session_factory, open_period
):
    data = {"document_type": "manual"}
    for _ in range(2):
        files = {"file": ("file.csv", BytesIO(b"a,b\n1,2\n"), "text/csv")}
        response = await client.post(
            f"/api/v1/periods/{open_period.period_id}/documents",
            data=data,
            files=files,
        )
        assert response.status_code == 201

    async with session_factory() as session:
        result = await session.scalars(select(Document))
        docs = result.all()
    assert len(docs) == 2
    paths = {d.file_path for d in docs}
    assert len(paths) == 2  # distinct file paths on disk


@pytest.mark.asyncio
async def test_upload_filename_with_path_traversal_is_contained(
    client: AsyncClient, session_factory, open_period
):
    """A crafted filename must not escape the period's upload directory, and the
    stored file_name must be reduced to a bare basename."""
    files = {"file": ("../../../evil.pdf", BytesIO(b"%PDF"), "application/pdf")}
    data = {"document_type": "bank_statement"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 201
    assert response.json()["file_name"] == "evil.pdf"

    period_dir = (document_service.UPLOAD_ROOT / str(open_period.period_id)).resolve()
    async with session_factory() as session:
        doc = await session.scalar(select(Document))
    assert doc is not None
    stored = Path(doc.file_path).resolve()
    assert stored.is_relative_to(period_dir)
    assert stored.exists()


@pytest.mark.asyncio
async def test_upload_blocked_when_period_not_open(
    client: AsyncClient, session_factory, open_period
):
    async with session_factory() as session:
        await period_service.update_status(
            session, open_period.period_id, "pending_review"
        )

    files = {"file": ("statement.pdf", BytesIO(b"%PDF"), "application/pdf")}
    data = {"document_type": "bank_statement"}
    response = await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents",
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert "open period" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, session_factory, open_period):
    files = {"file": ("statement.pdf", BytesIO(b"%PDF"), "application/pdf")}
    data = {"document_type": "bank_statement"}
    await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents", data=data, files=files
    )

    async with session_factory() as session:
        doc = await session.scalar(select(Document))
    assert doc is not None
    file_path = Path(doc.file_path)
    assert file_path.exists()

    response = await client.delete(
        f"/api/v1/periods/{open_period.period_id}/documents/{doc.document_id}"
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with session_factory() as session:
        remaining = await session.scalar(select(Document))
    assert remaining is None
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_delete_document_cascades_to_parsed_data(
    client: AsyncClient, session_factory, open_period
):
    """Deleting a parsed (and posted) document must cascade through
    raw_transactions, review_queue entries, and journal_entries/lines."""
    import uuid
    from datetime import date
    from decimal import Decimal

    from app.models.journal import JournalEntry, JournalLine
    from app.models.raw_transaction import RawTransaction
    from app.models.review_queue import ReviewQueue

    files = {"file": ("statement.pdf", BytesIO(b"%PDF"), "application/pdf")}
    data = {"document_type": "bank_statement"}
    await client.post(
        f"/api/v1/periods/{open_period.period_id}/documents", data=data, files=files
    )

    async with session_factory() as session:
        doc = await session.scalar(select(Document))
        assert doc is not None
        doc_id = doc.document_id
        period_id = doc.period_id

        entry_id = uuid.uuid4()
        session.add(JournalEntry(
            entry_id=entry_id,
            period_id=period_id,
            entry_date=date(2026, 4, 1),
            description="test",
            source_type="statement",
            source_document_id=doc_id,
            created_by="python",
        ))
        session.add(JournalLine(
            entry_id=entry_id, account_code=1000,
            debit_amount=Decimal("10"), credit_amount=Decimal("0"),
        ))
        session.add(JournalLine(
            entry_id=entry_id, account_code=2000,
            debit_amount=Decimal("0"), credit_amount=Decimal("10"),
        ))

        raw_id = uuid.uuid4()
        session.add(RawTransaction(
            raw_txn_id=raw_id,
            document_id=doc_id,
            period_id=period_id,
            txn_date=date(2026, 4, 1),
            description="test txn",
            amount=Decimal("10"),
            status="posted",
            journal_entry_id=entry_id,
        ))
        session.add(ReviewQueue(
            period_id=period_id,
            raw_txn_id=raw_id,
            review_type="unclassified",
        ))
        await session.commit()

    response = await client.delete(
        f"/api/v1/periods/{period_id}/documents/{doc_id}"
    )
    assert response.status_code == 200

    async with session_factory() as session:
        assert await session.scalar(select(Document)) is None
        assert await session.scalar(select(RawTransaction)) is None
        assert await session.scalar(select(ReviewQueue)) is None
        assert await session.scalar(select(JournalEntry)) is None
        assert await session.scalar(select(JournalLine)) is None
