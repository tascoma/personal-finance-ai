"""Shared test scaffolding.

Every route test needs the same three things: an in-memory SQLite engine with
the schema created, an `AsyncClient` bound to the app, and the two dependency
overrides that supply a session and a signed-in user. Those were previously
re-declared in each of 17 test modules — byte-identical in most of them — so
they live here instead.

Modules that need seeded reference data override `session_factory` locally;
pytest resolves a module-level fixture ahead of the one defined here.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable

# Provide a dummy key so Agent(...) construction succeeds at import time.
# Tests patch run_* functions directly, so this key is never sent to the API.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

# Public registration is disabled by default (single-user deployment); the test
# suite exercises the /auth/register endpoint, so re-enable it for tests.
os.environ.setdefault("ALLOW_REGISTRATION", "true")

# Most auth tests hammer /login many times; raise the per-IP rate limit so it
# never trips except in the dedicated rate-limit test (which overrides it).
os.environ.setdefault("AUTH_RATE_LIMIT", "100000/minute")

import pytest_asyncio  # noqa: E402 — must follow the env defaults above
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.databases import Base  # noqa: E402
from app.dependencies import get_current_user, get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

SessionFactory = async_sessionmaker[AsyncSession]


def make_test_user() -> User:
    """A signed-in user for `get_current_user` overrides."""
    return User(
        user_id=uuid.uuid4(),
        email="test@test.com",
        hashed_password="",
        is_active=True,
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[SessionFactory]:
    """In-memory engine with the full schema created.

    Override this in a module that needs seeded reference data (see
    test_statements.py and test_ledger.py, which seed a chart of accounts).
    """
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    yield factory
    await eng.dispose()


def _override_db(session_factory: SessionFactory) -> Callable[[], AsyncIterator[AsyncSession]]:
    async def _dep() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    return _dep


@pytest_asyncio.fixture
async def client(session_factory: SessionFactory) -> AsyncIterator[AsyncClient]:
    """Authenticated client. `get_current_user` yields a throwaway user."""
    app.dependency_overrides[get_db_session] = _override_db(session_factory)
    app.dependency_overrides[get_current_user] = make_test_user
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(session_factory: SessionFactory) -> AsyncIterator[AsyncClient]:
    """Client with the session override only, so real auth still applies.

    Used by the /auth tests, which need register/login/refresh to run through
    the actual dependency rather than a stubbed user.
    """
    app.dependency_overrides[get_db_session] = _override_db(session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as c:
        yield c
    app.dependency_overrides.clear()
