import { describe, it, expect } from 'vitest'
import { nextAccountCode } from '../accountCode'

// Mirror of the real chart's codes (a representative slice).
const CODES = [
  100101, 120101, // Asset
  112102, // Memo Asset* (inside the asset band)
  200101, 210102, // Liability
  300101, 300103, // Equity
  400101, 400104, 410103, // Income
  510101, 580104, 999999, // Expense (+ out-of-band Suspense)
]

describe('nextAccountCode', () => {
  it('returns highest-in-band + 1 for Income', () => {
    expect(nextAccountCode(CODES, 'Income')).toBe(410104)
  })

  it('ignores the out-of-band 999999 outlier for Expense', () => {
    expect(nextAccountCode(CODES, 'Expense')).toBe(580105)
  })

  it('treats Memo Asset* as sharing the Asset band', () => {
    expect(nextAccountCode(CODES, 'Memo Asset*')).toBe(120102)
    expect(nextAccountCode(CODES, 'Asset')).toBe(120102)
  })

  it('falls back to the band start when the band is empty', () => {
    expect(nextAccountCode([100101], 'Income')).toBe(400101)
    expect(nextAccountCode([], 'Asset')).toBe(100101)
  })

  it('returns null for an unknown type', () => {
    expect(nextAccountCode(CODES, 'Bogus')).toBeNull()
  })

  it('returns null when the band is full', () => {
    expect(nextAccountCode([199999], 'Asset')).toBeNull()
  })
})
