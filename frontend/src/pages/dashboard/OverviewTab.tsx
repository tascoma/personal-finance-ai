import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import HeroSparkline from '../../components/HeroSparkline'
import RingChart from '../../components/RingChart'
import SankeyChart from '../../components/SankeyChart'
import { fmtMoney } from '../../utils/format'
import { getChartPalette, moneyTick, moneyTip } from './chartTheme'
import { buildIncomeStatementSankey, SANKEY_COLORS } from './sankeyData'
import { TARGET_YEAR, type DashboardTabProps } from './constants'

const CONTRIB_LIMIT_401K = 24_500
const CONTRIB_LIMIT_IRA = 7_500
const CONTRIB_LIMIT_HSA = 4_400
const CONTRIB_LIMIT_TOTAL = CONTRIB_LIMIT_401K + CONTRIB_LIMIT_IRA + CONTRIB_LIMIT_HSA

function accountLimit(name: string): number {
  const n = name.toLowerCase()
  if (n.includes('401')) return CONTRIB_LIMIT_401K
  if (n.includes('ira')) return CONTRIB_LIMIT_IRA
  if (n.includes('hsa')) return CONTRIB_LIMIT_HSA
  return 0
}

export default function OverviewTab({ data, scopeLabel }: DashboardTabProps) {
  const ieRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!ieRef.current || !data.period_bars.length) return
    const palette = getChartPalette()
    const { green, red } = palette
    const chart = new Chart(ieRef.current, {
      type: 'bar',
      data: {
        labels: data.period_bars.map((d) => d.period_label),
        datasets: [
          { label: 'Income', data: data.period_bars.map((d) => parseFloat(d.income)), backgroundColor: green + '99', borderColor: green, borderWidth: 1, borderRadius: 4 },
          { label: 'Expenses', data: data.period_bars.map((d) => parseFloat(d.expenses)), backgroundColor: red + '99', borderColor: red, borderWidth: 1, borderRadius: 4 },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', labels: { boxWidth: 12, padding: 16 } }, tooltip: { callbacks: { label: moneyTip } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick } } } },
    })
    return () => chart.destroy()
  }, [data])

  // Hero data
  const nwSeries = data.net_worth_series.map((p) => parseFloat(p.net_worth))
  const nwLabels = data.net_worth_series.map((p) => p.period_label)
  const currentNw = parseFloat(data.net_worth)
  const yoyDelta = nwSeries.length > 1 ? currentNw - nwSeries[0] : 0
  const yoyPct = nwSeries.length > 1 && nwSeries[0] ? (yoyDelta / nwSeries[0]) * 100 : 0

  const compensation = parseFloat(data.compensation_income)
  const savingsContribs = parseFloat(data.retirement_contributions)
  const savingsRate = compensation > 0 ? (savingsContribs / compensation) * 100 : 0

  const lastMonthNwDelta = nwSeries.length >= 2 ? nwSeries[nwSeries.length - 1] - nwSeries[nwSeries.length - 2] : null
  const totalLiabilities = parseFloat(data.total_assets) - currentNw
  const debtToEquity = currentNw !== 0 ? totalLiabilities / currentNw : null

  // Asset composition for ring chart
  const composition = data.asset_composition
  const totalAssets = parseFloat(data.total_assets)
  const assetColors = ['var(--accent)', 'var(--green)', 'var(--amber)', 'var(--purple)', '#38bdf8', 'var(--pink)', '#fb923c', '#34d399']
  const ringData = composition.slice(0, 6).map((d, i) => ({ amount: parseFloat(d.amount), color: assetColors[i % assetColors.length], name: d.sub_category }))

  const retirementContribs = data.ytd_retirement_contributions ?? []
  const retirementTotal = retirementContribs.reduce((s, c) => s + Math.max(0, parseFloat(c.amount)), 0)
  const retirementPct = (retirementTotal / CONTRIB_LIMIT_TOTAL) * 100
  // Pace check: contributions should be ~(months elapsed / 12) of the annual limit by now.
  const expectedRetirementPct = (new Date().getMonth() + 1) / 12 * 100
  const retirementOnTrack = retirementPct >= expectedRetirementPct

  return (
    <>
      {/* Hero net worth */}
      {nwSeries.length > 0 && (
        <div className="hero count-anim mb-4">
          <div className="stack gap-2" style={{ justifyContent: 'space-between' }}>
            <div>
              <div className="hero-eyebrow">Net Worth · {scopeLabel}</div>
              <div className="hero-number">{fmtMoney(String(currentNw))}</div>
              <div className="hero-delta">
                <SvgIcon name="trending" size={14} />
                {yoyDelta >= 0 ? '+' : ''}{fmtMoney(String(yoyDelta))} ({yoyPct >= 0 ? '+' : ''}{yoyPct.toFixed(1)}%) · YTD
              </div>
            </div>
            <div className="hero-stats">
              <div className="hero-stat">
                <div className="hero-stat-label">This month</div>
                <div className="hero-stat-value">{lastMonthNwDelta !== null ? `${lastMonthNwDelta >= 0 ? '+' : ''}${fmtMoney(String(lastMonthNwDelta))}` : '—'}</div>
              </div>
              <div className="hero-stat">
                <div className="hero-stat-label">Debt to Equity</div>
                <div className="hero-stat-value">{debtToEquity !== null ? debtToEquity.toFixed(2) : '—'}</div>
              </div>
              <div className="hero-stat">
                <div className="hero-stat-label">Retirement Savings Rate</div>
                <div className="hero-stat-value">{savingsRate.toFixed(1)}%</div>
              </div>
            </div>
          </div>
          <div style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column' }}>
            <HeroSparkline data={nwSeries} labels={nwLabels} />
          </div>
        </div>
      )}

      {/* Asset + retirement rings */}
      {composition.length > 0 && (
        <div className="grid grid-12 mb-4">
          <div className="card col-7">
            <div className="card-hd">
              <div>
                <div className="card-title">Asset Composition</div>
                <div className="card-sub">{fmtMoney(String(totalAssets))} across {composition.length} buckets</div>
              </div>
              <span className="badge badge--ghost">{scopeLabel}</span>
            </div>
            <div className="card-bd">
              <div className="ring-wrap">
                <RingChart
                  data={ringData}
                  size={200}
                  centerLabel="Total"
                  centerValue={<span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{fmtMoney(String(totalAssets))}</span>}
                />
                <div className="legend">
                  {ringData.map((a, i) => {
                    const pct = totalAssets > 0 ? (a.amount / totalAssets) * 100 : 0
                    return (
                      <div key={i} className="legend-row">
                        <span className="legend-swatch" style={{ background: a.color }} />
                        <span>{a.name}</span>
                        <span className="legend-pct">{fmtMoney(String(a.amount))} · {pct.toFixed(0)}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>

          {retirementContribs.length > 0 ? (
            <div className="card col-5">
              <div className="card-hd">
                <div>
                  <div className="card-title">Retirement Progress</div>
                  <div className="card-sub">{TARGET_YEAR} contribution limits</div>
                </div>
                <span className={`badge ${retirementOnTrack ? 'badge--accent' : 'badge--amber'}`}><span className="badge-dot" />{retirementOnTrack ? 'On track' : 'Behind'}</span>
              </div>
              <div className="card-bd">
                <div className="row gap-4">
                  <RingChart
                    data={[
                      { amount: retirementTotal, color: 'var(--accent)' },
                      { amount: Math.max(0, CONTRIB_LIMIT_TOTAL - retirementTotal), color: 'var(--line)' },
                    ]}
                    size={168}
                    goalPct={80}
                    centerLabel="of limit"
                    centerValue={<span className="mono" style={{ fontSize: 26, fontWeight: 600 }}>{retirementPct.toFixed(1)}%</span>}
                  />
                  <div className="stack gap-3" style={{ flex: 1 }}>
                    {retirementContribs.map((c) => {
                      const limit = accountLimit(c.account_name)
                      const pct = limit > 0 ? (Math.max(0, parseFloat(c.amount)) / limit) * 100 : null
                      return (
                        <div key={c.account_code}>
                          <div className="spread mb-1">
                            <span style={{ fontSize: 12.5 }}>{c.account_name}</span>
                            <span className="mono fw-600" style={{ fontSize: 12.5 }}>{fmtMoney(c.amount)}{limit > 0 ? ` / ${fmtMoney(String(limit))}` : ''}</span>
                          </div>
                          {pct !== null && (
                            <div style={{ height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
                              <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, background: 'var(--accent)', borderRadius: 2 }} />
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="card col-5">
              <div className="card-hd"><div><div className="card-title">KPIs</div></div></div>
              <div className="card-bd stack gap-3">
                <div className="spread"><span className="muted" style={{ fontSize: 12.5 }}>Total Assets</span><span className="mono fw-600">{fmtMoney(data.total_assets)}</span></div>
                <div className="spread"><span className="muted" style={{ fontSize: 12.5 }}>Net Worth</span><span className="mono fw-600">{fmtMoney(data.net_worth)}</span></div>
                <div className="spread"><span className="muted" style={{ fontSize: 12.5 }}>Savings Rate</span><span className="mono fw-600">{savingsRate.toFixed(1)}%</span></div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Income vs Expenses + Income Statement */}
      <div className="grid grid-12 mb-4">
        <div className="card col-8">
          <div className="card-hd">
            <div><div className="card-title">Income vs Expenses</div><div className="card-sub">by period</div></div>
            <div className="row gap-3">
              <span className="row gap-2 muted" style={{ fontSize: 11.5 }}><span style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--green)', display: 'inline-block' }} />Income</span>
              <span className="row gap-2 muted" style={{ fontSize: 11.5 }}><span style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--red)', display: 'inline-block' }} />Expenses</span>
            </div>
          </div>
          <div className="card-bd">
            {data.period_bars.length ? <div style={{ height: 180 }}><canvas ref={ieRef} /></div> : <EmptyState message="No data yet." />}
          </div>
        </div>

        {(() => {
          const totalIncome = parseFloat(data.total_income)
          const totalExpenses = parseFloat(data.total_expenses)
          const netIncome = totalIncome - totalExpenses
          const netColor = netIncome >= 0 ? 'var(--green)' : 'var(--red)'
          return (
            <div className="card col-4">
              <div className="card-hd">
                <div>
                  <div className="card-title">Income Statement</div>
                  <div className="card-sub">{scopeLabel}</div>
                </div>
              </div>
              <div className="card-bd stack gap-3">
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>Revenue</span>
                  <span className="mono fw-600" style={{ fontSize: 13, color: 'var(--green)' }}>{fmtMoney(data.total_income)}</span>
                </div>
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>Expenses</span>
                  <span className="mono fw-600" style={{ fontSize: 13, color: 'var(--red)' }}>({fmtMoney(data.total_expenses)})</span>
                </div>
                <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
                <div className="spread">
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Net Income</span>
                  <span className="mono fw-600" style={{ fontSize: 15, color: netColor }}>{netIncome >= 0 ? '' : '('}{fmtMoney(String(Math.abs(netIncome)))}{netIncome < 0 ? ')' : ''}</span>
                </div>
                {(() => {
                  const oci = parseFloat(data.oci)
                  if (oci === 0) return null
                  const comprehensive = netIncome + oci
                  const ociColor = oci >= 0 ? 'var(--green)' : 'var(--red)'
                  const comprehensiveColor = comprehensive >= 0 ? 'var(--green)' : 'var(--red)'
                  return (
                    <>
                      <div className="spread">
                        <span className="muted" style={{ fontSize: 12.5 }}>OCI</span>
                        <span className="mono fw-600" style={{ fontSize: 13, color: ociColor }}>{oci >= 0 ? '' : '('}{fmtMoney(String(Math.abs(oci)))}{oci < 0 ? ')' : ''}</span>
                      </div>
                      <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
                      <div className="spread">
                        <span style={{ fontSize: 13, fontWeight: 600 }}>Comprehensive Income</span>
                        <span className="mono fw-600" style={{ fontSize: 15, color: comprehensiveColor }}>{comprehensive >= 0 ? '' : '('}{fmtMoney(String(Math.abs(comprehensive)))}{comprehensive < 0 ? ')' : ''}</span>
                      </div>
                    </>
                  )
                })()}
              </div>
            </div>
          )
        })()}
      </div>

      {/* Money flow */}
      {(() => {
        const sankey = buildIncomeStatementSankey(data.money_flow, SANKEY_COLORS)
        return (
          <div className="card mb-4">
            <div className="card-hd">
              <div><div className="card-title">Money Flow</div><div className="card-sub">{scopeLabel}</div></div>
            </div>
            <div className="card-bd">
              {sankey.nodes.length ? (
                <SankeyChart model={sankey} />
              ) : <EmptyState message="No income or expenses recorded yet." />}
            </div>
          </div>
        )
      })()}

      {/* Top categories + Recent activity */}
      <div className="grid grid-12">
        <div className="card col-5">
          <div className="card-hd">
            <div><div className="card-title">Top Categories</div><div className="card-sub">{scopeLabel}</div></div>
            <Link to="/statements" className="btn btn-ghost btn-sm">View all <SvgIcon name="arrow" size={13} /></Link>
          </div>
          <div className="card-bd">
            {data.top_expense_categories.length ? (
              <div className="stack gap-3">
                {data.top_expense_categories.slice(0, 6).map((d) => {
                  const max = parseFloat(data.top_expense_categories[0].amount)
                  const pct = max > 0 ? (parseFloat(d.amount) / max) * 100 : 0
                  return (
                    <div key={d.category}>
                      <div className="spread mb-2">
                        <span style={{ fontSize: 12.5 }}>{d.category}</span>
                        <span className="mono fw-600" style={{ fontSize: 12.5 }}>{fmtMoney(d.amount)}</span>
                      </div>
                      <div style={{ height: 5, background: 'var(--bg-3)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', borderRadius: 3 }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : <EmptyState message="No expenses yet." />}
          </div>
        </div>

        <div className="card col-7">
          <div className="card-hd">
            <div><div className="card-title">Recent Activity</div><div className="card-sub">Latest 6 posted entries</div></div>
            <Link to="/ledger" className="btn btn-ghost btn-sm">Open ledger <SvgIcon name="arrow" size={13} /></Link>
          </div>
          {data.recent_entries.length ? (
            <div className="card-bd-flush">
              <table className="tbl">
                <thead>
                  <tr><th>Description</th><th>Period</th><th>Date</th><th>Type</th><th className="text-right">Amount</th></tr>
                </thead>
                <tbody>
                  {data.recent_entries.map((e, i) => (
                    <tr key={i}>
                      <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.description}</td>
                      <td className="muted" style={{ fontSize: 12 }}>{e.period_label}</td>
                      <td className="mono muted" style={{ fontSize: 12 }}>{e.entry_date}</td>
                      <td><span className="badge badge--ghost" style={{ fontSize: 10.5 }}>{e.source_type}</span></td>
                      <td className="mono text-right fw-600">${parseFloat(e.total_debit).toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState icon="journal" message="No entries posted yet." hint="Complete a period workflow to post entries." />}
        </div>
      </div>
    </>
  )
}
