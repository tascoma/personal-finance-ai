import logging
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


# Precomputed hash of a throwaway value. Verified against when no user matches so
# login spends the same bcrypt time whether or not the email exists (no enumeration
# via response timing).
_DUMMY_HASH = bcrypt.hashpw(b"timing-attack-mitigation", bcrypt.gensalt()).decode()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _make_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    return _make_token(
        {"sub": str(user_id), "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: uuid.UUID, token_version: int) -> str:
    return _make_token(
        {"sub": str(user_id), "type": "refresh", "ver": token_version},
        timedelta(days=settings.refresh_token_expire_days),
    )


def _decode_jwt(token: str) -> dict:
    """Decode and validate JWT signature/expiry; return raw payload."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def decode_access_token(token: str) -> uuid.UUID:
    """Validate an access token and return user_id. Raises ValueError on failure."""
    payload = _decode_jwt(token)
    if payload.get("type") != "access":
        raise ValueError("Expected access token")
    sub: str | None = payload.get("sub")
    if sub is None:
        raise ValueError("Token missing 'sub' claim")
    return uuid.UUID(sub)


def decode_refresh_token(token: str) -> tuple[uuid.UUID, int]:
    """Validate a refresh token; return (user_id, token_version). Raises ValueError on failure."""
    payload = _decode_jwt(token)
    if payload.get("type") != "refresh":
        raise ValueError("Expected refresh token")
    sub: str | None = payload.get("sub")
    if sub is None:
        raise ValueError("Token missing 'sub' claim")
    ver = payload.get("ver")
    if ver is None:
        raise ValueError("Token missing version claim")
    return uuid.UUID(sub), int(ver)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.scalars(select(User).where(User.email == email))
    return result.first()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


class AuthError(Exception):
    """Raised for authentication failures."""


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    existing = await get_user_by_email(db, email)
    if existing is not None:
        raise AuthError("Email already registered")
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("Registered new user %s", user.user_id)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    # Always run a bcrypt comparison, even for a missing user, so the response
    # time doesn't reveal whether the email is registered.
    if not verify_password(password, user.hashed_password if user else _DUMMY_HASH):
        raise AuthError("Invalid credentials")
    if user is None:
        raise AuthError("Invalid credentials")
    if not user.is_active:
        raise AuthError("Account is disabled")
    return user


async def invalidate_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Increment token_version, invalidating all outstanding refresh tokens for this user."""
    user = await db.get(User, user_id)
    if user is not None:
        user.token_version += 1
        await db.commit()
