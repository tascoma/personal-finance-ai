# Improvement Backlog

Findings from a codebase scan on 2026-06-07 (branch `dev`). Baseline is healthy: 211
backend tests pass, `tsc --noEmit` is clean, no stray `TODO`/`print()`/`console.log`/`any`.
These are opportunities, ordered roughly by value-to-effort within each section.

## Frontend

### Dashboard hardcoded year (`pages/DashboardPage.tsx`)
The target year `2026` is hardcoded in several places and will silently rot at year-end:
- `targetYear = 2026` ([:95](../frontend/src/pages/DashboardPage.tsx#L95))
- forecast fallback `[2026, 12]` and `monthsRemaining` math ([:247-248](../frontend/src/pages/DashboardPage.tsx#L247-L248))
- copy: "2026 contribution limits" ([:435](../frontend/src/pages/DashboardPage.tsx#L435)),
  "EOY 2026" ([:824](../frontend/src/pages/DashboardPage.tsx#L824)),
  "projected through Dec 2026" ([:847](../frontend/src/pages/DashboardPage.tsx#L847))

Extract a single `targetYear` derived from `new Date().getFullYear()` and reference it everywhere.

### Retirement "On track" badge is static
The badge at [DashboardPage.tsx:437](../frontend/src/pages/DashboardPage.tsx#L437) always renders
"On track". Derive it from whether `retirementPct` ([:315](../frontend/src/pages/DashboardPage.tsx#L315))
is on pace for the current month (e.g. `retirementPct >= monthOfYear/12 * 100`), and color it
red/amber when behind.

### Native `window.confirm` dialogs
Eight destructive actions use the browser-native `window.confirm`, which looks off-brand and
isn't testable: PeriodDetailPage ([:358](../frontend/src/pages/PeriodDetailPage.tsx#L358),
[:363](../frontend/src/pages/PeriodDetailPage.tsx#L363), [:365](../frontend/src/pages/PeriodDetailPage.tsx#L365),
[:580](../frontend/src/pages/PeriodDetailPage.tsx#L580)),
JournalPage ([:206](../frontend/src/pages/JournalPage.tsx#L206), [:340](../frontend/src/pages/JournalPage.tsx#L340)),
CloseWizardPage ([:919](../frontend/src/pages/CloseWizardPage.tsx#L919)),
ReconcilePage ([:249](../frontend/src/pages/ReconcilePage.tsx#L249)).
Build one shared `ConfirmDialog` component and replace all eight.

### No toast / success feedback
Mutations (save balances, post, parse, delete) have no success affordance — the UI just
mutates. A lightweight toast/snackbar context would give consistent feedback across pages
and replace the silent saves.

### Oversized page components
- `CloseWizardPage.tsx` — 986 lines
- `DashboardPage.tsx` — 860 lines (four tabs; split into `OverviewTab`/`InsightsTab`/`AssetsTab`/`ForecastTab`)
- `PeriodDetailPage.tsx` — 623 lines
- `StatementsPage.tsx` — 587 lines

These are the four largest source files in the repo. Splitting tab/section content into
child components keeps them navigable and reduces re-render scope.

### Asset growth tiles
Confirm the "Period Growth" / "YTD Growth" KPI tiles in the Assets tab are computed and not
placeholder `"—"`; if still placeholders, compute from `asset_series` client-side or add the
fields to the `/dashboard` response.

## Backend

### Auth has no rate limiting / brute-force protection
No `slowapi`/limiter/throttle anywhere in `app/`. `POST /auth/login` and the refresh endpoint
are unthrottled. Even single-user, add a simple per-IP attempt limiter (or fail2ban-style
backoff) on the auth routes. See [routes/auth.py](../backend/app/routes/auth.py).

### Upload reads whole file into memory before size check
[services/document.py:85-89](../backend/app/services/document.py#L85-L89) does
`await upload.read()` then checks length. A large upload is fully buffered before rejection.
Stream to disk in chunks and abort once `max_upload_size_mb` is exceeded. Low priority for a
single-user deployment, but cheap to harden.

### No pagination on list endpoints
List routes (transactions, journal entries, periods) return full result sets. Fine at current
data volume, but transactions/journal will grow unbounded over time — add `limit`/`offset`
(or keyset) pagination before it becomes a problem.

### `statement_mapper` service has no direct test coverage
Every other service is referenced in tests except
[services/statement_mapper.py](../backend/app/services/statement_mapper.py). Add a focused
unit test for the mapping logic.

## iOS

### No test target
No test files exist anywhere under `ios/`. The networking layer is the highest-value place to
start: `@DecimalString` round-tripping (string ↔ Decimal), `TokenRefresher` actor behavior,
and APIClient error mapping. Add a unit test target to `project.yml` and cover these.

## Tooling & dependencies

### npm moderate vulnerabilities (4)
`npm audit` reports 4 moderate issues:
- `react-router` 6.7.0–6.30.3 — fixable with `npm audit fix` (non-breaking).
- `esbuild` ≤0.24.2 (dev-server request leak, transitive via Vite) — only fixable via
  `npm audit fix --force` which bumps Vite (breaking); dev-only impact.

Apply the react-router fix now; schedule the Vite/esbuild major bump deliberately. **Regenerate
the lockfile with `npx -y npm@10.8.2 install`** per the CLAUDE.md Render build constraint.

### Per-service READMEs
Only root `README.md` and `ios/README.md` exist. A short `backend/README.md` (run/test/migrate)
and `frontend/README.md` (dev/build) would lower onboarding friction; much of it can lift from
CLAUDE.md.
</content>
