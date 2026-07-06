---
name: "add-migration"
description: "Set up Alembic and manage schema migrations"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Set up Alembic for database schema migrations and run them against Supabase.

## First-time setup (run once)

### 1. Install Alembic
```bash
uv add alembic
```

### 2. Initialise Alembic inside the backend
The `backend/alembic/` directory already exists in the repo with a `.gitkeep` placeholder. Remove it, then run init:

```bash
cd backend
rm alembic/.gitkeep
uv run alembic init alembic
```

This populates `backend/alembic/` (env.py, script.py.mako, versions/) and creates `backend/alembic.ini`.

### 3. Configure `alembic.ini`
Set the script location (leave `sqlalchemy.url` blank — we'll set it from settings):

```ini
script_location = alembic
```

Remove or comment out the `sqlalchemy.url` line — it's set in `env.py` instead.

### 4. Configure `backend/alembic/env.py`
Wire Alembic to your SQLAlchemy `Base` and `settings.database_url`:

```python
from app.core.config import settings
from app.databases import Base  # your DeclarativeBase
from sqlalchemy import engine_from_config, pool

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
```

For async engines, use the synchronous URL form for Alembic (replace `+asyncpg` with `+psycopg2` or use `run_sync`). The simplest approach is a sync URL just for migrations:

```python
sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)
```

Install `psycopg2-binary` if using PostgreSQL:
```bash
uv add psycopg2-binary
```

### 5. Add `alembic/` to git, ignore versions output
The `alembic/versions/` folder should be committed — migration files are source code.

---

## Day-to-day migration workflow

### Create a migration
After changing a SQLAlchemy model, autogenerate a migration:

```bash
cd backend
uv run alembic revision --autogenerate -m "add users table"
```

Always review the generated file in `alembic/versions/` before applying — autogenerate misses some changes (indexes, constraints, enum types).

### Apply migrations
Run against the **direct connection** URL (port 5432), not the transaction pooler:

```bash
uv run alembic upgrade head
```

To apply to staging, ensure `DATABASE_URL` in your environment points to the Supabase staging direct connection URL before running.

### Roll back one step
```bash
uv run alembic downgrade -1
```

### Check current revision
```bash
uv run alembic current
```

### View migration history
```bash
uv run alembic history --verbose
```

---

## Environment workflow

| Environment | When to run migrations |
|---|---|
| Local | After creating or modifying a model, before starting the server |
| Staging | After merging a feature branch to `dev` — run against the staging DB before testing |
| Production | After merging `dev` to `main` — run against the prod DB before the deploy goes live |

Never run `alembic upgrade head` against production without first validating the migration on staging.

---

## Verification
After creating or applying a migration, confirm the database is at the latest revision. Run from `backend/`:

```bash
uv run alembic upgrade head
uv run alembic current   # should report the id of the newest file in alembic/versions/
```

Then confirm the schema change actually landed — inspect the affected table with the Supabase MCP (`/mcp-supabase`) or a direct query. The migration is done when `alembic current` matches head and the table reflects the model change.

---

## Notes
- Migration files in `alembic/versions/` are source code — commit them with the model change in the same PR.
- Use the Supabase MCP (`/mcp-supabase`) to verify the schema after applying a migration.
- If a migration fails mid-way on production, run `alembic downgrade -1` to roll back, fix the migration file, and re-apply.
