"""Apple Push Notification service (APNs) — Phase 6.

Sends a push to every DeviceToken row for a given user. The JWT is signed with
ES256 using the team's APNs Auth Key (.p8). Apple's APNs endpoint requires
HTTP/2, so this module needs `httpx[http2]` (which pulls in `h2`).

If any of APNS_AUTH_KEY_P8, APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID is
unset, or if `h2` isn't installed, `notify_user()` is a no-op. That lets the
backend ship without paid Apple Developer credentials; operators wire APNs by
setting the env vars and running `uv add 'httpx[http2]'` when they're ready.

NOTE: `h2` is deliberately not in the lockfile today, so this module is inert
in every deployed environment — `_has_http2_support()` returns False and
`notify_user` returns 0 before touching the database. Adding `h2` is what turns
push delivery on in production; treat it as an explicit rollout step, not a
routine dependency bump.

Tokens that come back as 410 Unregistered or 400 BadDeviceToken are deleted —
the device uninstalled the app or revoked permission.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx
from jose import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device_token import DeviceToken

logger = logging.getLogger(__name__)


def _credentials_present() -> bool:
    return bool(
        settings.apns_auth_key_p8
        and settings.apns_key_id
        and settings.apns_team_id
        and settings.apns_bundle_id
    )


def _has_http2_support() -> bool:
    try:
        import h2  # noqa: F401
        return True
    except ImportError:
        return False


def _build_jwt() -> str:
    """ES256 JWT, valid for up to 60 minutes per Apple's spec. Cached at the
    call site by keeping the issued token in memory until expiry — for a
    low-volume backend, re-signing per send is also acceptable."""
    headers = {"alg": "ES256", "kid": settings.apns_key_id}
    payload = {
        "iss": settings.apns_team_id,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.apns_auth_key_p8, algorithm="ES256", headers=headers)


def _apns_host() -> str:
    return (
        "https://api.sandbox.push.apple.com"
        if settings.apns_use_sandbox
        else "https://api.push.apple.com"
    )


async def notify_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    body: str,
    extra: dict[str, Any] | None = None,
) -> int:
    """Send a push to every registered device for `user_id`.

    Returns the count of successful deliveries. Logs and continues on partial
    failures; deletes tokens APNs reports as dead. Returns 0 if APNs isn't
    configured (no-op).
    """
    if not _credentials_present():
        logger.info("APNs credentials not set; skipping push to user %s", user_id)
        return 0
    if not _has_http2_support():
        logger.warning(
            "APNs requires HTTP/2 but `h2` is not installed. "
            "Run `uv add 'httpx[http2]'` to enable real push delivery."
        )
        return 0

    rows = (
        await db.execute(select(DeviceToken).where(DeviceToken.user_id == user_id))
    ).scalars().all()
    if not rows:
        return 0

    token_jwt = _build_jwt()
    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }
    if extra:
        payload.update(extra)
    body_bytes = json.dumps(payload).encode()

    delivered = 0
    dead_tokens: list[str] = []

    async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
        for row in rows:
            url = f"{_apns_host()}/3/device/{row.apns_token}"
            headers = {
                "authorization": f"bearer {token_jwt}",
                "apns-topic": settings.apns_bundle_id,
                "apns-push-type": "alert",
                "content-type": "application/json",
            }
            try:
                response = await client.post(url, headers=headers, content=body_bytes)
            except httpx.HTTPError as exc:
                logger.warning("APNs request failed for token %s: %s", row.id, exc)
                continue

            if 200 <= response.status_code < 300:
                delivered += 1
                continue

            try:
                reason = response.json().get("reason", "")
            except ValueError:
                reason = ""

            if response.status_code == 410 or reason in {"Unregistered", "BadDeviceToken"}:
                dead_tokens.append(row.apns_token)
                logger.info(
                    "APNs reports dead token (%s, reason=%s); deleting",
                    row.id, reason,
                )
            else:
                logger.warning(
                    "APNs %d for token %s: %s", response.status_code, row.id, reason
                )

    if dead_tokens:
        await db.execute(delete(DeviceToken).where(DeviceToken.apns_token.in_(dead_tokens)))
        await db.commit()

    return delivered


async def notify_user_background(
    user_id: uuid.UUID,
    *,
    title: str,
    body: str,
    extra: dict[str, Any] | None = None,
) -> int:
    """`notify_user` for use from a FastAPI BackgroundTask.

    Background tasks run *after* the request's dependency teardown, so the
    session yielded by `get_db_session` is already closed by the time the task
    executes. Passing that session in would raise on first use. Open a fresh
    one instead, scoped to the task.

    Exceptions are swallowed: a background push failure must not surface as an
    unhandled error in the ASGI layer after the response has been sent.
    """
    from app.databases import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            return await notify_user(db, user_id, title=title, body=body, extra=extra)
    except Exception:
        logger.exception("Background push to user %s failed", user_id)
        return 0
