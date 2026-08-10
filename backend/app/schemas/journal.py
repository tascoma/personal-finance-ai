import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class JournalEntryRead(BaseModel):
    entry_id: uuid.UUID
    period_id: uuid.UUID
    entry_date: date
    description: str
    source_type: str
    source_document_id: uuid.UUID | None
    is_adjusting: bool
    is_closing: bool
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JournalLineRead(BaseModel):
    line_id: uuid.UUID
    entry_id: uuid.UUID
    account_code: int
    debit_amount: Decimal
    credit_amount: Decimal
    memo: str | None

    model_config = {"from_attributes": True}
