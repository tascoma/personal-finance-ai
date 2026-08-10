"""Document service — uploaded source files for a period.

Owns the file-system writes and DB rows for documents. No LLM calls live here;
parsing happens later in the Parse phase. Documents always start at
`parse_status = "pending"`.
"""

import logging
import uuid
from collections.abc import Sequence
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
from app.models.review_queue import ReviewQueue

logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"

ALLOWED_DOCUMENT_TYPES: frozenset[str] = frozenset(
    {"paystub", "bank_statement", "credit_card", "investment", "mortgage_statement", "manual", "opening_balances", "unknown"}
)
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".csv", ".xlsx"})


class DocumentError(Exception):
    """Raised for invalid document operations (bad input, missing rows, closed periods)."""


def _unique_destination(directory: Path, file_name: str) -> Path:
    """Return a path inside `directory` that does not collide with an existing file.

    If `file_name` is free, use it. Otherwise append a short UUID suffix to the stem
    so we never silently overwrite a previous upload.
    """
    candidate = directory / file_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    return directory / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"


async def save_upload(
    db: AsyncSession,
    period_id: uuid.UUID,
    upload: UploadFile,
    document_type: str = "unknown",
    source_account_code: int | None = None,
) -> Document:
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise DocumentError(f"Invalid document_type: {document_type}")

    # Reduce the client-supplied filename to a bare basename before using it for
    # any filesystem path — an untrusted multipart filename like "../../foo.pdf"
    # would otherwise escape the period directory on both write and later unlink.
    file_name = Path(upload.filename or "").name
    extension = Path(file_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentError(
            f"Unsupported file extension: {extension or '(none)'}"
        )

    period = await db.get(Period, period_id)
    if period is None:
        raise DocumentError("Period not found")
    if period.status != "open":
        raise DocumentError("Documents can only be uploaded to an open period")

    directory = UPLOAD_ROOT / str(period_id)
    directory.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(directory, file_name)
    # Defence in depth: never let a destination resolve outside the period dir.
    if not destination.resolve().is_relative_to(directory.resolve()):
        raise DocumentError("Invalid file name")

    # Stream to disk in chunks and abort the moment the size limit is exceeded, so a
    # large upload is never fully buffered in memory before being rejected.
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    bytes_written = 0
    chunk_size = 1024 * 1024
    try:
        with destination.open("wb") as out:
            while chunk := await upload.read(chunk_size):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise DocumentError(
                        f"File exceeds maximum upload size of {settings.max_upload_size_mb} MB"
                    )
                out.write(chunk)
    except DocumentError:
        destination.unlink(missing_ok=True)
        raise

    document = Document(
        period_id=period_id,
        document_type=document_type,
        file_name=file_name,
        file_path=str(destination),
        source_account_code=source_account_code,
        parse_status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    logger.info(
        "Uploaded document %s (%s) for period %s",
        document.document_id,
        document_type,
        period_id,
    )
    return document


async def list_documents(
    db: AsyncSession, period_id: uuid.UUID
) -> Sequence[Document]:
    result = await db.scalars(
        select(Document)
        .where(Document.period_id == period_id)
        .order_by(Document.created_at)
    )
    return result.all()


async def get_or_create_manual_document(
    db: AsyncSession,
    period_id: uuid.UUID,
) -> Document:
    """Return the single shared manual document for the period, creating it if needed."""
    result = await db.scalars(
        select(Document).where(
            Document.period_id == period_id,
            Document.document_type == "manual",
        )
    )
    doc = result.first()
    if doc is not None:
        return doc

    doc = Document(
        period_id=period_id,
        document_type="manual",
        file_name="manual-entries",
        file_path="manual",
        source_account_code=None,
        parse_status="complete",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    logger.info("Created manual document for period %s", period_id)
    return doc


async def update_source_account(
    db: AsyncSession,
    document_id: uuid.UUID,
    source_account_code: int | None,
) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise DocumentError("Document not found")
    document.source_account_code = source_account_code
    await db.commit()
    await db.refresh(document)
    logger.info("Updated source account for document %s to %s", document_id, source_account_code)
    return document


async def delete_document(db: AsyncSession, document_id: uuid.UUID) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        raise DocumentError("Document not found")

    raw_txn_subq = select(RawTransaction.raw_txn_id).where(
        RawTransaction.document_id == document_id
    )
    entry_subq = select(JournalEntry.entry_id).where(
        JournalEntry.source_document_id == document_id
    )

    await db.execute(delete(ReviewQueue).where(ReviewQueue.raw_txn_id.in_(raw_txn_subq)))
    await db.execute(delete(JournalLine).where(JournalLine.entry_id.in_(entry_subq)))
    await db.execute(delete(JournalEntry).where(JournalEntry.source_document_id == document_id))
    await db.execute(delete(RawTransaction).where(RawTransaction.document_id == document_id))
    await db.execute(delete(Document).where(Document.document_id == document_id))

    Path(document.file_path).unlink(missing_ok=True)
    await db.commit()
    logger.info("Deleted document %s", document_id)
