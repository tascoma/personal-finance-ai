import { get } from './client'
import type {
  BalanceSheetPivotResponse,
  IncomeStatementResponse,
  CashflowStatementResponse,
} from '../types'

export function fetchBalanceSheet(): Promise<BalanceSheetPivotResponse> {
  return get<BalanceSheetPivotResponse>('/statements/balance-sheet')
}

export function fetchIncomeStatement(periodId?: string, year?: number): Promise<IncomeStatementResponse> {
  const qs = periodId ? `?period_id=${periodId}` : year != null ? `?year=${year}` : ''
  return get<IncomeStatementResponse>(`/statements/income${qs}`)
}

export function fetchCashflow(periodId?: string, year?: number): Promise<CashflowStatementResponse> {
  const qs = periodId ? `?period_id=${periodId}` : year != null ? `?year=${year}` : ''
  return get<CashflowStatementResponse>(`/statements/cashflow${qs}`)
}
