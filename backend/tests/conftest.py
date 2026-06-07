import os

# Provide a dummy key so Agent(...) construction succeeds at import time.
# Tests patch run_* functions directly, so this key is never sent to the API.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

# Public registration is disabled by default (single-user deployment); the test
# suite exercises the /auth/register endpoint, so re-enable it for tests.
os.environ.setdefault("ALLOW_REGISTRATION", "true")

# Most auth tests hammer /login many times; raise the per-IP rate limit so it
# never trips except in the dedicated rate-limit test (which overrides it).
os.environ.setdefault("AUTH_RATE_LIMIT", "100000/minute")
