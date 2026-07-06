---
name: "add-tests"
description: "Set up the pytest suite and write tests for a route module"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Set up the pytest suite and write tests for a FastAPI route module. Run all commands from `backend/`.

## First-time setup (run once)

### 1. Verify dev dependencies are installed
```bash
uv sync
```

`httpx`, `pytest`, and `pytest-asyncio` are already declared as dev dependencies.

### 2. Configure pytest (`backend/pyproject.toml` or `backend/pytest.ini`)
Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`asyncio_mode = "auto"` removes the need to decorate every async test with `@pytest.mark.asyncio`.

### 3. Conftest (`backend/tests/conftest.py`)
Set up a shared async client and a test database override. Use SQLite in-memory for speed, or point at a dedicated Supabase staging database for integration tests.

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.databases import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL)
TestSession = async_sessionmaker(engine, expire_on_commit=False)

async def override_get_db():
    async with TestSession() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

---

## Writing tests for a route module

One test file per route module: `tests/test_<resource>.py`.

### CRUD test pattern

```python
async def test_create(client):
    response = await client.post("/api/<resources>/", json={"name": "test"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "test"
    assert "id" in data

async def test_list(client):
    await client.post("/api/<resources>/", json={"name": "a"})
    await client.post("/api/<resources>/", json={"name": "b"})
    response = await client.get("/api/<resources>/")
    assert response.status_code == 200
    assert len(response.json()) == 2

async def test_get_one(client):
    created = (await client.post("/api/<resources>/", json={"name": "x"})).json()
    response = await client.get(f"/api/<resources>/{created['id']}")
    assert response.status_code == 200

async def test_get_one_not_found(client):
    response = await client.get("/api/<resources>/999")
    assert response.status_code == 404

async def test_update(client):
    created = (await client.post("/api/<resources>/", json={"name": "old"})).json()
    response = await client.patch(f"/api/<resources>/{created['id']}", json={"name": "new"})
    assert response.status_code == 200
    assert response.json()["name"] == "new"

async def test_delete(client):
    created = (await client.post("/api/<resources>/", json={"name": "x"})).json()
    response = await client.delete(f"/api/<resources>/{created['id']}")
    assert response.status_code == 204
```

### Testing authenticated routes
Override the auth dependency to inject a fake user:

```python
from app.dependencies.auth import get_current_user

def fake_user():
    return {"sub": "test-user-uuid", "email": "test@example.com"}

app.dependency_overrides[get_current_user] = fake_user
```

Reset overrides after the test if you need unauthenticated cases in the same file.

---

## Verification

```bash
# Run all tests
uv run pytest

# Run a specific file
uv run pytest tests/test_<resource>.py

# Run with output
uv run pytest -v

# Stop on first failure
uv run pytest -x
```

## Notes
- Test files must start with `test_`; test functions must start with `test_`.
- Each test gets a fresh database via the `autouse` fixture — tests are fully isolated.
- Test the HTTP contract (status codes, response shape), not internal implementation details.
- For agent tests, override the agent dependency with a stub that returns a fixed response — don't make real LLM calls in tests.
