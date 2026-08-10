import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.databases import Base


class Period(Base):
    __tablename__ = "periods"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'pending_review', 'pending_close', 'closed')",
            name="ck_period_status",
        ),
    )

    period_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    period_start: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, default="open", nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
