import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.databases import Base


class Reconciliation(Base):
    __tablename__ = "reconciliation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reconciled', 'adjusted', 'pending')",
            name="ck_recon_status",
        ),
    )

    recon_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("periods.period_id"), nullable=False
    )
    account_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.account_code"), nullable=False
    )
    computed_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    stated_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    gap: Mapped[Decimal] = mapped_column(
        Numeric(15, 2),
        Computed("stated_balance - computed_balance"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    run_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
