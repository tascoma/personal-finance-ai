/** Numeric band [lo, hi) each account type's codes live in (6-digit, by leading digit). */
export const ACCOUNT_BANDS: Record<string, [number, number]> = {
  Asset: [100000, 200000],
  'Memo Asset*': [100000, 200000], // memo assets share the asset band
  Liability: [200000, 300000],
  Equity: [300000, 400000],
  Income: [400000, 500000],
  Expense: [500000, 600000],
}

/**
 * Suggest the next available account code for a type: the highest existing code
 * within the type's band, plus one. Band-bounding ignores out-of-band outliers
 * (e.g. the Suspense expense at 999999). Returns the band start (lo + 101, matching
 * the chart's xx0101 convention) when the band has no codes yet, or null when the
 * band is full or the type is unknown.
 */
export function nextAccountCode(allCodes: number[], type: string): number | null {
  const band = ACCOUNT_BANDS[type]
  if (!band) return null
  const [lo, hi] = band
  const inBand = allCodes.filter((c) => c >= lo && c < hi)
  if (inBand.length === 0) return lo + 101
  const next = Math.max(...inBand) + 1
  return next < hi ? next : null
}
