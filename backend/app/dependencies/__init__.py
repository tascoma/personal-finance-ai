import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases import get_db
from app.models.period import Period
from app.models.user import User
from app.services.auth import decode_access_token, get_user_by_id
from app.services.period import get_period

_bearer = HTTPBearer()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_period_or_404(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Period:
    """Resolve the `{period_id}` path parameter, 404ing if it doesn't exist.

    Nine route handlers opened with the same three-line lookup-and-raise. As a
    dependency it also runs before the handler body, so a request for a missing
    period no longer does any of the handler's other work first.
    """
    period = await get_period(db, period_id)
    if period is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Period not found"
        )
    return period
