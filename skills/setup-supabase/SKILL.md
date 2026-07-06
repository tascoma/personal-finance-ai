---
name: "setup-supabase"
description: "Connect the app to a Supabase PostgreSQL database"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Connect the app to a Supabase PostgreSQL database: create the project, configure connection URLs, and wire SQLAlchemy.

## Steps

### 1. Create a Supabase project
Go to [supabase.com](https://supabase.com), create a new project, and wait for it to provision.

### 2. Get the connection strings
In the Supabase dashboard → **Project Settings → Database**:

- **Direct connection** (port 5432) — use this for running migrations (Alembic) and local development.
- **Transaction pooler** (port 6543, Session mode) — use this for the running app in production on Render, since serverless/ephemeral environments exhaust direct connections.

Both URLs are under **Connection string → URI**. Switch the dropdown between "Direct connection" and "Transaction pooler" to copy each.

The async SQLAlchemy driver requires `postgresql+asyncpg://` — replace the `postgresql://` prefix when pasting.

### 3. Set environment variables
Add to `.env` (and document the shape in `.env.example`):

```
# Direct connection — for migrations and local dev
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

# Transaction pooler — for production (set this as DATABASE_URL on Render)
# DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

The database connection only needs `DATABASE_URL`. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are optional and used only by Supabase Storage (`/setup-storage`) — leave them blank if you're not storing files.

### 4. Install the async driver
```bash
uv add asyncpg
```

### 5. Verify the SQLAlchemy engine config
In `backend/app/databases/`, confirm the engine is created with the async URL and has `pool_pre_ping` enabled to handle pooler connection resets:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

### 6. Run migrations
If using Alembic, run migrations against the **direct connection** URL (port 5432), not the pooler:

```bash
# from backend/
uv run alembic upgrade head
```

If not using Alembic yet, tables can be created with `Base.metadata.create_all(engine)` — but Alembic is preferred for any app that will evolve its schema.

## Verification
Start the app locally and hit a route that queries the database. Check `backend/logs/app.log` or stdout for SQLAlchemy connection errors. A successful query confirms the setup.

## Notes
- Never commit the Supabase password. It lives in `.env` only.
- The `anon` and `service_role` API keys are for the Supabase JS client — not needed here since the app connects directly via SQLAlchemy.
- Enable **Row Level Security (RLS)** on Supabase tables before going to production if any table will be accessed by untrusted clients.
