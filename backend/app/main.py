import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import configure_logging, request_id_ctx
from app.core.ratelimit import limiter
from app.routes import (
    accounts as api_accounts,
    auth as api_auth,
    dashboard as api_dashboard,
    documents as api_documents,
    journal as api_journal,
    ledger as api_ledger,
    periods as api_periods,
    reconciliation as api_reconciliation,
    statements as api_statements,
    transactions as api_transactions,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    yield
    from app.databases import engine as _engine
    await _engine.dispose()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["x-request-id"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


_is_production = settings.app_env == "production"
app = FastAPI(
    title="Personal Finance Agent",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "x-request-id"],
)


@app.get("/health", include_in_schema=False)
async def health_check() -> dict:
    return {"status": "ok"}


# JSON API router — must be mounted before the SPA catch-all
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(api_auth.router)
api_router.include_router(api_dashboard.router)
api_router.include_router(api_accounts.router)
api_router.include_router(api_ledger.router)
api_router.include_router(api_statements.router)
api_router.include_router(api_periods.router)
api_router.include_router(api_documents.router)
api_router.include_router(api_transactions.router)
api_router.include_router(api_journal.router)
api_router.include_router(api_reconciliation.router)
app.include_router(api_router)

# SPA catch-all: serve frontend/dist/index.html for any unmatched non-API path.
# Must be registered last so it never shadows API routes.
FRONTEND_DIST = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=f"{FRONTEND_DIST}/assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa_fallback(full_path: str) -> FileResponse | Response:
        if full_path.startswith("api/"):
            return Response(status_code=404)
        return FileResponse(f"{FRONTEND_DIST}/index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_excludes=["logs/*"],
    )
