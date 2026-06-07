"""Shared slowapi limiter.

Single instance imported by both `main.py` (to register the middleware and the
RateLimitExceeded handler) and the route modules (for the `@limiter.limit` decorator).

Uses slowapi's default in-memory storage, which is correct for the single Render
instance this app runs on. A multi-instance deployment would need a shared backend
(e.g. Redis via the `storage_uri` argument).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
