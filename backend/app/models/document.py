import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.databases import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('paystub', 'bank_statement', 'credit_card', 'investment', 'mortgage_statement', 'manual', 'opening_balances', 'unknown')",
            name="ck_document_type",
        ),
        CheckConstraint(
            "parse_status IN ('pending', 'in_progress', 'complete', 'failed')",
            name="ck_parse_status",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periods.period_id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    source_account_code: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.account_code"), nullable=True
    )
    parse_status: Mapped[str] = mapped_column(
        String, default="pending", nullable=False
    )
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
