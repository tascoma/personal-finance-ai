from typing import Literal

from pydantic import BaseModel

SearchHitType = Literal["account", "transaction", "journal_entry", "document", "period"]


class SearchHit(BaseModel):
    type: SearchHitType
    id: str
    title: str
    subtitle: str | None = None
    period_id: str | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
