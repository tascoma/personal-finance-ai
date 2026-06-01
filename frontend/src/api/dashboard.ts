import { get } from './client'
import type { DashboardResponse } from '../types'

export function fetchDashboard(year?: number): Promise<DashboardResponse> {
  const params = new URLSearchParams()
  if (year != null) params.set('year', String(year))
  const qs = params.toString()
  return get<DashboardResponse>(`/dashboard${qs ? `?${qs}` : ''}`)
}
