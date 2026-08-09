import type { MoneyFlowBucketPoint, MoneyFlowResponse } from '../../types'

/** Expense sub-categories drawn individually before the rest folds into "Other". */
const MAX_EXPENSE_NODES = 8
/**
 * Buckets thinner than this share of total income/expense fold into an "Other"
 * remainder. Low because the node cap already limits the count — the floor only
 * catches slivers that would draw a hairline ribbon and crowd a label.
 */
const MIN_SHARE = 0.02

/** Sub-categories whose full names are too long to label a node. */
const SHORT_LABELS: Record<string, string> = {
  'Retirement & Tax-Advantaged Accounts': 'Retirement',
  'Cash & Cash Equivalents': 'Cash',
  'Long-Term Debt': 'Debt Principal',
  'Restricted Cash': 'HSA',
  'Variable Compensation': 'Bonus',
  'Equity Compensation': 'Equity / RSU',
  'Employee Benefits': 'Benefits',
}

/** Fund-flow sub-categories treated as investing rather than general savings. */
const INVESTMENT_FUND_LABELS = new Set(['Investments', 'Retirement & Tax-Advantaged Accounts'])

export interface SankeyNode {
  id: string
  label: string
  value: number
  /** Layer, left to right. The income-statement flow uses 0..3; any integer is valid. */
  column: number
  color: string
  /** Source-side buckets, hatched so green↔red doesn't rely on hue alone. */
  hatched?: boolean
}

export interface SankeyLink {
  source: string
  target: string
  value: number
  color: string
}

export interface SankeyModel {
  nodes: SankeyNode[]
  links: SankeyLink[]
  total: number
}

export interface SankeyColors {
  /** Money earned (income sources, Total Income, a Net Income hub). */
  income: string
  /** Money consumed (expense sub-categories). */
  expense: string
  /** Money moved into investments. */
  fund: string
  hub: string
  /** Remainder buckets — deliberately neutral, not an identity hue. */
  other: string
  /** Reserves drawn down to cover a shortfall — a source, hatched red. */
  drawdown: string
}

/**
 * One hue per family — earn/keep, consume, build — plus red for drawdowns.
 *
 * Income sources and Total Income are green (money earned/kept), expenses are
 * purple (money spent), investments are blue (money built), remainder buckets
 * neutral, and reserves drawn down to cover a shortfall red-and-hatched. Purple
 * rather than amber for expenses because in light mode amber sits too close to
 * red, which is load-bearing here; validated with the dataviz palette checker.
 *
 * CSS custom properties rather than resolved hex, so the chart repaints on a
 * light/dark toggle without needing to re-render.
 */
export const SANKEY_COLORS: SankeyColors = {
  income: 'var(--green)',
  expense: 'var(--purple)',
  fund: 'var(--accent)',
  hub: 'var(--text-3)',
  other: 'var(--text-3)',
  drawdown: 'var(--red)',
}

const EMPTY: SankeyModel = { nodes: [], links: [], total: 0 }

interface Bucket {
  label: string
  value: number
}

function parse(section: MoneyFlowBucketPoint[]): Bucket[] {
  return section.map((b) => {
    const n = parseFloat(b.amount)
    return { label: b.category, value: Number.isFinite(n) ? n : 0 }
  })
}

const sum = (buckets: Bucket[]) => buckets.reduce((s, b) => s + b.value, 0)
const short = (label: string) => SHORT_LABELS[label] ?? label

/**
 * Drop buckets below `floor`, and past `cap`, into a single remainder.
 * Sum-preserving, so folding can never unbalance a column.
 */
function fold(buckets: Bucket[], floor: number, cap: number) {
  const kept: Bucket[] = []
  let other = 0
  for (const b of [...buckets].sort((a, b2) => b2.value - a.value)) {
    if (b.value <= 0) continue
    if (kept.length < cap && b.value >= floor) kept.push(b)
    else other += b.value
  }
  return { kept, other }
}

/**
 * Turn the backend's money flow into a four-column income-statement model:
 *
 *   col 0: income sources                → Total Income (col 1 hub)
 *   col 1: Total Income                  → expense sub-categories + Net Income/Loss (col 2)
 *   col 2: expense leaves + Net Income/Loss hub → Investments + Other (col 3)
 *   col 3: Investments, Other
 *
 * Net Income/Loss shares a column with the expense leaves (rather than sitting
 * one column further right) so every link spans only adjacent columns — a
 * link that skips a populated column draws a ribbon wide enough to visually
 * cut across that column's own nodes and labels. It's added to the node list
 * before the expense leaves so it stacks at the top of the column, keeping its
 * caption clear (the paycheck flow did the same with its Take Home hub).
 *
 * The backend guarantees sum(income) === sum(expenses) + sum(fund_flows), with
 * fund_flows signed per sub_category (positive = built, negative = drawn down;
 * see MoneyFlow in backend/app/services/dashboard.py, asserted by
 * test_money_flow_balances / test_money_flow_cash_decrease_is_negative).
 *
 * Total Income's value must stay a true income figure — never inflated by
 * drawn-down reserves — so in a loss period each expense leaf's incoming ribbon
 * splits proportionally between Total Income (funded by real income) and Net
 * Loss (funded by drawing down reserves), via coverRatio. In a surplus period
 * coverRatio is 1 and every expense leaf comes entirely from Total Income, same
 * as a normal month.
 *
 * Net Income/Loss's own value is max(P, N) — the larger of aggregate money
 * built (P) vs aggregate money drawn down (N) that period — which is what
 * actually tiles the hub exactly in every case, including a mixed-sign period
 * (e.g. contributed to Investments while Cash also drew down); abs(netIncome)
 * alone does not tile correctly there.
 */
export function buildIncomeStatementSankey(flow: MoneyFlowResponse, colors: SankeyColors): SankeyModel {
  const income = parse(flow.income).filter((b) => b.value > 0)
  const expenses = parse(flow.expenses).filter((b) => b.value > 0)
  const fundFlows = parse(flow.fund_flows) // signed — keep sign, do not filter

  const totalIncome = sum(income)
  const totalExpenses = sum(expenses)
  if (totalIncome <= 0 && totalExpenses <= 0) return EMPTY

  let investmentsTotal = 0
  let otherTotal = 0
  for (const b of fundFlows) {
    if (INVESTMENT_FUND_LABELS.has(b.label)) investmentsTotal += b.value
    else otherTotal += b.value
  }
  const built = Math.max(investmentsTotal, 0) + Math.max(otherTotal, 0)
  const drawnDown = Math.max(-investmentsTotal, 0) + Math.max(-otherTotal, 0)
  const surplus = Math.max(totalIncome - totalExpenses, 0)
  const hubValue = Math.max(built, drawnDown)
  const coverRatio = totalExpenses > 0 ? Math.min(1, totalIncome / totalExpenses) : 1

  const floor = (totalIncome || totalExpenses) * MIN_SHARE
  const foldExp = fold(expenses, floor, MAX_EXPENSE_NODES)
  const expenseLeaves = [...foldExp.kept, ...(foldExp.other > 0 ? [{ label: 'Other', value: foldExp.other }] : [])]

  const nodes: SankeyNode[] = []
  const links: SankeyLink[] = []
  const add = (n: SankeyNode) => nodes.push(n)
  const link = (source: string, target: string, value: number, color: string) =>
    value > 0 && links.push({ source, target, value, color })

  if (totalIncome > 0) {
    add({ id: 'totalincome', label: 'Total Income', value: totalIncome, column: 1, color: colors.hub })
  }

  // Col 0 — every income source pools into Total Income.
  for (const b of income) {
    const id = `income:${b.label}`
    add({ id, label: short(b.label), value: b.value, column: 0, color: colors.income })
    link(id, 'totalincome', b.value, colors.income)
  }

  // Col 2 — Net Income/Loss hub, added before the expense leaves it shares a
  // column with so it stacks topmost and its caption has clear space above.
  if (hubValue > 0) {
    add({
      id: 'netincomeloss',
      label: totalIncome >= totalExpenses ? 'Net Income' : 'Net Loss',
      value: hubValue,
      column: 2,
      color: totalIncome >= totalExpenses ? colors.income : colors.drawdown,
    })
    link('totalincome', 'netincomeloss', surplus, colors.income)
  }

  // Col 2 — expense sub-categories branch off Total Income (and, in a loss
  // period, partly off Net Loss — see coverRatio above).
  for (const e of expenseLeaves) {
    const id = `expense:${e.label}`
    const c = e.label === 'Other' ? colors.other : colors.expense
    add({ id, label: short(e.label), value: e.value, column: 2, color: c })
    link('totalincome', id, e.value * coverRatio, c)
    if (coverRatio < 1) link('netincomeloss', id, e.value * (1 - coverRatio), colors.drawdown)
  }

  // Col 3 — Investments / Other, each a sink when built up this period, or a
  // hatched red source when drawn down to cover a shortfall.
  const fundLeaf = (id: string, label: string, value: number) => {
    if (value > 0) {
      const c = label === 'Investments' ? colors.fund : colors.other
      add({ id, label, value, column: 3, color: c })
      link('netincomeloss', id, value, c)
    } else if (value < 0) {
      add({ id, label, value: -value, column: 3, color: colors.drawdown, hatched: true })
      link(id, 'netincomeloss', -value, colors.drawdown)
    }
  }
  fundLeaf('fund:Investments', 'Investments', investmentsTotal)
  fundLeaf('fund:Other', 'Other', otherTotal)

  return { nodes, links, total: Math.max(totalIncome, totalExpenses) }
}
