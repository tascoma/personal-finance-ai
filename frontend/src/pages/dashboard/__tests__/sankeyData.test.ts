import { describe, it, expect } from 'vitest'
import { buildIncomeStatementSankey, type SankeyColors, type SankeyModel } from '../sankeyData'
import type { MoneyFlowResponse } from '../../../types'

const COLORS: SankeyColors = {
  income: 'inc',
  expense: 'exp',
  fund: 'fund',
  hub: 'hub',
  other: 'other',
  drawdown: 'draw',
}

type Pairs = Array<[string, number]>

interface Seed {
  income?: Pairs
  expenses?: Pairs
  fund_flows?: Pairs
}

function mk(seed: Seed): MoneyFlowResponse {
  const section = (pairs: Pairs = []) =>
    pairs.map(([category, amount]) => ({ category, amount: String(amount) }))
  return {
    income: section(seed.income),
    expenses: section(seed.expenses),
    fund_flows: section(seed.fund_flows),
  }
}

const byId = (m: SankeyModel, id: string) => m.nodes.find((n) => n.id === id)
const nodeVal = (m: SankeyModel, id: string) => byId(m, id)?.value
const inflow = (m: SankeyModel, id: string) =>
  m.links.filter((l) => l.target === id).reduce((s, l) => s + l.value, 0)
const outflow = (m: SankeyModel, id: string) =>
  m.links.filter((l) => l.source === id).reduce((s, l) => s + l.value, 0)

// A surplus month: 9800 of income across three sources, 6600 of expenses
// across two sub-categories, and the 3200 left over split between building
// Investments (2700) and Retirement (300, folded into the same node), plus a
// 200 Cash build (folded into "Other").
const SURPLUS = mk({
  income: [['Earned Income', 9000], ['Variable Compensation', 500], ['Investment Income', 300]],
  expenses: [['Housing', 4000], ['Food', 2600]],
  fund_flows: [
    ['Investments', 2700],
    ['Retirement & Tax-Advantaged Accounts', 300],
    ['Cash & Cash Equivalents', 200],
  ],
})

describe('buildIncomeStatementSankey', () => {
  it('pools every income source into Total Income', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)

    expect(nodeVal(m, 'totalincome')).toBe(9800)
    expect(inflow(m, 'totalincome')).toBeCloseTo(9800, 6)
    expect(outflow(m, 'totalincome')).toBeCloseTo(9800, 6)
    expect(m.links).toContainEqual({ source: 'income:Earned Income', target: 'totalincome', value: 9000, color: 'inc' })
  })

  it('branches expense sub-categories off Total Income at their true value', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)

    expect(nodeVal(m, 'expense:Housing')).toBe(4000)
    expect(nodeVal(m, 'expense:Food')).toBe(2600)
    expect(m.links).toContainEqual({ source: 'totalincome', target: 'expense:Housing', value: 4000, color: 'exp' })
    // Fully funded from current income in a surplus month — no drawdown link.
    expect(m.links.some((l) => l.target === 'expense:Housing' && l.source === 'netincomeloss')).toBe(false)
  })

  it('labels the remainder Net Income, tiled by what actually moved', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)

    expect(byId(m, 'netincomeloss')!.label).toBe('Net Income')
    expect(byId(m, 'netincomeloss')!.color).toBe('inc')
    // 9800 income - 6600 expenses = 3200, which is exactly what built up.
    expect(nodeVal(m, 'netincomeloss')).toBe(3200)
    expect(inflow(m, 'netincomeloss')).toBeCloseTo(3200, 6)
    expect(outflow(m, 'netincomeloss')).toBeCloseTo(3200, 6)
  })

  it('combines Investments and Retirement into one Investments node, folds the rest into Other', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)

    expect(nodeVal(m, 'fund:Investments')).toBe(3000) // 2700 + 300
    expect(byId(m, 'fund:Investments')!.color).toBe('fund')
    expect(nodeVal(m, 'fund:Other')).toBe(200) // Cash & Cash Equivalents
    expect(byId(m, 'fund:Other')!.color).toBe('other')
    expect(m.links).toContainEqual({ source: 'netincomeloss', target: 'fund:Investments', value: 3000, color: 'fund' })
    expect(m.links).toContainEqual({ source: 'netincomeloss', target: 'fund:Other', value: 200, color: 'other' })
  })

  it('never leaves a hub untiled by its links', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)
    for (const hub of ['totalincome', 'netincomeloss']) {
      expect(inflow(m, hub)).toBeCloseTo(nodeVal(m, hub)!, 6)
      expect(outflow(m, hub)).toBeCloseTo(nodeVal(m, hub)!, 6)
    }
  })

  it('emits only positive-valued nodes', () => {
    const m = buildIncomeStatementSankey(SURPLUS, COLORS)
    expect(m.nodes.every((n) => n.value > 0)).toBe(true)
  })

  describe('a net-loss month funded by drawing down reserves', () => {
    // 5000 income, 7000 of expenses — a 2000 shortfall covered entirely by
    // drawing down Cash (an "Other" fund destination).
    const LOSS = mk({
      income: [['Earned Income', 5000]],
      expenses: [['Housing', 4000], ['Food', 3000]],
      fund_flows: [['Cash & Cash Equivalents', -2000]],
    })

    it('labels the hub Net Loss, coloured as a drawdown', () => {
      const m = buildIncomeStatementSankey(LOSS, COLORS)
      expect(byId(m, 'netincomeloss')!.label).toBe('Net Loss')
      expect(byId(m, 'netincomeloss')!.color).toBe('draw')
      expect(nodeVal(m, 'netincomeloss')).toBe(2000)
    })

    it('renders the drawn-down fund node as a hatched red source, reversed', () => {
      const m = buildIncomeStatementSankey(LOSS, COLORS)
      const other = byId(m, 'fund:Other')!
      expect(other.value).toBe(2000)
      expect(other.hatched).toBe(true)
      expect(other.color).toBe('draw')
      expect(m.links).toContainEqual({ source: 'fund:Other', target: 'netincomeloss', value: 2000, color: 'draw' })
    })

    it('splits each expense leaf proportionally between current income and the drawdown', () => {
      const m = buildIncomeStatementSankey(LOSS, COLORS)
      // coverRatio = 5000 / 7000
      const housingFromIncome = m.links.find((l) => l.source === 'totalincome' && l.target === 'expense:Housing')!
      const housingFromDrawdown = m.links.find((l) => l.source === 'netincomeloss' && l.target === 'expense:Housing')!
      expect(housingFromIncome.value + housingFromDrawdown.value).toBeCloseTo(4000, 6)
      expect(housingFromIncome.value).toBeCloseTo(4000 * (5000 / 7000), 6)
    })

    it('never leaves a hub untiled by its links', () => {
      const m = buildIncomeStatementSankey(LOSS, COLORS)
      for (const hub of ['totalincome', 'netincomeloss']) {
        expect(inflow(m, hub)).toBeCloseTo(nodeVal(m, hub)!, 6)
        expect(outflow(m, hub)).toBeCloseTo(nodeVal(m, hub)!, 6)
      }
    })
  })

  it('tiles a mixed-sign period (built Investments while also drawing down Cash) using gross movement', () => {
    // Surplus of 2500 overall, but 3000 went into Investments while 500 was
    // drawn from Cash in the same period — the hub must show 3000, not 2500,
    // to tile exactly against both fund nodes.
    const m = buildIncomeStatementSankey(
      mk({
        income: [['Earned Income', 10000]],
        expenses: [['Housing', 7500]],
        fund_flows: [['Investments', 3000], ['Cash & Cash Equivalents', -500]],
      }),
      COLORS,
    )

    expect(nodeVal(m, 'netincomeloss')).toBe(3000)
    expect(byId(m, 'netincomeloss')!.label).toBe('Net Income') // still a surplus overall
    expect(nodeVal(m, 'fund:Investments')).toBe(3000)
    const other = byId(m, 'fund:Other')!
    expect(other.value).toBe(500)
    expect(other.hatched).toBe(true)
    expect(inflow(m, 'netincomeloss')).toBeCloseTo(3000, 6)
    expect(outflow(m, 'netincomeloss')).toBeCloseTo(3000, 6)
  })

  it('folds sub-floor expense sub-categories into a remainder without losing value', () => {
    const m = buildIncomeStatementSankey(
      mk({
        income: [['Earned Income', 10000]],
        expenses: [
          ['Housing', 3000], ['Food', 1500], ['Transportation', 1200], ['Utilities', 900],
          ['Communications', 700], ['Subscriptions', 600], ['Lifestyle', 500], ['Personal', 400],
          ['Giving', 300], ['Payroll Taxes', 250], ['Employee Benefits', 200], ['Suspense', 50],
        ],
        fund_flows: [],
      }),
      COLORS,
    )

    const expenseLeaves = m.nodes.filter((n) => n.id.startsWith('expense:'))
    expect(expenseLeaves.length).toBeLessThanOrEqual(9) // MAX_EXPENSE_NODES (8) + Other
    expect(byId(m, 'expense:Other')).toBeDefined()
    expect(outflow(m, 'totalincome')).toBeCloseTo(9600, 6) // sum of all expenses, nothing lost
  })

  it('emits no Net Income/Loss node at breakeven', () => {
    const m = buildIncomeStatementSankey(
      mk({ income: [['Earned Income', 5000]], expenses: [['Housing', 5000]], fund_flows: [] }),
      COLORS,
    )
    expect(byId(m, 'netincomeloss')).toBeUndefined()
    expect(m.links.some((l) => l.source === 'netincomeloss' || l.target === 'netincomeloss')).toBe(false)
  })

  it('returns an empty model when there is no activity', () => {
    expect(buildIncomeStatementSankey(mk({}), COLORS)).toEqual({ nodes: [], links: [], total: 0 })
  })

  it('reports a total even in an all-drawdown period with zero real income', () => {
    const m = buildIncomeStatementSankey(
      mk({ income: [], expenses: [['Housing', 1000]], fund_flows: [['Cash & Cash Equivalents', -1000]] }),
      COLORS,
    )
    expect(byId(m, 'totalincome')).toBeUndefined()
    expect(m.total).toBe(1000)
  })

  it('ignores unparseable amounts', () => {
    const m = buildIncomeStatementSankey(
      {
        income: [{ category: 'Earned Income', amount: '5000' }, { category: 'Bad', amount: 'x' }],
        expenses: [],
        fund_flows: [],
      },
      COLORS,
    )

    expect(byId(m, 'income:Bad')).toBeUndefined()
    expect(nodeVal(m, 'totalincome')).toBe(5000)
  })
})
