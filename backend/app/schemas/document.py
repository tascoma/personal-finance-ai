import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    period_id: uuid.UUID
    document_type: str
    file_name: str
    file_path: str
    source_account_code: int | None = None


class DocumentRead(BaseModel):
    document_id: uuid.UUID
    period_id: uuid.UUID
    document_type: str
    file_name: str
    file_path: str
    source_account_code: int | None
    parse_status: str
    parsed_at: datetime | None
    llm_model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
