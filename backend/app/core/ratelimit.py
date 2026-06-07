"""Shared slowapi limiter.

Single instance imported by both `main.py` (to register the middleware and the
RateLimitExceeded handler) and the route modules (for the `@limiter.limit` decorator).

Uses slowapi's default in-memory storage, which is correct for the single Render
instance this app runs on. A multi-instance deployment would need a shared backend
(e.g. Redis via the `storage_uri` argument).
"""

from starlette.requests import Request

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def auth_limit_key(request: Request) -> str:
    """Constant key so auth endpoints share one global rate-limit bucket.

    Behind Render's proxy the per-request client IP isn't stable (the app sees the
    proxy, and Render fronts it with more than one source IP), so the default
    per-IP key splits the count into several buckets and the limit never bites.
    A single global bucket is the right model for this single-account deployment:
    it caps total login/refresh attempts and can't be sidestepped by IP rotation.
    """
    return "auth"
