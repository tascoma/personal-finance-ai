from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "changeme"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/finance"
    anthropic_api_key: str = ""
    host: str = "127.0.0.1"
    port: int = 8000

    # Comma-separated list of allowed CORS origins (e.g. "http://localhost:5173,http://localhost:4173").
    allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    log_level: str = "INFO"

    # Single-user deployment: registration is disabled by default. Operator provisions
    # the one account via `backend/scripts/create_user.py`. Set ALLOW_REGISTRATION=true
    # only for local development or tests.
    allow_registration: bool = False

    # Equity account used as the offset when posting opening-balance uploads.
    # Defaults to 300102 "Prior Period Net Worth" from the seed Chart of Accounts.
    opening_balance_equity_account_code: int = 300102

    # Claude model applied to all agents; override via env to switch versions.
    anthropic_model: str = "claude-sonnet-4-6"

    # Database connection options
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    @property
    def db_connect_args(self) -> dict:
        return {"statement_cache_size": 0} if self.database_url.startswith("postgresql") else {}

    # Maximum file upload size in megabytes
    max_upload_size_mb: int = 20

    # Apple Push Notification service (APNs). All four key/team/bundle/p8
    # settings must be set for `app.services.apns.notify_user()` to attempt
    # delivery — otherwise it's a graceful no-op. The .p8 value is the file
    # contents (multi-line PEM), provided via env var in a single line with
    # \n escapes for Render's env-var UI.
    apns_auth_key_p8: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = "com.tascoma.personalfinanceai"
    # True for Debug/Staging builds (registered with APNs sandbox); False for
    # TestFlight/App Store (registered with prod APNs). The simulator's APNs
    # env is the sandbox, so this should be True for local dev too.
    apns_use_sandbox: bool = True

    model_config = {"env_file": Path(__file__).resolve().parents[3] / ".env"}

    @model_validator(mode="after")
    def _normalize_database_url(self) -> "Settings":
        # Render's managed Postgres injects URLs as `postgresql://...`; SQLAlchemy needs
        # an explicit async driver. Rewrite only when no driver is specified.
        if self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+asyncpg://" + self.database_url[len("postgresql://"):]
        return self

    @model_validator(mode="after")
    def _check_production_secret(self) -> "Settings":
        if self.app_env == "production" and self.secret_key == "changeme":
            raise ValueError("SECRET_KEY must be set to a non-default value in production")
        return self


settings = Settings()
