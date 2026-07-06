# Architecture

Personal finance app with a double-entry bookkeeping core, an LLM pipeline that
turns uploaded statements into journal entries, and three clients: a React web
app, a native iOS app, and the FastAPI docs UI (non-prod only).

## System overview

```
┌─────────────┐   ┌──────────────┐
│  React SPA  │   │  iOS (Swift) │
└──────┬──────┘   └──────┬───────┘
       │  HTTPS / JSON           │
       └────────────┬────────────┘
                     ▼
            ┌──────────────────┐
            │   FastAPI app     │   Render web service (Docker)
            │  routes/services  │   prod: main branch
            │  agents (Pydantic-│   stage: dev branch
            │  AI + Claude)     │
            └─────────┬─────────┘
                       │ asyncpg
                       ▼
            ┌──────────────────┐        ┌────────────────┐
            │ Supabase Postgres │        │ Anthropic Claude│
            │ (schema owned by  │        │ (Sonnet, via    │
            │  Alembic)         │        │  Pydantic-AI)   │
            └──────────────────┘        └────────────────┘
```

The FastAPI process also serves the built frontend (`frontend/dist`) as static
files behind a SPA catch-all route, so in production there's a single deployed
service per environment, not separate frontend/backend hosts.

## Backend (`backend/`)

Layering is strict and one-directional: **routes → services → models / agents**.

- `routes/` — one `APIRouter` per resource (`accounts`, `auth`, `dashboard`,
  `documents`, `journal`, `ledger`, `periods`, `reconciliation`, `search`,
  `statements`, `transactions`). Routes only translate HTTP ↔ Pydantic schemas
  and map `AuthError`/`AgentError` to status codes — no business logic.
- `services/` — the actual business logic (`journal.py`, `period.py`,
  `reconciliation.py`, `classify.py`, `orchestrate.py`, `parse.py`, `apns.py`,
  etc.), operating on SQLAlchemy models via an injected `AsyncSession`.
- `models/` — SQLAlchemy 2.0 ORM classes: `Account`, `Period`, `Document`,
  `RawTransaction`, `JournalEntry`/`JournalLine`, `StatedBalance`,
  `Reconciliation`, `ReviewQueue`, `User`, `DeviceToken`.
- `schemas/` — Pydantic v2 request/response models. Never merged with `models/`.
- `dependencies/` — `Depends()` factories for the DB session, current user,
  and agents. No module-level singletons.
- `core/` — `config.py` (env-driven `Settings`), `logging.py`
  (`configure_logging()`), `ratelimit.py` (slowapi `limiter`).

### Request pipeline

`RequestIdMiddleware` → `SecurityHeadersMiddleware` → `SlowAPIMiddleware` →
`CORSMiddleware` → routed handler. Every request gets an `x-request-id`
(client-supplied or minted), stored in a `ContextVar` and included in every log
line for that request, then echoed back in the response header.

### Auth

JWT-based: short-lived Bearer access tokens + a long-lived refresh token in an
HttpOnly cookie scoped to `/api/v1/auth`. `services/auth.py` owns hashing, JWT
issuance/decoding, and user lookups; routes only translate `AuthError` into
HTTP responses. `get_current_user` (in `dependencies/`) protects routes.

**Single-user model.** Registration is closed by default
(`ALLOW_REGISTRATION=false`); the one operator account is created via
`backend/scripts/create_user.py`. Resource tables have no `user_id` and the
backend connects with full DB privileges (no Postgres RLS) — everything is
implicitly owned by that one account. This is deliberate, not an oversight:
adding real multi-user support requires retrofitting `user_id` + ownership
filters (ideally RLS-backed) on every resource table *before* registration is
ever opened up, or it's an IDOR waiting to happen.

## Data model (double-entry accounting)

- **`accounts`** — chart of accounts (`account_code`, `account_type` ∈
  Asset/Liability/Equity/Income/Expense/Memo Asset*, `normal_balance`).
- **`periods`** — a month-like accounting period with a status lifecycle
  (open → pending_review → … ), the unit that documents/transactions/entries
  belong to and that the close wizard operates on.
- **`documents`** — an uploaded statement/paystub, tied to a period and a
  `source_account_code`, with a `parse_status`.
- **`raw_transactions`** — line items extracted from a document before
  posting, carrying a classifier-suggested account + confidence.
- **`journal_entries` / `journal_lines`** — the posted, balanced double-entry
  records. Every entry's lines must net to zero.
- **`stated_balances`** — the balance an account *should* have per an external
  statement, used as the reconciliation target.
- **`reconciliation`** — computed vs. stated balance comparison per
  account/period, drives the close workflow.
- **`review_queue`** — ambiguous/flagged raw transactions awaiting manual
  resolution before posting.
- **`users`**, **`device_tokens`** — auth + APNs push registration.

Deleting a period cascades through all of the above (documents → raw
transactions → journal entries/lines → stated balances → reconciliation →
review queue); see `services/period.delete_period` and its regression test in
`backend/tests/test_periods.py`.

### Posting rules

- `paystub` and `mortgage_statement` documents post as **one balanced journal
  entry per document** (debit each component line, credit the source account
  for the total).
- `bank_statement`, `credit_card`, and `investment` documents post **one
  2-line entry per transaction**.
- The grouping logic lives in `journal.post_period`; new "compound" document
  types are added there.

## Agent pipeline (`app/agents/`)

Each agent module defines only a system prompt and a Pydantic output type,
then calls `build_agent()` / `run_agent()` from `_base.py`, which wires every
agent to the same Claude model (`settings.anthropic_model`, default
`claude-sonnet-4-6`) via Pydantic-AI's `AnthropicModel`/`AnthropicProvider`.
`run_agent` wraps any failure as `AgentError` so route handlers catch that one
narrow type instead of bare `Exception` — internal exception text never
reaches clients (mapped to a generic 502).

Flow, orchestrated by `services/orchestrate.py`:

1. **`orchestrator`** — given a batch of pending documents (filename,
   extension, short content peek) and the chart of accounts, resolves each
   document's type (`paystub` / `bank_statement` / `credit_card` /
   `investment` / `mortgage_statement` / `opening_balances`) and, where
   confidently identifiable, its `source_account_code`. Returns `null` rather
   than guessing.
2. **Type-specific extractors** — `statement.py` (bank/credit card/
   investment), `paystub.py`, `mortgage.py` — pull structured line items out
   of the document content.
3. **`classifier`** — assigns a suggested expense/income account + confidence
   to each extracted raw transaction.
4. **`reconciliation`** agent — assists reconciling computed vs. stated
   balances during period close.

Untrusted text (statement/paystub content, transaction descriptions) flows
into these prompts, but outputs stay structured Pydantic, and any value that
gets acted on (e.g. an account code) is validated against the DB before use —
see `services/classify.py`.

## Frontend (`frontend/`)

React 18 + TypeScript + Vite. `src/api/` holds one typed client module per
resource (mirroring the backend routers), `src/pages/` holds page-level
components (`DashboardPage`, `PeriodsListPage`/`PeriodDetailPage`,
`CloseWizardPage`, `LedgerPage`, `JournalPage`, `ReconcilePage`,
`StatementsPage`, `TransactionsPage`, `AccountsPage`), with `components/`,
`contexts/`, `hooks/`, and `utils/` shared across pages. Built output
(`frontend/dist`) is served directly by FastAPI in production — there is no
separate frontend host.

## iOS (`ios/`)

SwiftUI + WidgetKit native client, Swift Charts for visualizations (no
third-party chart libs), URLSession networking with no SPM runtime
dependencies. `Core/Networking` holds the API client and a `TokenRefresher`
actor; `Core/Auth` handles biometric app-lock and push registration.
`@DecimalString`/`@OptionalDecimalString` property wrappers
(`Core/Networking/JSONCoding.swift`) round-trip the backend's string-encoded
`Decimal` values — conversion to `Double` happens only at the chart boundary,
never in the models. Schemes select the backend per build (Debug → local,
Staging → Render staging, Release → Render prod). `project.yml` is the
XcodeGen source of truth; the `.xcodeproj` is generated and gitignored.

## Deployment topology

- **GitHub** (`tascoma/personal-finance-ai`) is the source of truth. Push to
  `main` deploys prod; push to `dev` deploys staging.
- **Render** hosts two Docker web services in `oregon`, both built from the
  same multi-stage `Dockerfile`:
  - `personal-finance-ai` (prod, tracks `main`)
  - `personal-finance-ai-stage` (staging, tracks `dev`)

  Each service's `preDeployCommand` runs `alembic upgrade head` before the new
  release takes traffic. `render.yaml` in the repo root declares a Render-
  managed `pfa-db` Postgres instance, but the live services' `DATABASE_URL` is
  set manually to point at Supabase instead (see below) — treat `render.yaml`
  as a partially-stale blueprint, not the live config.
- **Supabase** is the actual database, accessed via `asyncpg`. Schema is
  owned entirely by Alembic — never edit tables through the Supabase UI.
  - **Prod** — persistent main branch project, used by the prod Render
    service.
  - **Stage** — a persistent Supabase branch tied to git `dev`, used by the
    staging Render service and local dev. Bootstrapped empty (no prod data
    carryover).
  - Both `DATABASE_URL`s are the transaction-pooler URI on port 6543.
- **Anthropic** — Claude is the model behind every agent; requires
  `ANTHROPIC_API_KEY` (and `ANTHROPIC_MODEL` to override the default).

## Security notes

- Rate limiting (`slowapi`) on auth endpoints only counts correctly under a
  single uvicorn worker — the in-memory limiter state isn't shared across
  workers.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, HSTS in production) are applied to every response via
  `SecurityHeadersMiddleware`.
- API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled in production.
