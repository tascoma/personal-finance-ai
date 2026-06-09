# syntax=docker/dockerfile:1.7

# ─── Stage 1: build the React frontend ─────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: backend runtime ──────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install Python deps first (cached layer keyed on lockfile only).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy backend source and migration assets.
COPY backend/ ./backend/

# Copy the built SPA — main.py resolves `parents[2] / "frontend" / "dist"`
# from /app/backend/app/main.py, which lands at /app/frontend/dist.
COPY --from=frontend-build /frontend/dist ./frontend/dist

WORKDIR /app/backend

EXPOSE 8000

# Render injects $PORT; use shell form so it expands at runtime.
# Single worker on purpose: the in-process slowapi rate limiter (app/core/ratelimit.py)
# keeps per-worker state, so multiple workers would split and weaken the auth limit.
# Safe here — single Render instance, one operator, TCP (not HTTP) health check.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
