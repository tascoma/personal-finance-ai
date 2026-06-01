import { Fragment, useEffect, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { fetchBalanceSheet, fetchIncomeStatement, fetchCashflow } from '../api/statements'
import { fetchPeriods } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import type { CashflowStatementResponse, IncomeStatementResponse } from '../types'

type IncomeSectionKey = 'income' | 'expenses' | 'other_comprehensive_income'
type IncPivotRow = { account_code: number; account_name: string; amounts: string[] }
type IncPivotSection = { label: string; rows: IncPivotRow[]; subtotals: string[] }

function pivotIncomeSection(responses: (IncomeStatementResponse | undefined)[], key: IncomeSectionKey): IncPivotSection[] {
  const labelsSeen = new Set<string>()
  const labels: string[] = []
  for (const r of responses) {
    if (!r) continue
    for (const sec of r[key]) {
      if (!labelsSeen.has(sec.label)) { labelsSeen.add(sec.label); labels.push(sec.label) }
    }
  }
  return labels.map((label) => {
    const sectionsPerPeriod = responses.map((r) => r?.[key].find((s) => s.label === label))
    const accounts = new Map<number, string>()
    for (const sec of sectionsPerPeriod) {
      if (!sec) continue
      for (const ln of sec.lines) { if (!accounts.has(ln.account_code)) accounts.set(ln.account_code, ln.account_name) }
    }
    const rows: IncPivotRow[] = Array.from(accounts.entries()).sort((a, b) => a[0] - b[0])
      .map(([code, name]) => ({ account_code: code, account_name: name, amounts: sectionsPerPeriod.map((sec) => sec?.lines.find((l) => l.account_code === code)?.amount ?? '0') }))
    const subtotals = sectionsPerPeriod.map((sec) => sec?.subtotal ?? '0')
    return { label, rows, subtotals }
  })
}

type CashflowLinesKey = 'noncash_adjustments' | 'working_capital_changes' | 'investing' | 'financing' | 'cash_by_account'
type SubCategoryRow = { sub_category: string; amounts: string[] }

function pivotCashflowLines(responses: (CashflowStatementResponse | undefined)[], key: CashflowLinesKey): IncPivotRow[] {
  const accounts = new Map<number, string>()
  for (const r of responses) { if (!r) continue; for (const ln of r[key]) { if (!accounts.has(ln.account_code)) accounts.set(ln.account_code, ln.account_name) } }
  return Array.from(accounts.entries()).sort((a, b) => a[0] - b[0])
    .map(([code, name]) => ({ account_code: code, account_name: name, amounts: responses.map((r) => r?.[key].find((l) => l.account_code === code)?.amount ?? '0') }))
}

function pivotCashflowBySubCategory(responses: (CashflowStatementResponse | undefined)[], key: CashflowLinesKey): SubCategoryRow[] {
  const order: string[] = []
  const sums = new Map<string, number[]>()
  for (let i = 0; i < responses.length; i++) {
    const r = responses[i]
    if (!r) continue
    for (const ln of r[key]) {
      let bucket = sums.get(ln.sub_category)
      if (!bucket) { bucket = new Array(responses.length).fill(0); sums.set(ln.sub_category, bucket); order.push(ln.sub_category) }
      bucket[i] = (bucket[i] ?? 0) + parseFloat(ln.amount)
    }
  }
  return order.map((sub_category) => ({ sub_category, amounts: (sums.get(sub_category) ?? []).map((v) => v.toFixed(2)) }))
}

type Tab = 'balance_sheet' | 'income_statement' | 'cashflows'

function Money({ val }: { val: string }) {
  const n = parseFloat(val)
  const fmt = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (n < 0) return <span className="color-red">${fmt(Math.abs(n))}</span>
  return <span>${fmt(n)}</span>
}

export default function StatementsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('balance_sheet')
  const [bsAnchorId, setBsAnchorId] = useState<string>('')
  const [bsView, setBsView] = useState<'detailed' | 'condensed'>('detailed')
  const [incMode, setIncMode] = useState<'rolling' | 'aggregate'>('rolling')
  const [incAnchorId, setIncAnchorId] = useState<string>('')
  const [cfAnchorId, setCfAnchorId] = useState<string>('')
  const [printMode, setPrintMode] = useState(false)

  const periodsQ = useQuery({ queryKey: ['periods'], queryFn: fetchPeriods, staleTime: 30_000 })
  const closedPeriods = periodsQ.data?.filter((p) => p.status === 'closed') ?? []
  const bsQ = useQuery({ queryKey: ['balance-sheet'], queryFn: fetchBalanceSheet, staleTime: 30_000 })

  const incFetchIds: (string | undefined)[] = (() => {
    if (incMode === 'aggregate') return [undefined]
    if (!closedPeriods.length) return []
    const anchorIdx = incAnchorId ? Math.max(0, closedPeriods.findIndex((p) => p.period_id === incAnchorId)) : 0
    return [anchorIdx + 2, anchorIdx + 1, anchorIdx].filter((i) => i >= 0 && i < closedPeriods.length).map((i) => closedPeriods[i].period_id)
  })()

  const incQs = useQueries({
    queries: incFetchIds.map((pid) => ({ queryKey: ['income-statement', pid ?? 'aggregate'], queryFn: () => fetchIncomeStatement(pid), staleTime: 30_000 })),
  })

  const cfFetchIds: string[] = (() => {
    if (!closedPeriods.length) return []
    const anchorIdx = cfAnchorId ? Math.max(0, closedPeriods.findIndex((p) => p.period_id === cfAnchorId)) : 0
    return [anchorIdx + 2, anchorIdx + 1, anchorIdx].filter((i) => i >= 0 && i < closedPeriods.length).map((i) => closedPeriods[i].period_id)
  })()

  const cfQs = useQueries({
    queries: cfFetchIds.map((pid) => ({ queryKey: ['cashflow', pid], queryFn: () => fetchCashflow(pid), staleTime: 30_000 })),
  })

  const bs = bsQ.data
  const incResponses = incQs.map((q) => q.data)
  const incLoading = incQs.some((q) => q.isLoading)
  const incError = incQs.some((q) => q.error)
  const incPeriods = incMode === 'rolling' ? incFetchIds.map((pid) => closedPeriods.find((p) => p.period_id === pid)).filter((p): p is NonNullable<typeof p> => !!p) : []
  const incColCount = incMode === 'rolling' ? incPeriods.length : 1
  const incReady = incResponses.every((r) => !!r) && incResponses.length > 0
  const cfResponses = cfQs.map((q) => q.data)
  const cfLoading = cfQs.some((q) => q.isLoading)
  const cfError = cfQs.some((q) => q.error)
  const cfPeriods = cfFetchIds.map((pid) => closedPeriods.find((p) => p.period_id === pid)).filter((p): p is NonNullable<typeof p> => !!p)
  const cfReady = cfResponses.every((r) => !!r) && cfResponses.length > 0

  const bsAnchorIdx = (() => {
    if (!bs || !bs.periods.length) return -1
    if (!bsAnchorId) return bs.periods.length - 1
    const idx = bs.periods.findIndex((p) => p.period_id === bsAnchorId)
    return idx === -1 ? bs.periods.length - 1 : idx
  })()
  const bsStart = Math.max(0, bsAnchorIdx - 2)
  const bsEnd = bsAnchorIdx + 1
  const slice = <T,>(arr: T[]): T[] => arr.slice(bsStart, bsEnd)

  const bsSettled = !bsQ.isLoading
  const incSettled = incQs.every((q) => !q.isLoading)
  const cfSettled = cfQs.every((q) => !q.isLoading)
  const allSettled = bsSettled && incSettled && cfSettled

  useEffect(() => {
    const onAfter = () => setPrintMode(false)
    window.addEventListener('afterprint', onAfter)
    return () => window.removeEventListener('afterprint', onAfter)
  }, [])

  useEffect(() => {
    if (!printMode) return
    const fire = () => window.print()
    if (allSettled) { const t = setTimeout(fire, 100); return () => clearTimeout(t) }
    const fallback = setTimeout(() => setPrintMode(false), 5000)
    return () => clearTimeout(fallback)
  }, [printMode, allSettled])

  const tabs = [
    { id: 'balance_sheet' as Tab, label: 'Balance Sheet' },
    { id: 'income_statement' as Tab, label: 'Income Statement' },
    { id: 'cashflows' as Tab, label: 'Cash Flows' },
  ]

  return (
    <Layout>
      <div className="page">
        <PageHeader
          eyebrow="Financial Statements"
          title="Statements"
          subtitle={`Balance sheet, income, and cash flow — derived from posted journal entries`}
          actions={
            <>
              <select className="inp" value={closedPeriods[0]?.period_id ?? ''} onChange={() => {}}>
                {closedPeriods.slice().reverse().map((p) => (
                  <option key={p.period_id} value={p.period_id}>{p.period_start.slice(0, 7)}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => closedPeriods.length && setPrintMode(true)}
                disabled={printMode || !closedPeriods.length}
              >
                <SvgIcon name="download" size={13} />
                {printMode ? 'Preparing…' : 'Export PDF'}
              </button>
            </>
          }
        />

        <div className="tabs print-hide">
          {tabs.map((t) => (
            <button key={t.id} className={`tab${activeTab === t.id ? ' active' : ''}`} onClick={() => setActiveTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Balance Sheet */}
        {(activeTab === 'balance_sheet' || printMode) && (
          <div className="card mb-4">
            <div className="card-hd">
              <div>
                <div className="card-title">Balance Sheet</div>
                <div className="card-sub">Rolling 3 periods · cumulative balances</div>
              </div>
              <div className="row gap-3 print-hide">
                <div className="seg">
                  <button className={bsView === 'detailed' ? 'active' : ''} onClick={() => setBsView('detailed')}>Detailed</button>
                  <button className={bsView === 'condensed' ? 'active' : ''} onClick={() => setBsView('condensed')}>Summary</button>
                </div>
                {bs && bs.periods.length > 0 && (
                  <>
                    <span className="muted-2" style={{ fontSize: 13 }}>Ending period:</span>
                    <select
                      className="inp"
                      style={{ width: 140 }}
                      value={bsAnchorId || bs.periods[bs.periods.length - 1].period_id}
                      onChange={(e) => setBsAnchorId(e.target.value)}
                    >
                      {[...bs.periods].reverse().map((p) => (
                        <option key={p.period_id} value={p.period_id}>{p.period_start.slice(0, 7)}</option>
                      ))}
                    </select>
                  </>
                )}
              </div>
            </div>
            <div className="card-bd">
              {bsQ.isLoading && <p className="muted">Loading…</p>}
              {bsQ.error && <p className="color-red">Failed to load balance sheet.</p>}
              {bs && !bs.periods.length && <EmptyState message="No periods found." />}
              {bs && bs.periods.length > 0 && bsView === 'condensed' && (() => {
                const periodLabel = bs.periods[bsAnchorIdx]?.period_start.slice(0, 7) ?? ''
                const idx = bsAnchorIdx
                return (
                  <div>
                    <div className="muted text-center" style={{ fontSize: 12, marginBottom: 14, letterSpacing: '0.04em' }}>{periodLabel}</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', border: '1px solid var(--line)', borderRadius: 'var(--r)', overflow: 'hidden' }}>
                      {/* Left: Assets */}
                      <div style={{ borderRight: '1px solid var(--line)', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ padding: '10px 18px', borderBottom: '1px solid var(--line)', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.08em', color: 'var(--text-3)', background: 'var(--bg-3)' }}>Assets</div>
                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-evenly' }}>
                          {bs.assets.map((sec) => (
                            <div key={sec.label} className="stmt-row indent">
                              <span className="stmt-label">{sec.label}</span>
                              <span className="stmt-amount"><Money val={sec.subtotals[idx] ?? '0'} /></span>
                            </div>
                          ))}
                        </div>
                        <div className="stmt-row total" style={{ marginTop: 0 }}>
                          <span className="stmt-label">Total Assets</span>
                          <span className="stmt-amount"><Money val={bs.total_assets[idx] ?? '0'} /></span>
                        </div>
                      </div>
                      {/* Right: Liabilities + Equity */}
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <div style={{ padding: '10px 18px', borderBottom: '1px solid var(--line)', fontSize: 11, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.08em', color: 'var(--text-3)', background: 'var(--bg-3)' }}>Liabilities &amp; Equity</div>
                        {bs.liabilities.length > 0 && (
                          <div style={{ padding: '8px 18px 2px', fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.06em', color: 'var(--text-3)' }}>Liabilities</div>
                        )}
                        {bs.liabilities.map((sec) => (
                          <div key={sec.label} className="stmt-row indent">
                            <span className="stmt-label">{sec.label}</span>
                            <span className="stmt-amount"><Money val={sec.subtotals[idx] ?? '0'} /></span>
                          </div>
                        ))}
                        {bs.liabilities.length > 0 && (
                          <div className="stmt-row">
                            <span className="stmt-label" style={{ fontStyle: 'italic', fontSize: 12.5, color: 'var(--text-2)' }}>Total Liabilities</span>
                            <span className="stmt-amount"><Money val={bs.total_liabilities[idx] ?? '0'} /></span>
                          </div>
                        )}
                        {bs.equity.length > 0 && (
                          <div style={{ padding: '8px 18px 2px', fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.06em', color: 'var(--text-3)', marginTop: bs.liabilities.length > 0 ? 4 : 0 }}>Equity</div>
                        )}
                        {bs.equity.map((sec) => (
                          <div key={sec.label} className="stmt-row indent">
                            <span className="stmt-label">{sec.label}</span>
                            <span className="stmt-amount"><Money val={sec.subtotals[idx] ?? '0'} /></span>
                          </div>
                        ))}
                        <div className="stmt-row total" style={{ marginTop: 'auto' }}>
                          <span className="stmt-label">Total Liabilities + Equity</span>
                          <span className="stmt-amount"><Money val={(parseFloat(bs.total_liabilities[idx] ?? '0') + parseFloat(bs.total_equity[idx] ?? '0')).toFixed(2)} /></span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })()}
              {bs && bs.periods.length > 0 && bsView === 'detailed' && (() => {
                const visiblePeriods = slice(bs.periods)
                const visibleTotalAssets = slice(bs.total_assets)
                const visibleTotalLiab = slice(bs.total_liabilities)
                const visibleTotalEquity = slice(bs.total_equity)
                const visibleTotalOff = slice(bs.total_off_balance_sheet)
                const colCount = visiblePeriods.length + 1
                return (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th style={{ minWidth: 220 }}>Account</th>
                          {visiblePeriods.map((p) => (
                            <th key={p.period_id} className="mono text-right" style={{ minWidth: 120, whiteSpace: 'nowrap' }}>
                              {p.period_start.slice(0, 7)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          { label: 'Assets', sections: bs.assets, totals: visibleTotalAssets },
                          { label: 'Liabilities', sections: bs.liabilities, totals: visibleTotalLiab },
                          { label: 'Equity', sections: bs.equity, totals: visibleTotalEquity },
                        ].map(({ label, sections, totals }) => (
                          <Fragment key={label}>
                            <tr>
                              <td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 18, fontWeight: 600 }}>{label}</td>
                            </tr>
                            {sections.map((sec) => (
                              <Fragment key={sec.label}>
                                {!printMode && <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 10 }}>{sec.label}</td></tr>}
                                {!printMode && sec.rows.map((row) => (
                                  <tr key={row.account_code}>
                                    <td style={{ paddingLeft: 28 }}>
                                      <span className="mono muted" style={{ fontSize: 12.5 }}>{row.account_code}</span>
                                      <span style={{ marginLeft: 10 }}>{row.account_name}</span>
                                    </td>
                                    {slice(row.balances).map((bal, i) => (
                                      <td key={i} className="mono text-right" style={{ minWidth: 120 }}>{bal ? <Money val={bal} /> : null}</td>
                                    ))}
                                  </tr>
                                ))}
                                <tr>
                                  {printMode ? <td style={{ paddingLeft: 28 }}>{sec.label}</td> : <td className="muted-2" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>Subtotal — {sec.label}</td>}
                                  {slice(sec.subtotals).map((st, i) => (
                                    <td key={i} className="mono text-right" style={!printMode ? { borderTop: '1px solid var(--line)' } : undefined}><Money val={st} /></td>
                                  ))}
                                </tr>
                              </Fragment>
                            ))}
                            <tr>
                              <td className="fw-600">Total {label}</td>
                              {totals.map((t, i) => (
                                <td key={i} className="mono text-right fw-600" style={{ borderTop: '1px solid var(--line-2)' }}><Money val={t} /></td>
                              ))}
                            </tr>
                          </Fragment>
                        ))}
                        <tr>
                          <td className="fw-600" style={{ paddingTop: 10 }}>Total Liabilities + Equity</td>
                          {visiblePeriods.map((_, i) => {
                            const liab = parseFloat(visibleTotalLiab[i] ?? '0')
                            const eq = parseFloat(visibleTotalEquity[i] ?? '0')
                            return <td key={i} className="mono text-right fw-600" style={{ borderTop: '1px solid var(--line-2)', paddingTop: 10 }}><Money val={(liab + eq).toFixed(2)} /></td>
                          })}
                        </tr>
                        {bs.off_balance_sheet.length > 0 && (
                          <>
                            <tr><td colSpan={colCount} className="muted-2" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 24, fontStyle: 'italic', fontWeight: 600 }}>Off-Balance-Sheet (Memo)</td></tr>
                            {bs.off_balance_sheet.map((sec) => (
                              <Fragment key={sec.label}>
                                {!printMode && <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 10 }}>{sec.label}</td></tr>}
                                {!printMode && sec.rows.map((row) => (
                                  <tr key={row.account_code}>
                                    <td style={{ paddingLeft: 28 }}><span className="mono muted" style={{ fontSize: 12.5 }}>{row.account_code}</span><span style={{ marginLeft: 10 }}>{row.account_name}</span></td>
                                    {slice(row.balances).map((bal, i) => <td key={i} className="mono text-right" style={{ minWidth: 120 }}>{bal && parseFloat(bal) !== 0 ? <Money val={bal} /> : null}</td>)}
                                  </tr>
                                ))}
                                <tr>
                                  {printMode ? <td style={{ paddingLeft: 28 }}>{sec.label}</td> : <td className="muted-2" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>Subtotal — {sec.label}</td>}
                                  {slice(sec.subtotals).map((st, i) => <td key={i} className="mono text-right" style={!printMode ? { borderTop: '1px solid var(--line)' } : undefined}><Money val={st} /></td>)}
                                </tr>
                              </Fragment>
                            ))}
                            <tr>
                              <td className="muted-2" style={{ fontStyle: 'italic' }}>Total Off-Balance-Sheet</td>
                              {visibleTotalOff.map((t, i) => <td key={i} className="mono text-right" style={{ borderTop: '1px solid var(--line-2)' }}><Money val={t} /></td>)}
                            </tr>
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                )
              })()}
            </div>
          </div>
        )}

        {/* Income Statement */}
        {(activeTab === 'income_statement' || printMode) && (
          <div className="card mb-4">
            <div className="card-hd">
              <div>
                <div className="card-title">Income Statement</div>
                <div className="card-sub">{incMode === 'rolling' ? 'Rolling 3 periods' : 'All periods · aggregate'}</div>
              </div>
              <div className="row gap-3 print-hide">
                <select className="inp" style={{ width: 130 }} value={incMode} onChange={(e) => setIncMode(e.target.value as 'rolling' | 'aggregate')}>
                  <option value="rolling">Rolling 3</option>
                  <option value="aggregate">Aggregate</option>
                </select>
                {incMode === 'rolling' && closedPeriods.length > 0 && (
                  <>
                    <span className="muted-2" style={{ fontSize: 13 }}>Ending:</span>
                    <select className="inp" style={{ width: 140 }} value={incAnchorId || closedPeriods[0].period_id} onChange={(e) => setIncAnchorId(e.target.value)}>
                      {closedPeriods.map((p) => <option key={p.period_id} value={p.period_id}>{p.period_start.slice(0, 7)}</option>)}
                    </select>
                  </>
                )}
              </div>
            </div>
            <div className="card-bd">
              {incLoading && <p className="muted">Loading…</p>}
              {incError && <p className="color-red">Failed to load income statement.</p>}
              {!incLoading && !incError && incMode === 'rolling' && !closedPeriods.length && <EmptyState message="No closed periods found." />}
              {!incLoading && !incError && incReady && (() => {
                const incomeSections = pivotIncomeSection(incResponses, 'income')
                const expenseSections = pivotIncomeSection(incResponses, 'expenses')
                const ociSections = pivotIncomeSection(incResponses, 'other_comprehensive_income')
                const totalIncome = incResponses.map((r) => r!.total_income)
                const totalExpenses = incResponses.map((r) => r!.total_expenses)
                const totalOci = incResponses.map((r) => r!.total_oci)
                const netIncome = incResponses.map((r) => r!.net_income)
                const compIncome = incResponses.map((r) => r!.comprehensive_income)
                const colCount = incColCount + 1
                const hasOci = ociSections.length > 0

                const renderSectionGroup = (heading: string, sections: IncPivotSection[], totalLabel: string, totals: string[]) => (
                  <>
                    <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 18, fontWeight: 600 }}>{heading}</td></tr>
                    {sections.length === 0 && <tr><td colSpan={colCount} className="muted" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>No activity.</td></tr>}
                    {sections.map((sec) => (
                      <Fragment key={sec.label}>
                        {!printMode && <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 10 }}>{sec.label}</td></tr>}
                        {!printMode && sec.rows.map((row) => (
                          <tr key={row.account_code}>
                            <td style={{ paddingLeft: 28 }}><span className="mono muted" style={{ fontSize: 12.5 }}>{row.account_code}</span><span style={{ marginLeft: 10 }}>{row.account_name}</span></td>
                            {row.amounts.map((amt, i) => <td key={i} className="mono text-right" style={{ minWidth: 120 }}>{parseFloat(amt) !== 0 ? <Money val={amt} /> : null}</td>)}
                          </tr>
                        ))}
                        <tr>
                          {printMode ? <td style={{ paddingLeft: 28 }}>{sec.label}</td> : <td className="muted-2" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>Subtotal — {sec.label}</td>}
                          {sec.subtotals.map((st, i) => <td key={i} className="mono text-right" style={!printMode ? { borderTop: '1px solid var(--line)' } : undefined}><Money val={st} /></td>)}
                        </tr>
                      </Fragment>
                    ))}
                    <tr>
                      <td className="fw-600">{totalLabel}</td>
                      {totals.map((t, i) => <td key={i} className="mono text-right fw-600" style={{ borderTop: '1px solid var(--line-2)' }}><Money val={t} /></td>)}
                    </tr>
                  </>
                )

                return (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th style={{ minWidth: 220 }}>Account</th>
                          {incMode === 'rolling'
                            ? incPeriods.map((p) => <th key={p.period_id} className="mono text-right" style={{ minWidth: 120, whiteSpace: 'nowrap' }}>{p.period_start.slice(0, 7)}</th>)
                            : <th className="mono text-right" style={{ minWidth: 140, whiteSpace: 'nowrap' }}>{incResponses[0]?.range_label ?? 'All Periods'}</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {renderSectionGroup('Income', incomeSections, 'Total Income', totalIncome)}
                        {renderSectionGroup('Expenses', expenseSections, 'Total Expenses', totalExpenses)}
                        <tr>
                          <td className="fw-600" style={{ paddingTop: 10 }}>Net Income</td>
                          {netIncome.map((t, i) => <td key={i} className="mono text-right fw-600" style={{ borderTop: '1px solid var(--line-2)', paddingTop: 10 }}><Money val={t} /></td>)}
                        </tr>
                        {hasOci && (
                          <>
                            {renderSectionGroup('Other Comprehensive Income', ociSections, 'Total OCI', totalOci)}
                            <tr>
                              <td className="fw-600" style={{ paddingTop: 10 }}>Comprehensive Income</td>
                              {compIncome.map((t, i) => <td key={i} className="mono text-right fw-600" style={{ borderTop: '1px solid var(--line-2)', paddingTop: 10 }}><Money val={t} /></td>)}
                            </tr>
                          </>
                        )}
                      </tbody>
                    </table>
                  </div>
                )
              })()}
            </div>
          </div>
        )}

        {/* Cashflows */}
        {(activeTab === 'cashflows' || printMode) && (
          <div className="card mb-4">
            <div className="card-hd">
              <div>
                <div className="card-title">Statement of Cash Flows</div>
                <div className="card-sub">Rolling 3 periods · indirect method</div>
              </div>
              {closedPeriods.length > 0 && (
                <div className="row gap-3 print-hide">
                  <span className="muted-2" style={{ fontSize: 13 }}>Ending:</span>
                  <select className="inp" style={{ width: 140 }} value={cfAnchorId || closedPeriods[0].period_id} onChange={(e) => setCfAnchorId(e.target.value)}>
                    {closedPeriods.map((p) => <option key={p.period_id} value={p.period_id}>{p.period_start.slice(0, 7)}</option>)}
                  </select>
                </div>
              )}
            </div>
            <div className="card-bd">
              {cfLoading && <p className="muted">Loading…</p>}
              {cfError && <p className="color-red">Failed to load cash flows.</p>}
              {!cfLoading && !cfError && !closedPeriods.length && <EmptyState message="No closed periods found." />}
              {!cfLoading && !cfError && cfReady && (() => {
                const noncash = printMode ? pivotCashflowBySubCategory(cfResponses, 'noncash_adjustments') : pivotCashflowLines(cfResponses, 'noncash_adjustments')
                const wc = printMode ? pivotCashflowBySubCategory(cfResponses, 'working_capital_changes') : pivotCashflowLines(cfResponses, 'working_capital_changes')
                const investing = printMode ? pivotCashflowBySubCategory(cfResponses, 'investing') : pivotCashflowLines(cfResponses, 'investing')
                const financing = printMode ? pivotCashflowBySubCategory(cfResponses, 'financing') : pivotCashflowLines(cfResponses, 'financing')
                const cashByAcct = pivotCashflowLines(cfResponses, 'cash_by_account')
                const netInc = cfResponses.map((r) => r!.net_income)
                const opTotal = cfResponses.map((r) => r!.operating_total)
                const invTotal = cfResponses.map((r) => r!.investing_total)
                const finTotal = cfResponses.map((r) => r!.financing_total)
                const netChange = cfResponses.map((r) => r!.net_change_in_cash)
                const beginCash = cfResponses.map((r) => r!.beginning_cash)
                const endCash = cfResponses.map((r) => r!.ending_cash)
                const colCount = cfPeriods.length + 1

                const renderRows = (rows: IncPivotRow[] | SubCategoryRow[]) => rows.map((row) => {
                  const isSub = 'sub_category' in row
                  const key = isSub ? row.sub_category : row.account_code
                  return (
                    <tr key={key}>
                      <td style={{ paddingLeft: 28 }}>
                        {isSub ? row.sub_category : <><span className="mono muted" style={{ fontSize: 12.5 }}>{row.account_code}</span><span style={{ marginLeft: 10 }}>{row.account_name}</span></>}
                      </td>
                      {row.amounts.map((amt, i) => <td key={i} className="mono text-right" style={{ minWidth: 120 }}>{parseFloat(amt) !== 0 ? <Money val={amt} /> : null}</td>)}
                    </tr>
                  )
                })
                const subhead = (label: string) => <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 12, paddingLeft: 14 }}>{label}</td></tr>
                const sectionHead = (label: string) => <tr><td colSpan={colCount} className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 18, fontWeight: 600 }}>{label}</td></tr>
                const totalRow = (label: string, totals: string[], heavy = false) => <tr><td className="fw-600">{label}</td>{totals.map((t, i) => <td key={i} className="mono text-right fw-600" style={{ borderTop: `${heavy ? 2 : 1}px solid var(--line-2)` }}><Money val={t} /></td>)}</tr>

                return (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th style={{ minWidth: 220 }}>Account</th>
                          {cfPeriods.map((p) => <th key={p.period_id} className="mono text-right" style={{ minWidth: 120, whiteSpace: 'nowrap' }}>{p.period_start.slice(0, 7)}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {sectionHead('Operating Activities')}
                        <tr>
                          <td style={{ paddingLeft: 14 }}>Net income</td>
                          {netInc.map((t, i) => <td key={i} className="mono text-right" style={{ minWidth: 120 }}><Money val={t} /></td>)}
                        </tr>
                        {noncash.length > 0 && <>{subhead('Adjustments for non-cash items')}{renderRows(noncash)}</>}
                        {wc.length > 0 && <>{subhead('Changes in working capital')}{renderRows(wc)}</>}
                        {totalRow('Net cash from operating activities', opTotal)}
                        {sectionHead('Investing Activities')}
                        {investing.length === 0 && <tr><td colSpan={colCount} className="muted" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>No activity.</td></tr>}
                        {renderRows(investing)}
                        {totalRow('Net cash from investing activities', invTotal)}
                        {sectionHead('Financing Activities')}
                        {financing.length === 0 && <tr><td colSpan={colCount} className="muted" style={{ paddingLeft: 28, fontStyle: 'italic', fontSize: 12.5 }}>No activity.</td></tr>}
                        {renderRows(financing)}
                        {totalRow('Net cash from financing activities', finTotal)}
                        {totalRow('Net change in cash', netChange, true)}
                        <tr>
                          <td className="muted-2" style={{ paddingTop: 14 }}>Beginning cash balance</td>
                          {beginCash.map((t, i) => <td key={i} className="mono text-right" style={{ paddingTop: 14, minWidth: 120 }}><Money val={t} /></td>)}
                        </tr>
                        <tr>
                          <td className="muted-2">+ Net change in cash</td>
                          {netChange.map((t, i) => <td key={i} className="mono text-right" style={{ minWidth: 120 }}><Money val={t} /></td>)}
                        </tr>
                        <tr>
                          <td className="fw-600" style={{ paddingTop: 6 }}>Ending cash balance</td>
                          {endCash.map((t, i) => <td key={i} className="mono text-right fw-600" style={{ borderTop: '2px solid var(--line-2)', paddingTop: 6 }}><Money val={t} /></td>)}
                        </tr>
                        {!printMode && cashByAcct.length > 0 && <>{sectionHead('Cash change by account')}{renderRows(cashByAcct)}</>}
                      </tbody>
                    </table>
                  </div>
                )
              })()}
            </div>
          </div>
        )}
      </div>
    </Layout>
  )
}

