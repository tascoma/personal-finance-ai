import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.databases import Base


class RawTransaction(Base):
    __tablename__ = "raw_transactions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('staged', 'approved', 'rejected', 'posted')",
            name="ck_raw_txn_status",
        ),
        Index("ix_raw_txn_period_id", "period_id"),
        Index("ix_raw_txn_dedup_hash", "dedup_hash"),
        Index("ix_raw_txn_flagged", "is_flagged", postgresql_where="is_flagged = TRUE"),
    )

    raw_txn_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.document_id"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periods.period_id"), nullable=False
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    suggested_account_code: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.account_code"), nullable=True
    )
    classifier_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dedup_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="staged", nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_entries.entry_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
