import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.models.document import Document
from app.schemas.api_responses import CountResult, OperationResult, SourceAccountRequest
from app.schemas.document import DocumentRead
from app.services import classify as classify_service
from app.services import document as document_service
from app.services import journal as journal_service
from app.services import parse as parse_service
from app.services.file_readers import ParseError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"], dependencies=[Depends(get_current_user)])


@router.post("/periods/{period_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    period_id: uuid.UUID,
    file: UploadFile = File(...),
    document_type: str = Form("unknown"),
    source_account_code: int | None = Form(None),
    db: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    try:
        doc = await document_service.save_upload(
            db,
            period_id=period_id,
            upload=file,
            document_type=document_type,
            source_account_code=source_account_code,
        )
    except document_service.DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentRead.model_validate(doc)


@router.delete("/periods/{period_id}/documents/{document_id}", response_model=OperationResult)
async def delete_document(
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> OperationResult:
    try:
        await document_service.delete_document(db, document_id)
    except document_service.DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Deleted document %s from period %s", document_id, period_id)
    return OperationResult(ok=True)


@router.post("/periods/{period_id}/documents/{document_id}/parse", response_model=DocumentRead)
async def parse_document(
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    doc = await db.get(Document, document_id)
    if doc is None or doc.period_id != period_id:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        await parse_service.parse_document(db, document_id=document_id)
    except ParseError as exc:
        logger.info("Parse refused for document %s: %s", document_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Parse failed for document %s: %s", document_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Document parsing failed") from exc

    await db.refresh(doc)

    if doc.document_type in ("bank_statement", "credit_card"):
        try:
            updated = await classify_service.classify_period(db, period_id)
            logger.info("Auto-classified %d transactions after parsing document %s", updated, document_id)
        except Exception:
            logger.exception("Auto-classification failed after parsing document %s — continuing", document_id)

    return DocumentRead.model_validate(doc)


@router.post("/periods/{period_id}/documents/{document_id}/unpost", response_model=CountResult)
async def unpost_document(
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    unposted = await journal_service.unpost_document(db, document_id, period_id)
    logger.info("Unposted %d transactions for document %s in period %s", unposted, document_id, period_id)
    return CountResult(count=unposted)


@router.patch("/periods/{period_id}/documents/{document_id}/source-account", response_model=DocumentRead)
async def set_source_account(
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    body: SourceAccountRequest,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    doc = await db.get(Document, document_id)
    if doc is None or doc.period_id != period_id:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        updated = await document_service.update_source_account(db, document_id, body.source_account_code)
    except document_service.DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentRead.model_validate(updated)
