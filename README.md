# Personal Finance AI

A personal double-entry accounting system with an AI-powered document and transaction intelligence backend, a React web frontend, and a native SwiftUI iOS companion app. Upload bank statements, paystubs, and mortgage documents; let AI agents extract and classify transactions; then follow a structured monthly close workflow to maintain an accurate general ledger.

## Stack

### Backend
- **FastAPI** — async web framework with dependency injection
- **Pydantic AI** — structured LLM agent framework (Claude Sonnet 4.6)
- **Pydantic v2** — request/response schemas and settings via `BaseSettings`
- **SQLAlchemy 2.0** — async ORM with asyncpg driver (PostgreSQL / Supabase)
- **Alembic** — database schema migration management
- **python-jose** — JWT access and refresh token generation/validation
- **bcrypt** — password hashing
- **uv** — dependency and virtual environment management

### Frontend
- **React 18** + **TypeScript** — component-based SPA
- **Vite** — dev server and build tool

### iOS app
- **SwiftUI** + **Swift Charts** — UI and dashboard visualisations
- **WidgetKit** — Home Screen widget (net worth + monthly cash flow)
- **LocalAuthentication** — Face ID / Touch ID app lock
- **APNs** — push notifications for period status changes
- **XcodeGen** — `ios/project.yml` is the source of truth; the `.xcodeproj` is generated. Min target iOS 17

## Platforms

External services this app depends on:

- **GitHub** (`tascoma/personal-finance-ai`) — source repository. Pushes to `main` deploy to prod; pushes to `dev` deploy to staging.
- **Render** — runs two Dockerized web services in the `oregon` region, each with its own `DATABASE_URL`:
  - **Production** (`personal-finance-ai`) — tracks `main`, at https://personal-finance-agent-ipuu.onrender.com
  - **Staging** (`personal-finance-ai-stage`) — tracks `dev`, at https://personal-finance-agent-1-tqet.onrender.com
- **Supabase** — managed PostgreSQL accessed via `asyncpg`; schema managed by Alembic (not Supabase's UI). Two databases via Pro-plan branching:
  - **Prod project** — the persistent main branch; the Render prod service and local `.env` connect here
  - **Stage branch** — persistent, tied to git `dev`; the Render staging service connects here. Schema is promoted by merging `dev` → `main`
- **Anthropic (Claude)** — LLM backing the Pydantic-AI agents under `app/agents/`; requires `ANTHROPIC_API_KEY`
- **PyPI** (via `uv`), **npm registry**, and **Docker Hub / GHCR** — package and base-image sources used at build time

## Features

- **Authentication** — JWT-based user registration, login, token refresh, and logout; access tokens via Bearer header, refresh tokens via HttpOnly cookie
- Upload and AI-parse bank/credit card statements, paystubs, and mortgage statements (PDF, CSV, XLSX)
- AI transaction classifier assigns account codes with confidence scores
- Double-entry journal with debit/credit constraints enforced at the DB level
- Period-based monthly close workflow: `open → pending_review → pending_close → closed`
- Reconciliation engine comparing computed book balances to stated bank balances
- AI reconciliation analyzer surfaces likely gap causes and remediation steps
- Automatic closing entries to zero income/expense accounts and roll equity
- Financial statements: Balance Sheet, Income Statement, Cash Flow Statement
- Dashboard with net worth trends, top expense categories, and a retirement savings rate KPI (retirement contributions ÷ salary + bonus)
- Native iOS app: read-only Dashboard + Statements, Home Screen widget, Face ID lock, push notifications on period status changes
- Per-request `x-request-id` correlation between client and server logs

## Getting started

### 1. Install dependencies

From the project root:

```bash
uv venv
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env` (lives at the project root). Get the `DATABASE_URL` from **Supabase → Project Settings → Database → Transaction pooler** (URI tab, port 6543):

```env
APP_ENV=development
SECRET_KEY=changeme                  # must be a strong random value in production
DATABASE_URL=postgresql+asyncpg://postgres.YOUR_PROJECT_REF:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
ANTHROPIC_API_KEY=your-api-key-here
ALLOWED_ORIGINS=http://localhost:5173
ACCESS_TOKEN_EXPIRE_MINUTES=60       # optional, default 60
REFRESH_TOKEN_EXPIRE_DAYS=30         # optional, default 30
```

### 3. Apply database migrations

```bash
cd backend
alembic upgrade head
```

This creates all tables in your Supabase database. Run this once on first setup and after pulling any schema changes.

### 4. Run the backend

```bash
cd backend
uv run python -m app.main
```

Or directly with uvicorn:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

The API starts at `http://127.0.0.1:8000`.

### 5. Run the frontend dev server

```bash
cd frontend
npm install   # first time only
npm run dev
```

The UI is served at `http://localhost:5173` and proxies API requests to the backend.

### 6. (Optional) Run the iOS app

The iOS app lives under [`ios/`](ios/) and uses XcodeGen, so the `.xcodeproj` is generated rather than checked in:

```bash
brew install xcodegen
cd ios
xcodegen
open PersonalFinanceAI.xcodeproj
```

Pick a scheme in Xcode to choose which backend to talk to:

| Scheme  | Backend |
| ------- | ------- |
| Debug   | `http://127.0.0.1:8000` (run the backend locally) |
| Staging | https://personal-finance-agent-1-tqet.onrender.com |
| Release | https://personal-finance-agent-ipuu.onrender.com |

See [`ios/README.md`](ios/README.md) for the auth/cookie flow, the `@DecimalString` property wrappers used to round-trip backend money, widget setup, and push notification configuration.

### 7. Run tests

Tests use an in-memory SQLite database and do not require a live PostgreSQL connection:

```bash
uv run pytest
```

## Authentication

The API uses JWT-based authentication. All routes except `/api/v1/auth/register` and `/api/v1/auth/login` require a valid Bearer token.

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/auth/register` | POST | Create a new user account |
| `/api/v1/auth/login` | POST | Authenticate and receive an access token; sets an HttpOnly refresh-token cookie |
| `/api/v1/auth/refresh` | POST | Exchange the refresh-token cookie for a new access token |
| `/api/v1/auth/logout` | POST | Clear the refresh-token cookie |
| `/api/v1/auth/me` | GET | Return the currently authenticated user |

Access tokens expire after 60 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`). The refresh token is stored as an HttpOnly cookie scoped to `/api/v1/auth` and expires after 30 days (configurable via `REFRESH_TOKEN_EXPIRE_DAYS`). In production, ensure `SECRET_KEY` is set to a strong random value — the app will refuse to start otherwise.

## Monthly close workflow

Each accounting period follows a linear status progression. Here's the full workflow from period creation to close.

### 1. Open a period

Create a new accounting period for the month. Each calendar month can have at most one period.

### 2. Upload documents

Upload supporting documents — bank/credit card statements, paystubs, mortgage statements. The system accepts PDF, CSV, and XLSX formats. AI agents parse each document and stage extracted transactions for review.

### 3. Classify transactions

Set the source account (e.g., the checking account) for each document. Run the AI classifier to assign suggested account codes and confidence scores to unclassified transactions. Low-confidence suggestions (<0.7) are flagged for manual review. Approve or reject each transaction.

### 4. Post to journal

Advance the period to `pending_close`. Review approved transactions and optionally add manual journal entries for adjustments. Post all approved transactions to the general ledger as double-entry journal entries.

### 5. Reconcile

Enter stated ending balances from bank statements. Run the reconciliation engine to compute the gap between book and stated balances. Optionally invoke the AI reconciliation analyzer to identify likely causes (missing transactions, duplicates, timing differences). Post adjusting entries where needed.

### 6. Close

Post closing entries to zero out income and expense accounts and roll net income into equity. Close the period. Closed periods can be reopened for corrections.

## AI agents

The app uses a small set of focused Pydantic-AI agents (each = one prompt + one output schema, all sharing the factory in [`app/agents/_base.py`](backend/app/agents/_base.py)). An **Orchestrator** agent sits on top of the extraction agents and decides per-document which sub-agent should run.

| Agent | Role | When it runs |
|---|---|---|
| **Orchestrator** | Reads a digest (filename + declared type + a short content peek) for every pending document and returns a routing plan — the resolved type for each document and whether classification should follow | Once per "Parse" click |
| **Statement Extractor** | Extracts date, description, and signed amount per transaction from bank / credit-card / investment statement PDFs | Per document, when orchestrator routes there |
| **Paystub Extractor** | Extracts payroll line items (earnings, deductions, taxes, net pay) from paystub PDFs | Per document, when orchestrator routes there |
| **Mortgage Extractor** | Extracts principal, interest, escrow, property tax, and insurance amounts from mortgage statement PDFs | Per document, when orchestrator routes there |
| **Transaction Classifier** | Assigns chart-of-accounts codes with confidence scores; considers source account type for sign interpretation | Once per period after extraction, only if any document required classification |
| **Reconciliation Analyzer** | Identifies likely causes of reconciliation gaps and suggests remediation steps | Reconciliation phase, separate from parse |

### How they work together

The Orchestrator follows a **plan-then-execute** pattern. One LLM call decides routing for the entire batch; deterministic Python then invokes the existing extractors and classifier based on that plan. This keeps the LLM in charge of *delegation* while extraction itself stays in well-tested code paths.

Agents (LLM-backed) are drawn with the double-rectangle `[[ ]]` shape; everything else is deterministic Python.

```mermaid
flowchart TD
    User([User])
    Upload[Upload N documents<br/>multi-file picker]
    Click{{Click Parse}}
    Route["POST /periods/:id/orchestrate-parse"]
    Digest["Build per-document digest<br/>filename, declared type, content peek"]
    Orch[["Orchestrator Agent<br/>1 LLM call for whole batch"]]
    Plan["OrchestrationPlan<br/>resolved_type + run_classifier per doc"]
    Correct["Persist document_type corrections<br/>declared ≠ resolved"]

    Stmt[["Statement Extractor"]]
    Pay[["Paystub Extractor"]]
    Mort[["Mortgage Extractor"]]
    Det["Deterministic CSV/XLSX mapper<br/>no LLM"]

    NeedClass{Any step<br/>requested<br/>classification?}
    Class[["Transaction Classifier<br/>runs once for the period"]]

    Staged[(Raw transactions<br/>status=staged)]
    Final[(Suggested account codes<br/>+ confidence)]
    Done([Done])

    User --> Upload --> Click --> Route --> Digest --> Orch --> Plan --> Correct
    Correct -->|paystub| Pay
    Correct -->|mortgage_statement| Mort
    Correct -->|bank/credit/investment .pdf| Stmt
    Correct -->|bank/credit/investment .csv or .xlsx| Det

    Pay --> Staged
    Mort --> Staged
    Stmt --> Staged
    Det --> Staged

    Staged --> NeedClass
    NeedClass -->|yes| Class --> Final --> Done
    NeedClass -->|no| Done
```

Walk-through of one "Parse" click:

1. **Digest build** — the orchestrate service reads each pending document and extracts a small peek: ~800 characters for PDFs, ~10 rows for CSV/XLSX. The full file is never sent to the orchestrator.
2. **Single orchestrator call** — one LLM call with the batch of digests returns an `OrchestrationPlan` covering every document. The orchestrator is free to *override* the user's declared `document_type` when the content disagrees (e.g. a paystub mistakenly uploaded as a bank statement).
3. **Type correction is persisted** — if the orchestrator's `resolved_type` differs from the declared one, the `Document.document_type` column is updated before extraction runs.
4. **Per-document extraction** — the service calls the existing `parse_document` flow, which dispatches to the right extractor agent (or a deterministic CSV/XLSX mapper) based on the resolved type and file extension. A failure on one document does not abort the others.
5. **Optional classification** — if any planned step set `run_classifier=true` (true only for bank/credit-card documents) and at least one document parsed successfully, the Transaction Classifier runs once for the period to assign suggested account codes and confidence scores.
6. **Result** — the endpoint returns an `OrchestrationResult` with per-document outcomes (declared type, resolved type, whether reclassified, success/error) plus aggregate counts for the UI to display.

## Project structure

```
personal-finance-ai/
├── backend/
│   ├── alembic/                 # Alembic migration environment
│   │   └── versions/            # Migration scripts
│   ├── alembic.ini              # Alembic config
│   ├── app/
│   │   ├── main.py              # FastAPI app instance, router includes, lifespan
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic BaseSettings (env-driven)
│   │   │   └── logging.py       # Logging configuration
│   │   ├── databases/           # SQLAlchemy engine and session factory
│   │   ├── dependencies/        # Shared Depends() factories (get_current_user, get_db_session)
│   │   ├── routes/              # APIRouter modules (auth, dashboard, accounts, ledger, periods…)
│   │   ├── models/              # SQLAlchemy ORM models (User, …)
│   │   ├── schemas/             # Pydantic request/response schemas (auth, …)
│   │   ├── agents/              # Pydantic AI agents (classifier, statement, paystub, mortgage, reconciliation) + shared _base.py factory
│   │   └── services/            # Business logic layer (auth, …)
│   ├── scripts/                 # One-off operational/diagnostic scripts
│   ├── tests/                   # pytest suite (SQLite in-memory)
│   ├── logs/                    # Runtime logs (gitignored)
│   └── uploads/                 # Uploaded documents (gitignored)
├── frontend/
│   ├── src/
│   │   ├── api/                 # Typed API client
│   │   ├── components/          # Shared React components (incl. ErrorBoundary)
│   │   ├── contexts/            # React contexts (AuthContext)
│   │   ├── pages/               # Page-level components
│   │   ├── types/               # TypeScript types
│   │   └── utils/
│   ├── index.html
│   └── vite.config.ts
├── ios/
│   ├── project.yml              # XcodeGen spec — generates the .xcodeproj
│   ├── App/                     # @main entry, root view, environment wiring
│   ├── Config/                  # xcconfig per scheme (Debug/Staging/Release)
│   ├── Core/                    # Networking, Auth, Models (Pydantic mirrors)
│   ├── Features/                # Login, Dashboard, Statements, Settings
│   ├── Widget/                  # WidgetKit Home Screen widget
│   ├── Shared/                  # Code shared between app + widget
│   └── README.md                # iOS-specific setup, auth model, conventions
├── .env                         # Local secrets (gitignored)
├── .env.example                 # Documents required env vars
├── pyproject.toml
└── uv.lock
```

## Domain concepts

**Account** — A chart-of-accounts entry with a numeric code, type (Asset / Liability / Equity / Income / Expense), normal balance (debit or credit), and optional paystub label mapping.

**Period** — A calendar month with a linear status lifecycle. Only one period per month is allowed.

**Document** — An uploaded file linked to a period with a type (statement, paystub, mortgage, manual) and a source account representing where the money flows from.

**Raw Transaction** — An extracted transaction staged for review. Carries a suggested account code, classifier confidence score, and a dedup hash for duplicate detection. Status flows: `staged → approved → posted` (or `rejected`).

**Journal Entry / Journal Line** — A double-entry journal entry header with one or more debit/credit lines. The DB enforces that exactly one of `debit_amount` or `credit_amount` is non-zero per line.

**Reconciliation** — A per-account, per-period record comparing the computed book balance (from journal entries) against the user-entered stated balance. Gap = stated − computed. Status: `pending` (gap exists), `reconciled` (gap = 0), or `adjusted` (adjusting entry posted).
