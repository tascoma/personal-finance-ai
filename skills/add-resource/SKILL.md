---
name: "add-resource"
description: "Add a full CRUD resource: model, schema, dep, service, router, tests"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Add a full CRUD resource to the backend: ORM model, Pydantic schemas, dependency, service, router, and tests. Replace `<Resource>` / `<resource>` with the actual resource name throughout.

## Steps

### 1. Model (`backend/app/models/<resource>.py`)
One file per resource. Inherit from the shared `Base` defined in `backend/app/databases/`. Use SQLAlchemy 2.0 mapped-column style with full type annotations.

```python
from sqlalchemy.orm import Mapped, mapped_column
from app.databases import Base

class Resource(Base):
    __tablename__ = "<resources>"

    id: Mapped[int] = mapped_column(primary_key=True)
    # ... fields
```

### 2. Schemas (`backend/app/schemas/<resource>.py`)
Define separate `<Resource>Create`, `<Resource>Update`, and `<Resource>Read` Pydantic models. `Read` includes database-generated fields (`id`, `created_at`, etc.). Never share a class between ORM and Pydantic layers.

```python
from pydantic import BaseModel

class ResourceCreate(BaseModel):
    ...

class ResourceUpdate(BaseModel):
    ...

class ResourceRead(BaseModel):
    id: int
    model_config = {"from_attributes": True}
```

### 3. Dependency (`backend/app/dependencies/<resource>.py`)
Add any resource-specific `Depends()` factories here (e.g. `get_resource_or_404`). Import `get_db` from `app.databases` and compose upward. Generic deps (db session, current user) already live in `backend/app/dependencies/`.

### 4. Service (`backend/app/services/<resource>.py`)
Own the business logic here. Accept a db session (and/or agent) as arguments — injected by the route via `Depends()`. Routes stay thin; services do the work.

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.<resource> import Resource
from app.schemas.<resource> import ResourceCreate

async def create_resource(db: AsyncSession, data: ResourceCreate) -> Resource:
    obj = Resource(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj
```

### 5. Router (`backend/app/routes/<resource>.py`)
One `APIRouter` per resource. Expose the full CRUD set — omit an endpoint only when the resource genuinely doesn't support that operation. Return Pydantic schema instances — never raw dicts or ORM objects.

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.databases import get_db
from app.schemas.<resource> import ResourceCreate, ResourceRead
from app.services import <resource> as svc

router = APIRouter(prefix="/<resources>", tags=["<resources>"])

@router.post("/", response_model=ResourceRead, status_code=201)
async def create(data: ResourceCreate, db: AsyncSession = Depends(get_db)):
    return await svc.create_resource(db, data)

@router.get("/", response_model=list[ResourceRead])
async def list_all(db: AsyncSession = Depends(get_db)):
    return await svc.list_resources(db)

@router.get("/{id}", response_model=ResourceRead)
async def get_one(id: int, db: AsyncSession = Depends(get_db)):
    return await svc.get_resource(db, id)

@router.patch("/{id}", response_model=ResourceRead)
async def update(id: int, data: ResourceUpdate, db: AsyncSession = Depends(get_db)):
    return await svc.update_resource(db, id, data)

@router.delete("/{id}", status_code=204)
async def delete(id: int, db: AsyncSession = Depends(get_db)):
    await svc.delete_resource(db, id)
```

### 6. Register the router (`backend/app/main.py`)
Import and include the new router in the `FastAPI` app:

```python
from app.routes.<resource> import router as <resource>_router
app.include_router(<resource>_router)
```

### 7. Tests (`backend/tests/test_<resource>.py`)
Use `httpx.AsyncClient` with `ASGITransport` against the real app. Override `get_db` to use a separate test database. Cover create, list, get, update, and delete.

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_create_resource():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/<resources>/", json={...})
    assert response.status_code == 201
```

## Verification
Run from `backend/`:

```bash
uv run pytest tests/test_<resource>.py -v
```

All CRUD endpoints should have passing tests before marking the task complete.
