import logging
import uuid
from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session, get_period_or_404
from app.models.account import Account
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
from app.models.review_queue import ReviewQueue
from app.schemas.api_responses import (
    AccountCodeRequest,
    CountResult,
    ManualTransactionBatch,
    OperationResult,
)
from app.schemas.raw_transaction import RawTransactionRead
from app.services import document as document_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transactions"], dependencies=[Depends(get_current_user)])


@router.get("/periods/{period_id}/transactions", response_model=list[RawTransactionRead])
async def list_transactions(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    limit: int | None = Query(default=None, ge=1, description="Max rows to return; omit for all."),
    offset: int = Query(default=0, ge=0),
) -> list[RawTransactionRead]:
    query = (
        select(RawTransaction)
        .where(RawTransaction.period_id == period_id)
        .order_by(RawTransaction.txn_date, RawTransaction.created_at)
    )
    # Default (limit omitted) returns all rows, preserving existing client behavior.
    if limit is not None:
        query = query.offset(offset).limit(limit)
    result = await db.scalars(query)
    return [RawTransactionRead.model_validate(t) for t in result.all()]


@router.post("/periods/{period_id}/transactions", response_model=list[RawTransactionRead], status_code=status.HTTP_201_CREATED)
async def add_manual_transactions(
    period_id: uuid.UUID,
    body: ManualTransactionBatch,
    period: Period = Depends(get_period_or_404),
    db: AsyncSession = Depends(get_db_session),
) -> list[RawTransactionRead]:
    if period.status not in ("open", "pending_close"):
        raise HTTPException(status_code=400, detail="Period is not open for new transactions")

    manual_doc = await document_service.get_or_create_manual_document(db, period_id)
    created: list[RawTransaction] = []

    for item in body.transactions:
        try:
            txn_date = date_type.fromisoformat(item.txn_date)
            amount = Decimal(item.amount)
        except (ValueError, InvalidOperation) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid value: {exc}") from exc

        account = await db.get(Account, item.account_code)
        if account is None:
            raise HTTPException(status_code=400, detail=f"Unknown account {item.account_code}")

        txn = RawTransaction(
            document_id=manual_doc.document_id,
            period_id=period_id,
            txn_date=txn_date,
            description=item.description.strip(),
            amount=amount,
            suggested_account_code=item.account_code,
            classifier_confidence=Decimal("1.000"),
            is_flagged=False,
            is_duplicate=False,
            status="staged",
        )
        db.add(txn)
        created.append(txn)

    await db.commit()
    for txn in created:
        await db.refresh(txn)
    logger.info("Added %d manual transaction(s) for period %s", len(created), period_id)
    return [RawTransactionRead.model_validate(t) for t in created]


@router.post("/periods/{period_id}/transactions/{txn_id}/approve", response_model=RawTransactionRead)
async def approve_transaction(
    period_id: uuid.UUID,
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RawTransactionRead:
    txn = await db.get(RawTransaction, txn_id)
    if txn is None or txn.period_id != period_id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.status = "approved"
    await db.commit()
    await db.refresh(txn)
    return RawTransactionRead.model_validate(txn)


@router.post("/periods/{period_id}/transactions/{txn_id}/unapprove", response_model=RawTransactionRead)
async def unapprove_transaction(
    period_id: uuid.UUID,
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> RawTransactionRead:
    txn = await db.get(RawTransaction, txn_id)
    if txn is None or txn.period_id != period_id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    txn.status = "staged"
    await db.commit()
    await db.refresh(txn)
    return RawTransactionRead.model_validate(txn)


@router.delete("/periods/{period_id}/transactions/{txn_id}", response_model=OperationResult)
async def reject_transaction(
    period_id: uuid.UUID,
    txn_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> OperationResult:
    txn = await db.get(RawTransaction, txn_id)
    if txn is None or txn.period_id != period_id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.execute(delete(ReviewQueue).where(ReviewQueue.raw_txn_id == txn_id))
    await db.delete(txn)
    await db.commit()
    logger.info("Rejected transaction %s in period %s", txn_id, period_id)
    return OperationResult(ok=True)


@router.post("/periods/{period_id}/transactions/approve-all-staged", response_model=CountResult)
async def approve_all_staged(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    result = await db.execute(
        update(RawTransaction)
        .where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "staged",
        )
        .values(status="approved")
    )
    await db.commit()
    updated = result.rowcount or 0
    logger.info("Approved all %d staged transactions for period %s", updated, period_id)
    return CountResult(count=updated)


@router.post("/periods/{period_id}/transactions/unapprove-all", response_model=CountResult)
async def unapprove_all(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    result = await db.execute(
        update(RawTransaction)
        .where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "approved",
        )
        .values(status="staged")
    )
    await db.commit()
    updated = result.rowcount or 0
    logger.info("Unapproved all %d transactions for period %s", updated, period_id)
    return CountResult(count=updated)


@router.post("/periods/{period_id}/transactions/reject-all-staged", response_model=CountResult)
async def reject_all_staged(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    staged_ids_result = await db.scalars(
        select(RawTransaction.raw_txn_id).where(
            RawTransaction.period_id == period_id,
            RawTransaction.status == "staged",
        )
    )
    staged_ids = staged_ids_result.all()
    deleted = len(staged_ids)
    if staged_ids:
        await db.execute(delete(ReviewQueue).where(ReviewQueue.raw_txn_id.in_(staged_ids)))
        await db.execute(delete(RawTransaction).where(RawTransaction.raw_txn_id.in_(staged_ids)))
        await db.commit()
    logger.info("Rejected all %d staged transactions for period %s", deleted, period_id)
    return CountResult(count=deleted)


@router.post("/periods/{period_id}/transactions/clear-all", response_model=CountResult)
async def clear_all_transactions(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> CountResult:
    txn_ids_result = await db.scalars(
        select(RawTransaction.raw_txn_id).where(
            RawTransaction.period_id == period_id,
            RawTransaction.status.in_(["staged", "approved"]),
        )
    )
    txn_ids = txn_ids_result.all()
    deleted = len(txn_ids)
    if txn_ids:
        await db.execute(delete(ReviewQueue).where(ReviewQueue.raw_txn_id.in_(txn_ids)))
        await db.execute(delete(RawTransaction).where(RawTransaction.raw_txn_id.in_(txn_ids)))
        await db.commit()
    logger.info("Cleared all %d transactions for period %s", deleted, period_id)
    return CountResult(count=deleted)


@router.patch("/periods/{period_id}/transactions/{txn_id}/account", response_model=RawTransactionRead)
async def update_transaction_account(
    period_id: uuid.UUID,
    txn_id: uuid.UUID,
    body: AccountCodeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RawTransactionRead:
    txn = await db.get(RawTransaction, txn_id)
    if txn is None or txn.period_id != period_id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    account = await db.get(Account, body.account_code)
    if account is None:
        raise HTTPException(status_code=400, detail=f"Unknown account {body.account_code}")
    txn.suggested_account_code = body.account_code
    txn.classifier_confidence = Decimal("1.000")
    await db.commit()
    await db.refresh(txn)
    return RawTransactionRead.model_validate(txn)
