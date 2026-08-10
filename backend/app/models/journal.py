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


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('paystub', 'statement', 'manual', 'adjusting', 'closing')",
            name="ck_entry_source_type",
        ),
        CheckConstraint(
            "created_by IN ('python', 'user')",
            name="ck_entry_created_by",
        ),
        Index("ix_journal_entry_date", "entry_date"),
    )

    entry_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periods.period_id"), nullable=False
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.document_id"), nullable=True
    )
    is_adjusting: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_closing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(String, default="python", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)",
            name="debit_or_credit",
        ),
        CheckConstraint("debit_amount >= 0", name="ck_debit_non_negative"),
        CheckConstraint("credit_amount >= 0", name="ck_credit_non_negative"),
        Index("ix_journal_line_entry_id", "entry_id"),
        Index("ix_journal_line_account_code", "account_code"),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journal_entries.entry_id"), nullable=False
    )
    account_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_code"), nullable=False
    )
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"), nullable=False
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0"), nullable=False
    )
    memo: Mapped[str | None] = mapped_column(String, nullable=True)
