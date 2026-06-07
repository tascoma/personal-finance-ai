import type { DashboardResponse } from '../../types'

// Year the forecast projects toward and that retirement contribution limits apply to.
export const TARGET_YEAR = new Date().getFullYear()

export interface DashboardTabProps {
  data: DashboardResponse
  scopeLabel: string
}
