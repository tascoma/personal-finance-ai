import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class RawTransactionRead(BaseModel):
    raw_txn_id: uuid.UUID
    document_id: uuid.UUID
    period_id: uuid.UUID
    txn_date: date
    description: str
    amount: Decimal
    suggested_account_code: int | None
    classifier_confidence: Decimal | None
    is_flagged: bool
    is_duplicate: bool
    dedup_hash: str | None
    status: str
    journal_entry_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
