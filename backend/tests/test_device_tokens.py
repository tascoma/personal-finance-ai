"""Tests for /auth/device-tokens routes and apns.notify_user no-op behavior."""

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.dependencies import get_db_session
from app.main import app
from app.models.device_token import DeviceToken
from app.services import apns as apns_service

REGISTER_PAYLOAD = {"email": "tester@example.com", "password": "securepassword"}


@pytest_asyncio.fixture
async def auth_client(session_factory):
    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        resp = await client.post("/api/v1/auth/login", json=REGISTER_PAYLOAD)
        token = resp.json()["access_token"]
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client
    app.dependency_overrides.clear()


async def test_register_device_token_creates_row(auth_client: AsyncClient, session_factory):
    payload = {
        "apns_token": "a" * 64,
        "bundle_id": "com.tascoma.personalfinanceai",
    }
    resp = await auth_client.post("/api/v1/auth/device-tokens", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["bundle_id"] == payload["bundle_id"]
    assert "id" in data and "created_at" in data and "last_seen_at" in data

    async with session_factory() as session:
        rows = (await session.execute(select(DeviceToken))).scalars().all()
    assert len(rows) == 1
    assert rows[0].apns_token == payload["apns_token"]


async def test_register_device_token_upserts_existing(auth_client: AsyncClient, session_factory):
    token = "b" * 64
    await auth_client.post(
        "/api/v1/auth/device-tokens",
        json={"apns_token": token, "bundle_id": "com.tascoma.personalfinanceai"},
    )
    # Re-registering with a new bundle id (e.g. after a TestFlight install)
    # should reuse the row, not create a duplicate.
    await auth_client.post(
        "/api/v1/auth/device-tokens",
        json={"apns_token": token, "bundle_id": "com.tascoma.personalfinanceai.beta"},
    )
    async with session_factory() as session:
        rows = (await session.execute(select(DeviceToken))).scalars().all()
    assert len(rows) == 1
    assert rows[0].bundle_id == "com.tascoma.personalfinanceai.beta"


async def test_register_device_token_requires_auth(session_factory):
    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/device-tokens",
            json={"apns_token": "z" * 64, "bundle_id": "com.tascoma.personalfinanceai"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 401


async def test_delete_device_token(auth_client: AsyncClient, session_factory):
    token = "c" * 64
    await auth_client.post(
        "/api/v1/auth/device-tokens",
        json={"apns_token": token, "bundle_id": "com.tascoma.personalfinanceai"},
    )
    resp = await auth_client.delete(f"/api/v1/auth/device-tokens/{token}")
    assert resp.status_code == 204

    async with session_factory() as session:
        rows = (await session.execute(select(DeviceToken))).scalars().all()
    assert rows == []


async def test_delete_unknown_token_is_idempotent(auth_client: AsyncClient):
    resp = await auth_client.delete("/api/v1/auth/device-tokens/" + "d" * 64)
    assert resp.status_code == 204


async def test_apns_noop_without_credentials(session_factory):
    """notify_user() returns 0 and writes nothing when APNs creds are unset."""
    async with session_factory() as session:
        result = await apns_service.notify_user(
            session,
            uuid.uuid4(),
            title="Test",
            body="Body",
        )
    assert result == 0
