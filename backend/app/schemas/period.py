import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PeriodStatus = Literal["open", "pending_review", "pending_close", "closed"]


class PeriodCreate(BaseModel):
    """Create a period by month. period_start/period_end are derived server-side."""

    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)


class PeriodUpdate(BaseModel):
    status: PeriodStatus


class PeriodRead(BaseModel):
    period_id: uuid.UUID
    period_start: date
    period_end: date
    # The Literal, not a bare `str`: the TypeScript client already narrows this
    # field to the same four values, so leaving it untyped here meant the client
    # asserted a contract the API never enforced.
    status: PeriodStatus
    closed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
