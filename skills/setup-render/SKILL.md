---
name: "setup-render"
description: "Deploy the backend and frontend to Render"
metadata:
  author: agent-webapp-template
  version: 2.0.0
---

Deploy the FastAPI backend as a Dockerized Render Web Service and the React frontend as a Render Static Site, using a single Blueprint (`render.yaml`) that provisions production and staging for both in one sync.

## Prerequisites
- Code is pushed to a GitHub repository with `main` and `dev` branches (see `/github-workflow`).
- Supabase (or another database) is provisioned for both staging and production, and you have both `DATABASE_URL` values.
- You have an Anthropic API key.

---

## What gets created

| File | Purpose |
|---|---|
| `Dockerfile` | Builds the FastAPI backend image. Used by both backend services. |
| `.dockerignore` | Keeps the frontend, docs, and local artifacts out of the backend build context. |
| `render.yaml` | Render Blueprint — defines all 4 services (backend × 2 environments, frontend × 2 environments) in one file. |

The frontend has no Dockerfile — it deploys as a Render Static Site (`env: static`), built directly by Render from `frontend/`.

---

## 1. Create the `Dockerfile`
At the repo root:

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY backend/app ./backend/app

RUN uv sync --no-dev

WORKDIR /app/backend

EXPOSE 8000

CMD uv run python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

> Why call `uvicorn` directly instead of `uv run python -m app.main`? `backend/app/main.py`'s `if __name__ == "__main__":` block sets `reload=True` for local hot-reload (see `/run-dev`). Production must never run with autoreload — calling `uvicorn` directly via `-m` bypasses that block entirely, with no code change needed, while still guaranteeing `backend/` (the working directory) is on `sys.path` the same way local dev relies on.

## 2. Create `.dockerignore`
At the repo root:

```
.git
.gitignore
**/__pycache__/
**/*.py[cod]
.venv
backend/logs/*
!backend/logs/.gitkeep
backend/uploads/*
!backend/uploads/.gitkeep
backend/tests
.pytest_cache

frontend/node_modules
frontend/dist
frontend/src
frontend/*.json
frontend/*.ts
frontend/*.html

ios
docs
README.md
CLAUDE.md
skills

.env
.env.*
!.env.example

.DS_Store
**/.DS_Store
.vscode
.idea
```

## 3. Create `render.yaml`
At the repo root. This Blueprint defines all four services — production and staging backend, production and staging frontend — pinned to `main` and `dev` respectively, per the branch model in `/github-workflow`. Service URLs on Render are deterministic (`https://<service-name>.onrender.com`), so `ALLOWED_ORIGINS` and `VITE_API_URL` are hardcoded to each other's predictable URLs below — no manual CORS wiring step after deploy.

```yaml
services:
  - name: agent-webapp-template-backend
    type: web
    env: docker
    dockerfilePath: ./Dockerfile
    dockerContext: ./
    plan: free
    branch: main
    healthCheckPath: /api/health
    envVars:
      - key: APP_ENV
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: HOST
        value: 0.0.0.0
      - key: ALLOWED_ORIGINS
        value: https://agent-webapp-template-frontend.onrender.com
      - key: DATABASE_URL
        sync: false
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: STORAGE_BUCKET
        value: uploads
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ANTHROPIC_MODEL
        value: claude-sonnet-4-6
      - key: LOG_LEVEL
        value: INFO

  - name: agent-webapp-template-backend-staging
    type: web
    env: docker
    dockerfilePath: ./Dockerfile
    dockerContext: ./
    plan: free
    branch: dev
    healthCheckPath: /api/health
    envVars:
      - key: APP_ENV
        value: staging
      - key: SECRET_KEY
        generateValue: true
      - key: HOST
        value: 0.0.0.0
      - key: ALLOWED_ORIGINS
        value: https://agent-webapp-template-frontend-staging.onrender.com
      - key: DATABASE_URL
        sync: false
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: STORAGE_BUCKET
        value: uploads
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ANTHROPIC_MODEL
        value: claude-sonnet-4-6
      - key: LOG_LEVEL
        value: DEBUG

  - name: agent-webapp-template-frontend
    type: web
    env: static
    rootDir: frontend
    buildCommand: npm ci && npm run build
    staticPublishPath: dist
    branch: main
    envVars:
      - key: VITE_API_URL
        value: https://agent-webapp-template-backend.onrender.com

  - name: agent-webapp-template-frontend-staging
    type: web
    env: static
    rootDir: frontend
    buildCommand: npm ci && npm run build
    staticPublishPath: dist
    branch: dev
    envVars:
      - key: VITE_API_URL
        value: https://agent-webapp-template-backend-staging.onrender.com
```

> Service names assume `agent-webapp-template-*` is available on Render. If a name is taken, Render appends a random suffix to the URL — if that happens, manually update `ALLOWED_ORIGINS` and `VITE_API_URL` in the dashboard to match the actual assigned URLs, then redeploy both affected services.

## 4. Sync the Blueprint
In the Render dashboard → **New → Blueprint** → connect the GitHub repo. Render detects `render.yaml` at the repo root and shows a preview of all 4 services it will create.

Confirm the sync. Render provisions:

| Service | Branch | Type |
|---|---|---|
| `agent-webapp-template-backend` | `main` | Docker web service |
| `agent-webapp-template-backend-staging` | `dev` | Docker web service |
| `agent-webapp-template-frontend` | `main` | Static site |
| `agent-webapp-template-frontend-staging` | `dev` | Static site |

The first deploy kicks off automatically for each service as soon as it's created.

## 5. Fill in secrets
`render.yaml` marks `SECRET_KEY` with `generateValue: true` — Render generates it automatically per service, no action needed. The remaining secrets are marked `sync: false` and must be entered manually, once, after the sync:

| Service | Variables to fill in |
|---|---|
| `agent-webapp-template-backend` | `DATABASE_URL` (prod Supabase pooler URL), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY` |
| `agent-webapp-template-backend-staging` | `DATABASE_URL` (staging Supabase pooler URL), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY` |

For each service in the Render dashboard → **Environment**, add the values, then save — this triggers a redeploy with the real secrets applied.

`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are optional (only needed if using `/setup-storage`) — leave blank if not using Supabase Storage.

---

## Verification
1. After the Blueprint sync, all 4 services should show a successful first deploy in the Render dashboard.
2. Visit `https://agent-webapp-template-backend.onrender.com/api/health` (and the `-staging` equivalent) — both should return `{"status": "ok"}`.
3. Visit `https://agent-webapp-template-frontend.onrender.com` (and the `-staging` equivalent) — the React app should load.
4. Trigger an action in the frontend that calls the API — check for CORS errors in the browser console. If present, confirm `ALLOWED_ORIGINS` on the backend exactly matches the frontend's actual URL (no trailing slash, correct prod/staging pairing).
5. Push a commit to `dev` — confirm the staging backend and staging frontend both redeploy automatically. Repeat for `main` and the production services.
6. Use `/mcp-render` to tail logs (`list_logs`) on any service that fails to start.

## Notes
- Free-tier Web Services spin down after 15 minutes of inactivity and take ~30s to cold-start on the next request. This applies to both backend services on `plan: free`. Upgrade the plan in the dashboard (or `render.yaml`) for production if this is unacceptable.
- Static sites are free by nature on Render — no `plan` field applies to them.
- Render injects `PORT` for Docker web services — the Dockerfile's `CMD` already binds `0.0.0.0:${PORT:-8000}`; do not hardcode a port elsewhere.
- Editing `render.yaml` and pushing it updates service configuration on the next sync (Render re-reads the Blueprint on push to a service's branch). Adding a brand-new service to the file requires a manual **Sync Blueprint** from the dashboard the first time.
- The Dockerfile is single-stage — appropriate while the backend has no heavy native build dependencies. If that changes (e.g. adding a package requiring compilation), consider a multi-stage build to keep the final image lean.
- `backend/alembic` has no migrations yet (`/add-migration` creates them). This Blueprint does not run migrations automatically on deploy — once migrations exist, add a manual step (or a Render **pre-deploy command**, available on paid plans) to run `uv run alembic upgrade head` before the app starts.
- Use Render's **Secret Files** (not environment variables) for any multi-line secrets or certificate files — not needed for the variables in this template today.
