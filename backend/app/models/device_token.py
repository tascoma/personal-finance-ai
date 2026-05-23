import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.databases import Base


class DeviceToken(Base):
    """An APNs device token registered for push notifications.

    One row per (user, device). Tokens are unique across users — if the same
    device token re-registers under a different user, we re-bind it on upsert.
    APNs `410 Unregistered` / `400 BadDeviceToken` responses trigger deletion.
    """

    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    apns_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bundle_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
