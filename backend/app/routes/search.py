import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db_session
from app.models.account import Account
from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
from app.schemas.search import SearchHit, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"], dependencies=[Depends(get_current_user)])


@router.get("/search", response_model=SearchResponse)
async def global_search(
    q: str = Query(min_length=1, max_length=100),
    limit_per_type: int = Query(default=6, ge=1, le=20),
    db: AsyncSession = Depends(get_db_session),
) -> SearchResponse:
    terms = q.split()
    if not terms:
        return SearchResponse(query=q, hits=[])

    hits: list[SearchHit] = []

    # Accounts — match name or (numeric) account code.
    account_filters = [
        Account.account_name.ilike(f"%{t}%") | cast(Account.account_code, String).ilike(f"%{t}%")
        for t in terms
    ]
    accounts = await db.scalars(
        select(Account).where(*account_filters).order_by(Account.account_code).limit(limit_per_type)
    )
    for acc in accounts.all():
        hits.append(
            SearchHit(
                type="account",
                id=str(acc.account_code),
                title=acc.account_name,
                subtitle=f"{acc.account_code} · {acc.account_type}",
            )
        )

    # Transactions — match description or (when numeric) the amount.
    txn_filters = [
        RawTransaction.description.ilike(f"%{t}%")
        | cast(RawTransaction.amount, String).ilike(f"%{t}%")
        for t in terms
    ]
    txns = await db.scalars(
        select(RawTransaction)
        .where(*txn_filters)
        .order_by(RawTransaction.txn_date.desc(), RawTransaction.created_at.desc())
        .limit(limit_per_type)
    )
    for txn in txns.all():
        hits.append(
            SearchHit(
                type="transaction",
                id=str(txn.raw_txn_id),
                title=txn.description,
                subtitle=f"{txn.amount} · {txn.txn_date.isoformat()}",
                period_id=str(txn.period_id),
            )
        )

    # Journal entries — match the entry description or any line memo.
    entry_filters = [
        JournalEntry.description.ilike(f"%{t}%")
        | exists().where(
            JournalLine.entry_id == JournalEntry.entry_id,
            JournalLine.memo.ilike(f"%{t}%"),
        )
        for t in terms
    ]
    entries = await db.scalars(
        select(JournalEntry)
        .where(*entry_filters)
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
        .limit(limit_per_type)
    )
    for entry in entries.all():
        hits.append(
            SearchHit(
                type="journal_entry",
                id=str(entry.entry_id),
                title=entry.description,
                subtitle=f"{entry.entry_date.isoformat()} · {entry.source_type}",
                period_id=str(entry.period_id),
            )
        )

    # Documents — match the file name.
    doc_filters = [Document.file_name.ilike(f"%{t}%") for t in terms]
    docs = await db.scalars(
        select(Document)
        .where(*doc_filters)
        .order_by(Document.created_at.desc())
        .limit(limit_per_type)
    )
    for doc in docs.all():
        hits.append(
            SearchHit(
                type="document",
                id=str(doc.document_id),
                title=doc.file_name,
                subtitle=f"{doc.document_type} · {doc.parse_status}",
                period_id=str(doc.period_id),
            )
        )

    # Periods — few rows, so match against a formatted label in Python so that
    # "january", "jan 2026", and "2026-01" all resolve.
    all_periods = (await db.scalars(select(Period).order_by(Period.period_start.desc()))).all()
    lowered = [t.lower() for t in terms]
    matched_periods = 0
    for period in all_periods:
        if matched_periods >= limit_per_type:
            break
        haystack = (
            f"{period.period_start.isoformat()} "
            f"{period.period_start.strftime('%B %b %Y')} "
            f"{period.status}"
        ).lower()
        if all(t in haystack for t in lowered):
            hits.append(
                SearchHit(
                    type="period",
                    id=str(period.period_id),
                    title=period.period_start.strftime("%B %Y"),
                    subtitle=period.status,
                    period_id=str(period.period_id),
                )
            )
            matched_periods += 1

    logger.info("Search %r returned %d hit(s)", q, len(hits))
    return SearchResponse(query=q, hits=hits)
