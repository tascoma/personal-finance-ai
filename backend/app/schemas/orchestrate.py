"""Schemas for the orchestrate-parse endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class OrchestrationStepResult(BaseModel):
    document_id: uuid.UUID
    file_name: str
    resolved_type: str
    resolved_source_account_code: int | None = None
    resolved_account_name: str | None = None
    type_reason: str | None = None
    source_account_reason: str | None = None
    run_classifier: bool
    status: str  # "complete" | "failed" | "needs_review"
    error: str | None = None


class OrchestrationResult(BaseModel):
    period_id: uuid.UUID
    parsed: int
    failed: int
    needs_review: int = 0
    classifier_ran: bool
    classifier_updated: int
    steps: list[OrchestrationStepResult] = []
