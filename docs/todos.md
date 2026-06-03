# UI/UX Todos — ui-rehaul branch

## 1. Dashboard tabs (Overview · Insights · Assets · Forecast)

### Overview
- [ ] Asset composition ring: limit legend to 5 rows and add an "Other" slice for the remainder instead of slicing the data silently at 6
- [ ] Retirement progress card: the "On track" badge is always hardcoded — derive it from whether `retirementPct` is on pace for the current month of the year
- [ ] Hero delta stat "vs. prior period" shows a raw percentage — add a ± color (green/red) to match the YTD delta style
- [ ] "Active period" card only renders if `data.active_period` exists — when there is no active period the right column of the Income vs Expenses grid disappears and the chart stretches to `col-12`; constrain the chart column in that case

### Insights
- [ ] KPI row: `Expenses Δ` compares only the last two bars — clarify this in the sub-label (e.g. "vs. prior period")
- [ ] "Category Spend vs Compensation" chart falls back to an EmptyState when `compensation_income` is `0`, but gives no actionable hint about which account type drives that field; add a hint

### Assets
- [ ] KPI tiles for "Period Growth" and "YTD Growth" are hardcoded `"—"` — either compute them from `asset_series` client-side or add the fields to the `/dashboard` API response
- [ ] Asset Growth line chart draws a gradient fill but `assetGrowthRef.current.clientHeight` is `0` at paint time (canvas not yet laid out), so the gradient stop is wrong — read the height after a `requestAnimationFrame` or use a fixed pixel height

### Forecast
- [ ] Target year (`2026`) is hardcoded in three separate places — extract to a single constant and derive `monthsRemaining` dynamically from the current date
- [ ] Projection subtitle "historical + projected through Dec 2026" also hardcodes the year — tie it to the constant above
- [ ] When `avgMonthlyNet` is negative the projected EOY can be less than the current net worth; add a note or colour cue to the KPI grid so the negative trajectory is obvious at a glance

### Cross-cutting dashboard
- [ ] `DashboardPage` is ~745 lines; split tab content into separate components (`OverviewTab`, `InsightsTab`, `AssetsTab`, `ForecastTab`) to keep the file navigable
- [ ] Chart cleanup: four separate `useEffect` hooks each destroy and recreate Chart.js instances on every data change — consolidate into one effect or use a `useChart` hook
- [ ] The `KPI` component is defined at the bottom of `DashboardPage.tsx` — move it to `components/KPI.tsx` since it's already used across three tabs

---

## 2. Workflow UX/UI

### Close wizard (`CloseWizardPage`)
- [ ] Step 3 (Stated balances): the `<input>` uses `defaultValue` — changes are never saved; wire up an `onBlur` / submit handler that calls `saveBalances` (the API function already exists in `api/periods.ts`)
- [ ] Step 4 (Reconcile): the "Fix" button per gap row has no handler — it should either navigate to the Reconcile tab on `PeriodDetailPage` or open an inline adjustment form
- [ ] The `window.confirm()` in step 5 ("Close this period?") is a browser-native dialog — replace with the same delete-confirm modal pattern already used in `PeriodDetailPage`
- [ ] Wizard `completed` state is client-only; refreshing the page resets to step 0 — derive initial `step` and `completed` from `period.status` so the wizard resumes at the right place
- [ ] Doc list in step 0 is capped at 6 with no indication that more exist — show a count or scroll the list

### Period detail (`PeriodDetailPage`)
- [ ] `PeriodStepper` in the Overview card and on the dashboard links to "Continue close" which goes to `PeriodDetailPage`, not the wizard — decide the canonical entry point and make both links consistent (probably the wizard)
- [ ] Stated balances tab: inputs save on blur, but there's no success feedback (toast / inline confirmation) after `saveBalances` resolves
- [ ] "Parse all pending" orchestration result (`orchestrationResult`) renders a raw JSON-like object in some code paths — format it as a summary card (parsed count, failed count, new transactions)
- [ ] Manual transaction entry form (`txnRows`) has no validation before submission — at minimum check that `date`, `amount`, and `account` are non-empty and show field-level errors

### Periods list (`PeriodsListPage`)
- [ ] Period cards show a `StatusBadge` but no quick-action button — add a "Continue" / "View" button that routes to the wizard for in-progress periods and to `PeriodDetailPage` for closed ones

### Shared workflow components
- [ ] `WorkflowHint` is rendered in `PeriodDetailPage` but its content is a static `STATUS_HINTS` string — consider linking the hint text to the relevant tab so users know exactly where to go next
- [ ] `ConfidencePill` in the classify table is purely decorative — add a tooltip that explains the confidence levels (high / medium / low thresholds)
