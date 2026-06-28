// ── Orchestration streaming events ─────────────────────────────────

export type OrchestrationEventKind =
  | 'planning'
  | 'planned'
  | 'parsing'
  | 'parsed'
  | 'classifying'
  | 'complete'
  | 'error'

export interface OrchestrationEvent {
  event: OrchestrationEventKind
  doc_count?: number
  file_name?: string
  index?: number
  total?: number
  status?: 'complete' | 'failed' | 'needs_review'
  txn_count?: number
  parsed?: number
  failed?: number
  needs_review?: number
  classifier_ran?: boolean
  classifier_updated?: number
  message?: string
}

// ── Core domain types ──────────────────────────────────────────────

export type PeriodStatus = 'open' | 'pending_review' | 'pending_close' | 'closed'

export interface Account {
  account_code: number
  account_name: string
  account_type: string
  sub_category: string
  normal_balance: string
  paystub_mapping: string | null
  is_memo: boolean
  is_active: boolean
}

export interface Period {
  period_id: string
  period_start: string
  period_end: string
  status: PeriodStatus
  closed_at: string | null
  created_at: string
}

export interface JournalEntry {
  entry_id: string
  period_id: string
  entry_date: string
  description: string
  source_type: string
  source_document_id: string | null
  is_adjusting: boolean
  is_closing: boolean
  created_by: string
  created_at: string
}

export interface JournalLine {
  line_id: string
  entry_id: string
  account_code: number
  debit_amount: string
  credit_amount: string
  memo: string | null
}

export interface JournalEntryWithLines extends JournalEntry {
  lines: JournalLine[]
}

export interface Document {
  document_id: string
  period_id: string
  document_type: string
  file_name: string
  file_path: string
  source_account_code: number | null
  parse_status: string
  parsed_at: string | null
  llm_model: string | null
  created_at: string
}

export interface RawTransaction {
  raw_txn_id: string
  document_id: string
  period_id: string
  txn_date: string
  description: string
  amount: string
  suggested_account_code: number | null
  classifier_confidence: string | null
  is_flagged: boolean
  is_duplicate: boolean
  dedup_hash: string | null
  status: string
  journal_entry_id: string | null
  created_at: string
}

export interface ReconciliationDetail {
  recon_id: string
  period_id: string
  account_code: number
  account_name: string
  is_investment: boolean
  beginning_balance: string
  period_net_change: string
  computed_balance: string
  stated_balance: string
  gap: string
  status: string
  run_at: string
}

export interface TempAccountLine {
  account_code: number
  account_name: string
  account_type: string
  sub_category: string
  normal_balance: string
  period_balance: string
}

export interface TempAccountPreview {
  income_accounts: TempAccountLine[]
  expense_accounts: TempAccountLine[]
  total_income: string
  total_expenses: string
  net_income: string
  closing_posted: boolean
}

export interface EquityRollupPreview {
  net_income_balance: string
  rollup_posted: boolean
}

// ── Dashboard ──────────────────────────────────────────────────────

export interface PeriodBarPoint {
  period_label: string
  income: string
  expenses: string
  net: string
}

export interface NetWorthPoint {
  period_label: string
  net_worth: string
}

export interface ExpenseCategoryPoint {
  category: string
  amount: string
}

export interface ExpenseCategorySeriesPoint {
  period_label: string
  category: string
  amount: string
}

export interface AssetCompositionPoint {
  sub_category: string
  amount: string
}

export interface AssetSeriesPoint {
  period_label: string
  sub_category: string
  amount: string
}

export interface RetirementContributionPoint {
  account_code: number
  account_name: string
  amount: string
}

export interface RecentEntryPoint {
  description: string
  entry_date: string
  source_type: string
  period_label: string
  total_debit: string
}

export interface DashboardResponse {
  total_income: string
  total_expenses: string
  net_income: string
  total_assets: string
  total_assets_prev: string
  total_liabilities: string
  net_worth: string
  investing_cashflow: string
  salary_income: string
  retirement_contributions: string
  compensation_income: string
  lifestyle_expenses: string
  oci: string
  liquid_assets: string
  liquid_assets_prev: string
  tax_advantaged: string
  tax_advantaged_prev: string
  period_count: number
  has_data: boolean
  period_bars: PeriodBarPoint[]
  net_worth_series: NetWorthPoint[]
  top_expense_categories: ExpenseCategoryPoint[]
  expense_category_series: ExpenseCategorySeriesPoint[]
  asset_composition: AssetCompositionPoint[]
  asset_series: AssetSeriesPoint[]
  ytd_year: number | null
  ytd_retirement_contributions: RetirementContributionPoint[]
  recent_entries: RecentEntryPoint[]
  active_period: Period | null
}

// ── Period detail ──────────────────────────────────────────────────

export interface PeriodDetailResponse {
  period: Period
  transaction_count: number
  staged_count: number
  approved_count: number
  posted_count: number
  unclassified_count: number
  documents: Document[]
  accounts: Account[]
  balance_accounts: Account[]
  stated_balances: Record<number, string>
  has_pending_documents: boolean
  posted_doc_ids: string[]
  next_status: string | null
  prev_status: string | null
}

// ── Ledger ─────────────────────────────────────────────────────────

export interface LedgerResponse {
  periods: Period[]
  entries_by_period: Record<string, JournalEntryWithLines[]>
  accounts_by_code: Record<number, Account>
}

// ── Statements ─────────────────────────────────────────────────────

export interface StatementLine {
  account_code: number
  account_name: string
  sub_category: string
  amount: string
}

export interface StatementSection {
  label: string
  lines: StatementLine[]
  subtotal: string
}

export interface BalanceSheetPivotRow {
  account_code: number
  account_name: string
  sub_category: string
  balances: string[]
}

export interface BalanceSheetPivotSection {
  label: string
  rows: BalanceSheetPivotRow[]
  subtotals: string[]
}

export interface BalanceSheetPivotResponse {
  periods: Period[]
  assets: BalanceSheetPivotSection[]
  liabilities: BalanceSheetPivotSection[]
  equity: BalanceSheetPivotSection[]
  off_balance_sheet: BalanceSheetPivotSection[]
  total_assets: string[]
  total_liabilities: string[]
  total_equity: string[]
  total_off_balance_sheet: string[]
}

export interface IncomeStatementResponse {
  range_label: string
  income: StatementSection[]
  expenses: StatementSection[]
  other_comprehensive_income: StatementSection[]
  total_income: string
  total_expenses: string
  total_oci: string
  net_income: string
  comprehensive_income: string
}

export interface CashflowStatementResponse {
  range_label: string
  net_income: string
  noncash_adjustments: StatementLine[]
  working_capital_changes: StatementLine[]
  operating_total: string
  investing: StatementLine[]
  investing_total: string
  financing: StatementLine[]
  financing_total: string
  net_change_in_cash: string
  cash_by_account: StatementLine[]
  beginning_cash: string
  ending_cash: string
}

// ── Journal page ───────────────────────────────────────────────────

export interface JournalPageResponse {
  period: Period
  accounts: Account[]
  staged: RawTransaction[]
  approved: RawTransaction[]
  entries: JournalEntryWithLines[]
  has_unclassified: boolean
  documents: Document[]
  docs_missing_source: Document[]
  next_status: string | null
  prev_status: string | null
}

// ── Reconciliation ─────────────────────────────────────────────────

export interface AccountAnalysis {
  account_code: number
  likely_causes: string[]
  suggested_actions: string[]
  severity: string
}

export interface ReconciliationAnalysis {
  accounts: AccountAnalysis[]
  overall_summary: string
}

export interface ReconcilePageResponse {
  period: Period
  details: ReconciliationDetail[]
  ran: boolean
  has_gaps: boolean
  has_investment_gaps: boolean
  has_non_investment_gaps: boolean
  analysis: ReconciliationAnalysis | null
  temp_preview: TempAccountPreview
  equity_preview: EquityRollupPreview
}

// ── Request types ──────────────────────────────────────────────────

export interface AccountCreate {
  account_code: number
  account_name: string
  account_type: string
  sub_category: string
  normal_balance: string
  paystub_mapping?: string | null
  is_memo: boolean
}

export interface AccountUpdate {
  account_name?: string
  account_type?: string
  sub_category?: string
  normal_balance?: string
  paystub_mapping?: string | null
  is_memo?: boolean
  is_active?: boolean
}

export interface PeriodCreate {
  year: number
  month: number
}

export interface ManualTransactionItem {
  txn_date: string
  description: string
  amount: string
  account_code: number
}

export interface ManualTransactionBatch {
  transactions: ManualTransactionItem[]
}

export interface JournalLineCreate {
  account_code: number
  debit: string
  credit: string
  memo?: string
}

export interface ManualJournalEntryCreate {
  entry_date: string
  description: string
  source_type: string
  lines: JournalLineCreate[]
}

export interface StatedBalanceItem {
  account_code: number
  stated_balance: string
}

// ── Orchestration ──────────────────────────────────────────────────

export interface OrchestrationStepResult {
  document_id: string
  file_name: string
  resolved_type: string
  resolved_source_account_code: number | null
  resolved_account_name: string | null
  type_reason: string | null
  source_account_reason: string | null
  run_classifier: boolean
  status: 'complete' | 'failed' | 'needs_review'
  error: string | null
}

export interface OrchestrationResult {
  period_id: string
  parsed: number
  failed: number
  needs_review: number
  classifier_ran: boolean
  classifier_updated: number
  steps: OrchestrationStepResult[]
}
