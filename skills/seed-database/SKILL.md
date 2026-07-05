---
name: "seed-database"
description: "Write and run idempotent seed scripts to populate the database with reference or test data"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Populate the database with reference or development data using a repeatable, idempotent seed script. Run migrations first (`/add-migration`) so the schema exists before seeding.

## Steps

### 1. Seed script (`backend/app/databases/seed.py`)
Write an async script that opens a session from the existing `AsyncSessionLocal` factory (defined in `backend/app/databases/`) and inserts rows via the ORM models. Make it **idempotent** — check for existing rows (or upsert) so re-running never duplicates data.

```python
import asyncio
import logging

from sqlalchemy import select

from app.databases import AsyncSessionLocal
from app.models.<resource> import Resource

logger = logging.getLogger(__name__)

SEED_RESOURCES = [
    {"name": "alpha"},
    {"name": "beta"},
]

async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for data in SEED_RESOURCES:
            exists = await db.scalar(
                select(Resource).where(Resource.name == data["name"])
            )
            if exists:
                continue
            db.add(Resource(**data))
        await db.commit()
    logger.info("Seed complete: %d resources ensured", len(SEED_RESOURCES))

if __name__ == "__main__":
    asyncio.run(seed())
```

### 2. Run it
From `backend/`:

```bash
uv run python -m app.databases.seed
```

### 3. Keep environments separate
Seed data is for **local and staging** only. Never run a throwaway seed against the production database. Keep distinct seed sets if dev and staging need different fixtures, and gate them on `settings.app_env` if they live in one script.

## Verification
Run the script twice in a row — the first run inserts rows, the second is a no-op (proves idempotency). Then confirm the rows exist by one of:

- Querying the table via the Supabase MCP (`/mcp-supabase`).
- Starting the app (`/run-dev`) and hitting the seeded resource's list endpoint — the seeded rows come back.
