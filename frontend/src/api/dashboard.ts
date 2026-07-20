import { get } from './client'
import type { DashboardResponse } from '../types'

export function fetchDashboard(periodId?: string, year?: number): Promise<DashboardResponse> {
  const params = new URLSearchParams()
  if (periodId) params.set('period_id', periodId)
  else if (year != null) params.set('year', String(year))
  const qs = params.toString()
  return get<DashboardResponse>(`/dashboard${qs ? `?${qs}` : ''}`)
}
