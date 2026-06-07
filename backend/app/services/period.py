"""Period service — month-based accounting periods.

Periods are the root workflow entity. Each period represents one calendar month
and progresses through a linear status lifecycle:

    open → pending_review → pending_close → closed

A closed period can also be reopened (closed → open), resetting closed_at.

Business rules:
- period_start is the first day of the month; period_end is the last day.
- Only one period may exist per month (enforced by unique index on period_start).
- Forward transitions are one step at a time along the lifecycle.
- A period can be deleted at any status; all child records are removed first.
"""

import calendar
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.journal import JournalEntry, JournalLine
from app.models.period import Period
from app.models.raw_transaction import RawTransaction
from app.models.reconciliation import Reconciliation
from app.models.review_queue import ReviewQueue
from app.models.stated_balance import StatedBalance

logger = logging.getLogger(__name__)

_STATUS_ORDER: tuple[str, ...] = ("open", "pending_review", "pending_close", "closed")


def next_status(current: str) -> str | None:
    """Return the next status in the lifecycle, or None if already at the end."""
    try:
        idx = _STATUS_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(_STATUS_ORDER):
        return None
    return _STATUS_ORDER[idx + 1]


def prev_status(current: str) -> str | None:
    """Return the previous status in the lifecycle, or None if already at the start."""
    try:
        idx = _STATUS_ORDER.index(current)
    except ValueError:
        return None
    if idx == 0:
        return None
    return _STATUS_ORDER[idx - 1]


class PeriodError(Exception):
    """Raised for invalid period operations (bad input, conflicts, illegal transitions)."""


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return (first-day, last-day) for the given calendar month."""
    first = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    last = date(year, month, last_day)
    return first, last


async def create_period(db: AsyncSession, year: int, month: int) -> Period:
    start, end = month_bounds(year, month)
    existing = await db.scalar(select(Period).where(Period.period_start == start))
    if existing is not None:
        raise PeriodError(f"Period for {year}-{month:02d} already exists")
    period = Period(period_start=start, period_end=end, status="open")
    db.add(period)
    await db.commit()
    await db.refresh(period)
    logger.info("Created period %s (%s → %s)", period.period_id, start, end)
    return period


async def list_periods(
    db: AsyncSession, *, limit: int | None = None, offset: int = 0
) -> Sequence[Period]:
    query = select(Period).order_by(Period.period_start.desc())
    # Default (limit omitted) returns all rows, preserving existing client behavior.
    if limit is not None:
        query = query.offset(offset).limit(limit)
    result = await db.scalars(query)
    return result.all()


async def get_period(db: AsyncSession, period_id: uuid.UUID) -> Period | None:
    return await db.get(Period, period_id)


async def get_current_open_period(db: AsyncSession) -> Period | None:
    """Most recent in-progress period (any non-closed status)."""
    return await db.scalar(
        select(Period)
        .where(Period.status != "closed")
        .order_by(Period.period_start.desc())
        .limit(1)
    )


async def update_status(
    db: AsyncSession, period_id: uuid.UUID, new_status: str
) -> Period:
    period = await db.get(Period, period_id)
    if period is None:
        raise PeriodError("Period not found")

    try:
        current_idx = _STATUS_ORDER.index(period.status)
        target_idx = _STATUS_ORDER.index(new_status)
    except ValueError as exc:
        raise PeriodError(f"Unknown status: {exc}") from exc

    # Forward-only transitions, one step at a time. This keeps the close workflow
    # honest — you can't skip from 'open' straight to 'closed' and bypass review.
    if target_idx != current_idx + 1:
        raise PeriodError(
            f"Illegal transition {period.status} → {new_status}"
        )

    period.status = new_status
    if new_status == "closed":
        period.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(period)
    logger.info("Period %s → %s", period.period_id, new_status)
    return period


async def step_back(db: AsyncSession, period_id: uuid.UUID) -> Period:
    """Move the period one step backward in the lifecycle."""
    period = await db.get(Period, period_id)
    if period is None:
        raise PeriodError("Period not found")
    previous = prev_status(period.status)
    if previous is None:
        raise PeriodError(f"Period is already at the earliest status ({period.status})")
    period.status = previous
    if previous != "closed":
        period.closed_at = None
    await db.commit()
    await db.refresh(period)
    logger.info("Period %s stepped back to %s", period.period_id, previous)
    return period


async def reopen_period(db: AsyncSession, period_id: uuid.UUID) -> Period:
    period = await db.get(Period, period_id)
    if period is None:
        raise PeriodError("Period not found")
    if period.status != "closed":
        raise PeriodError(f"Only closed periods can be reopened (current: {period.status})")
    period.status = "open"
    period.closed_at = None
    await db.commit()
    await db.refresh(period)
    logger.info("Reopened period %s", period.period_id)
    return period


async def delete_period(db: AsyncSession, period_id: uuid.UUID) -> None:
    period = await db.get(Period, period_id)
    if period is None:
        raise PeriodError("Period not found")

    # Delete in FK dependency order so no constraint is violated.
    # review_queue → raw_transactions → journal_lines → journal_entries
    #              → documents → stated_balances → reconciliation → period
    await db.execute(delete(ReviewQueue).where(ReviewQueue.period_id == period_id))
    await db.execute(delete(RawTransaction).where(RawTransaction.period_id == period_id))
    entry_ids = await db.scalars(
        select(JournalEntry.entry_id).where(JournalEntry.period_id == period_id)
    )
    await db.execute(delete(JournalLine).where(JournalLine.entry_id.in_(list(entry_ids))))
    await db.execute(delete(JournalEntry).where(JournalEntry.period_id == period_id))
    await db.execute(delete(Document).where(Document.period_id == period_id))
    await db.execute(delete(StatedBalance).where(StatedBalance.period_id == period_id))
    await db.execute(delete(Reconciliation).where(Reconciliation.period_id == period_id))
    await db.delete(period)
    await db.commit()
    logger.info("Deleted period %s", period_id)
