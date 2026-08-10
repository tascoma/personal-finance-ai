"""Tests for auth endpoints and protected route enforcement."""

import pytest_asyncio
from httpx import AsyncClient

from app.core.config import settings

REGISTER_PAYLOAD = {"email": "test@example.com", "password": "securepassword"}
LOGIN_PAYLOAD = REGISTER_PAYLOAD


@pytest_asyncio.fixture
async def auth_client(anon_client: AsyncClient):
    """Client with a valid Bearer token pre-loaded."""
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    token = resp.json()["access_token"]
    anon_client.headers.update({"Authorization": f"Bearer {token}"})
    return anon_client


# ── Register ──────────────────────────────────────────────────────────────────


async def test_register_creates_user(anon_client: AsyncClient):
    resp = await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == REGISTER_PAYLOAD["email"]
    assert "user_id" in data
    assert "hashed_password" not in data


async def test_register_duplicate_email_returns_409(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 409


async def test_register_short_password_returns_422(anon_client: AsyncClient):
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": "a@b.com", "password": "short"}
    )
    assert resp.status_code == 422


async def test_register_returns_404_when_disabled(anon_client: AsyncClient, monkeypatch):
    """Public registration must be closed by default for single-user deployments."""
    monkeypatch.setattr(settings, "allow_registration", False)
    resp = await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 404


# ── Login ─────────────────────────────────────────────────────────────────────


async def test_login_returns_access_token(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_sets_refresh_cookie(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    assert "refresh_token" in resp.cookies


async def test_login_bad_password_returns_401(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    resp = await anon_client.post(
        "/api/v1/auth/login", json={**LOGIN_PAYLOAD, "password": "wrongpass"}
    )
    assert resp.status_code == 401


async def test_login_rate_limited(anon_client: AsyncClient, monkeypatch):
    """Per-IP rate limit returns 429 once the threshold is exceeded."""
    from app.core.ratelimit import limiter

    # Low limit for this test; a fresh storage bucket so prior tests don't count.
    monkeypatch.setattr(settings, "auth_rate_limit", "3/minute")
    limiter.reset()

    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    statuses = [
        (await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)).status_code
        for _ in range(4)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429


async def test_login_unknown_and_wrong_password_are_indistinguishable(anon_client: AsyncClient):
    """No account enumeration: an unknown email and a wrong password return the
    same status and the same generic message."""
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

    unknown = await anon_client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "securepassword"}
    )
    wrong = await anon_client.post(
        "/api/v1/auth/login", json={**LOGIN_PAYLOAD, "password": "wrongpass"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"] == "Invalid credentials"


async def test_register_overlong_password_returns_422(anon_client: AsyncClient):
    """Passwords beyond bcrypt's 72-byte limit are rejected at the schema, not 500."""
    resp = await anon_client.post(
        "/api/v1/auth/register", json={"email": "a@b.com", "password": "p" * 73}
    )
    assert resp.status_code == 422


async def test_security_headers_present(anon_client: AsyncClient):
    resp = await anon_client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"


# ── Refresh ───────────────────────────────────────────────────────────────────


async def test_refresh_issues_new_access_token(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_without_cookie_returns_401(anon_client: AsyncClient):
    resp = await anon_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ── Protected routes ──────────────────────────────────────────────────────────


async def test_protected_route_without_token_returns_4xx(anon_client: AsyncClient):
    resp = await anon_client.get("/api/v1/accounts")
    assert resp.status_code in (401, 403)


async def test_protected_route_with_token_succeeds(auth_client: AsyncClient):
    resp = await auth_client.get("/api/v1/accounts")
    assert resp.status_code == 200


async def test_me_returns_user_info(auth_client: AsyncClient):
    resp = await auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == REGISTER_PAYLOAD["email"]


# ── Logout ────────────────────────────────────────────────────────────────────


async def test_logout_clears_cookie(anon_client: AsyncClient):
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    resp = await anon_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204


async def test_logout_invalidates_refresh_token(anon_client: AsyncClient):
    """Refresh token must be rejected after logout (server-side revocation)."""
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    await anon_client.post("/api/v1/auth/logout")
    resp = await anon_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ── Token type security ───────────────────────────────────────────────────────


async def test_refresh_token_rejected_as_bearer(anon_client: AsyncClient):
    """A refresh token must not be accepted as a Bearer access token."""
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    login_resp = await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    refresh_token = login_resp.cookies.get("refresh_token")
    assert refresh_token is not None

    resp = await anon_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert resp.status_code == 401


async def test_access_token_rejected_as_refresh_cookie(anon_client: AsyncClient):
    """An access token must not be accepted at the /refresh endpoint."""
    await anon_client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    login_resp = await anon_client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    access_token = login_resp.json()["access_token"]

    # Manually set the refresh_token cookie to the access token value
    anon_client.cookies.set("refresh_token", access_token)
    resp = await anon_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
