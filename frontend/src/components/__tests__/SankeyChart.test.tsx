import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import SankeyChart from '../SankeyChart'
import { buildIncomeStatementSankey, type SankeyColors } from '../../pages/dashboard/sankeyData'
import type { MoneyFlowResponse } from '../../types'

const COLORS: SankeyColors = {
  income: '#0a0',
  expense: '#a0a',
  fund: '#00a',
  hub: '#hub',
  other: '#other',
  drawdown: 'var(--red)',
}

type Pairs = Array<[string, number]>

interface Seed {
  income?: Pairs
  expenses?: Pairs
  fund_flows?: Pairs
}

function model(seed: Seed) {
  const section = (pairs: Pairs = []) =>
    pairs.map(([category, amount]) => ({ category, amount: String(amount) }))
  const flow: MoneyFlowResponse = {
    income: section(seed.income),
    expenses: section(seed.expenses),
    fund_flows: section(seed.fund_flows),
  }
  return buildIncomeStatementSankey(flow, COLORS)
}

// 8300 of income, 4300 of expenses, and the 4000 left over split between
// Investments (2700 direct + 800 retirement = 3500) and a 500 Cash build.
const REALISTIC = model({
  income: [['Earned Income', 6000], ['Variable Compensation', 2000], ['Investment Income', 300]],
  expenses: [['Housing', 2000], ['Food', 1500], ['Transportation', 800]],
  fund_flows: [
    ['Investments', 2700],
    ['Retirement & Tax-Advantaged Accounts', 800],
    ['Cash & Cash Equivalents', 500],
  ],
})

const HEIGHT = 480

const rectBounds = (container: HTMLElement) =>
  [...container.querySelectorAll('rect[data-node]')].map((r) => ({
    y: parseFloat(r.getAttribute('y')!),
    h: parseFloat(r.getAttribute('height')!),
  }))

describe('SankeyChart', () => {
  it('draws one rect per node and one path per link', () => {
    const { container } = render(<SankeyChart model={REALISTIC} height={HEIGHT} />)

    expect(container.querySelectorAll('rect[data-node]')).toHaveLength(REALISTIC.nodes.length)
    expect(container.querySelectorAll('path')).toHaveLength(REALISTIC.links.length)
  })

  it('keeps every node inside the viewBox', () => {
    const { container } = render(<SankeyChart model={REALISTIC} height={HEIGHT} />)

    for (const { y, h } of rectBounds(container)) {
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y + h).toBeLessThanOrEqual(HEIGHT)
    }
  })

  it('keeps a crowded expense column inside the viewBox', () => {
    const crowded = model({
      income: [['Earned Income', 20000]],
      expenses: [
        ['Housing', 3000], ['Food', 2500], ['Lifestyle', 2000], ['Transportation', 1800],
        ['Utilities', 1200], ['Subscriptions', 900], ['Personal', 700],
      ],
      fund_flows: [['Investments', 2500], ['Cash & Cash Equivalents', 5400]],
    })
    const { container } = render(<SankeyChart model={crowded} height={HEIGHT} />)

    expect(crowded.nodes.filter((n) => n.column === 2).length).toBeGreaterThanOrEqual(6)
    for (const { y, h } of rectBounds(container)) {
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y + h).toBeLessThanOrEqual(HEIGHT)
    }
  })

  it('tiles the hubs exactly with the ribbons on each side', () => {
    const { container } = render(<SankeyChart model={REALISTIC} height={HEIGHT} />)
    const heights = new Map(
      [...container.querySelectorAll('rect[data-node]')].map((r) => [
        r.getAttribute('data-node')!,
        parseFloat(r.getAttribute('height')!),
      ]),
    )
    const heightOf = (id: string) => heights.get(id)!

    // Total Income is fed by every col-0 income source...
    const sourcesH =
      heightOf('income:Earned Income') + heightOf('income:Variable Compensation') +
      heightOf('income:Investment Income')
    expect(sourcesH).toBeCloseTo(heightOf('totalincome'), 6)
    // ...and Net Income pays out exactly into Investments + Other.
    const fundH = heightOf('fund:Investments') + heightOf('fund:Other')
    expect(fundH).toBeCloseTo(heightOf('netincomeloss'), 6)
  })

  it('captions the spine hubs and labels the outer nodes', () => {
    const { container } = render(<SankeyChart model={REALISTIC} height={HEIGHT} />)
    const text = container.textContent ?? ''

    expect(text).toContain('Earned Income')  // an income source (left)
    expect(text).toContain('Housing')        // an expense (middle)
    expect(text).toContain('TOTAL INCOME')   // hub captions
    expect(text).toContain('NET INCOME')
    expect(text).not.toContain('TAKE HOME')
    expect(text).not.toContain('PAYSTUB')
    expect(text).not.toContain('SPENDABLE')
    expect(text).toContain('$8,300.00')      // total income value in its caption
    expect(text).toContain('$4,000.00')      // net income hub (8300 - 4300)
  })

  it('renders a reserve drawdown in red and hatched on the source side', () => {
    const withDraw = model({
      income: [['Earned Income', 3000]],
      expenses: [['Housing', 5000]],
      fund_flows: [['Cash & Cash Equivalents', -2000]],
    })
    const { container } = render(<SankeyChart model={withDraw} height={HEIGHT} />)

    expect(container.querySelector('rect[fill="var(--red)"]')).not.toBeNull()
    expect(container.querySelector('rect[fill="url(#sankey-hatch)"]')).not.toBeNull()
  })

  it('renders a backward link (source column right of target column) without throwing', () => {
    // A net-loss period: fund:Other (column 4) feeds netincomeloss (column 3)
    // backward, and part of each expense leaf (column 2) is funded by
    // netincomeloss (column 3) rather than totalincome (column 1) — both are
    // links whose source column is >= its target column.
    const loss = model({
      income: [['Earned Income', 3000]],
      expenses: [['Housing', 5000]],
      fund_flows: [['Cash & Cash Equivalents', -2000]],
    })
    const backward = loss.links.filter((l) => {
      const src = loss.nodes.find((n) => n.id === l.source)!
      const tgt = loss.nodes.find((n) => n.id === l.target)!
      return src.column >= tgt.column
    })
    expect(backward.length).toBeGreaterThan(0)

    const { container } = render(<SankeyChart model={loss} height={HEIGHT} />)
    const paths = [...container.querySelectorAll('path')]
    expect(paths).toHaveLength(loss.links.length)
    for (const p of paths) {
      expect(p.getAttribute('d')).not.toContain('NaN')
    }
  })

  it('gives every node and flow a titled tooltip', () => {
    const { container } = render(<SankeyChart model={REALISTIC} height={HEIGHT} />)
    const titles = [...container.querySelectorAll('title')]

    expect(titles).toHaveLength(REALISTIC.nodes.length + REALISTIC.links.length)
    expect(titles.every((t) => t.textContent?.includes('$'))).toBe(true)
  })

  it('renders nothing for an empty model', () => {
    const { container } = render(<SankeyChart model={{ nodes: [], links: [], total: 0 }} />)

    expect(container.querySelector('svg')).toBeNull()
  })
})
