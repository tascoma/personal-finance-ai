import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.dependencies import get_current_user, get_db_session
from app.models.device_token import DeviceToken
from app.models.user import User
from app.schemas.auth import (
    DeviceTokenRead,
    DeviceTokenRegister,
    TokenResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.services.auth import (
    AuthError,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_user_by_id,
    invalidate_tokens,
    register_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86_400,
        path="/api/v1/auth",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegister, db: AsyncSession = Depends(get_db_session)
) -> UserRead:
    # Single-user deployment: public registration is closed. The 404 mirrors what
    # an unmounted route would return so the endpoint's existence isn't advertised.
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        user = await register_user(db, email=body.email, password=body.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    try:
        user = await authenticate_user(db, email=body.email, password=body.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    access_token = create_access_token(user.user_id)
    refresh_token = create_refresh_token(user.user_id, user.token_version)
    _set_refresh_cookie(response, refresh_token)
    logger.info("User %s logged in", user.user_id)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> TokenResponse:
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token"
        )
    try:
        user_id, token_version = decode_refresh_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        )
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked"
        )

    new_access = create_access_token(user.user_id)
    new_refresh = create_refresh_token(user.user_id, user.token_version)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> None:
    if refresh_token is not None:
        try:
            user_id, _ = decode_refresh_token(refresh_token)
            await invalidate_tokens(db, user_id)
        except ValueError:
            pass  # Invalid/expired token — nothing to revoke, still clear the cookie
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post(
    "/device-tokens",
    response_model=DeviceTokenRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_device_token(
    body: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DeviceTokenRead:
    """Register or refresh an APNs token for the calling user.

    The same physical device can re-register the same token (after app upgrade
    or relaunch); we upsert and re-bind to the current user if needed, and
    bump `last_seen_at`.
    """
    now = datetime.now(timezone.utc)
    existing = (
        await db.execute(select(DeviceToken).where(DeviceToken.apns_token == body.apns_token))
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = current_user.user_id
        existing.bundle_id = body.bundle_id
        existing.last_seen_at = now
        await db.commit()
        await db.refresh(existing)
        return DeviceTokenRead.model_validate(existing)

    token = DeviceToken(
        user_id=current_user.user_id,
        apns_token=body.apns_token,
        bundle_id=body.bundle_id,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return DeviceTokenRead.model_validate(token)


@router.delete(
    "/device-tokens/{apns_token}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_device_token(
    apns_token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Drop a token (called by the iOS app on logout). Idempotent — succeeds
    silently if the token isn't on file or belongs to another user."""
    await db.execute(
        delete(DeviceToken).where(
            DeviceToken.apns_token == apns_token,
            DeviceToken.user_id == current_user.user_id,
        )
    )
    await db.commit()
