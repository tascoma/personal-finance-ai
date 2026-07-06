---
name: "run-dev"
description: "Run the backend and frontend locally together with hot reload"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Run the full stack locally: the FastAPI backend on port 8000 and the React (Vite) frontend on port 5173, with the Vite dev server proxying `/api/*` to the backend. Run each side in its own terminal.

## Prerequisites
- `.env` exists at the repo root (copy from `.env.example` — see `/setup`).
- Backend deps installed: `uv sync` from the repo root.
- Frontend deps installed: `npm install` from `frontend/` (see `/setup-frontend`).

## Steps

### 1. Start the backend
From `backend/`:

```bash
uv run python -m app.main
```

Uvicorn serves on `http://localhost:8000` with `reload=True` — code changes restart the server automatically. Logs stream to stdout and `backend/logs/`.

### 2. Start the frontend
In a second terminal, from `frontend/`:

```bash
npm run dev
```

Vite serves on `http://localhost:5173`. Its dev proxy forwards `/api/*` to `http://localhost:8000`, so the browser never hits CORS — the frontend calls `/api/...` and the backend answers.

### 3. Work against the running stack
Edit backend code → uvicorn reloads. Edit frontend code → Vite hot-module-replaces in the browser. Keep both terminals open while developing.

## Verification
- `http://localhost:8000/docs` loads the FastAPI Swagger UI.
- `http://localhost:5173` loads the React app.
- A frontend request to `/api/<an existing route>` returns data with no CORS error in the browser console. If `/api` calls 404, confirm the Vite proxy target and the backend router prefixes match.
