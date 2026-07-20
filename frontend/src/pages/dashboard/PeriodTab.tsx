import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import { fetchDashboard } from '../../api/dashboard'
import { fetchCashflow } from '../../api/statements'
import { fmtMoney, fmtPeriod } from '../../utils/format'
import { getChartPalette, moneyTick } from './chartTheme'
import type { Period } from '../../types'

interface PeriodTabProps {
  periods: Period[]
  periodId: string
}

function pct(delta: number, base: number): number | null {
  return base !== 0 ? (delta / Math.abs(base)) * 100 : null
}

function DeltaBadge({ delta, pctVal }: { delta: number; pctVal: number | null }) {
  const positive = delta >= 0
  return (
    <span className="row gap-1" style={{ fontSize: 11.5, color: positive ? 'var(--green)' : 'var(--red)' }}>
      <SvgIcon name={positive ? 'trend-up' : 'trend-down'} size={12} />
      {positive ? '+' : ''}{fmtMoney(String(delta))}{pctVal != null ? ` (${positive ? '+' : ''}${pctVal.toFixed(1)}%)` : ''}
    </span>
  )
}

export default function PeriodTab({ periods, periodId }: PeriodTabProps) {
  const selectedPeriod = periods.find((p) => p.period_id === periodId)
  const selectedIdx = periods.findIndex((p) => p.period_id === periodId)
  const prevPeriodId = selectedIdx >= 0 && selectedIdx + 1 < periods.length
    ? periods[selectedIdx + 1].period_id
    : undefined

  const currentQ = useQuery({
    queryKey: ['dashboard-period', periodId],
    queryFn: () => fetchDashboard(periodId),
    enabled: !!periodId,
  })
  const prevQ = useQuery({
    queryKey: ['dashboard-period', prevPeriodId],
    queryFn: () => fetchDashboard(prevPeriodId),
    enabled: !!prevPeriodId,
  })
  const cfQ = useQuery({
    queryKey: ['cashflow', periodId],
    queryFn: () => fetchCashflow(periodId),
    enabled: !!periodId,
  })

  const spendChartRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const categories = currentQ.data?.top_expense_categories ?? []
    if (!spendChartRef.current || !categories.length) return
    const palette = getChartPalette()
    const catColors = [palette.accent, palette.green, palette.amber, palette.purple, '#38bdf8', palette.pink, '#fb923c', '#34d399']
    const chart = new Chart(spendChartRef.current, {
      type: 'bar',
      data: {
        labels: categories.map((d) => d.category),
        datasets: [{
          data: categories.map((d) => parseFloat(d.amount)),
          backgroundColor: categories.map((_, i) => catColors[i % catColors.length] + 'bb'),
          borderColor: categories.map((_, i) => catColors[i % catColors.length]),
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => ` $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } },
        },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick }, grace: '10%' } },
      },
    })
    return () => chart.destroy()
  }, [currentQ.data])

  if (periods.length === 0) {
    return (
      <div className="card">
        <EmptyState icon="periods" message="No closed periods yet." hint="Close a period from the Workflow page to see its snapshot here." />
      </div>
    )
  }
  if ((currentQ.isLoading || cfQ.isLoading) && !currentQ.data) {
    return <div className="card"><EmptyState message="Loading period snapshot…" /></div>
  }
  if (currentQ.error || cfQ.error || !currentQ.data || !cfQ.data) {
    return <div className="card"><EmptyState message="Couldn't load this period's data." /></div>
  }

  const curr = currentQ.data
  const prev = prevQ.data
  const cf = cfQ.data

  const totalIncome = parseFloat(curr.total_income)
  const totalExpenses = parseFloat(curr.total_expenses)
  const netIncome = totalIncome - totalExpenses
  const oci = parseFloat(curr.oci)
  const comprehensive = netIncome + oci

  const netWorth = parseFloat(curr.net_worth)
  const totalLiabilities = parseFloat(curr.total_liabilities)
  const debtToEquity = netWorth !== 0 ? totalLiabilities / netWorth : null

  const compensation = parseFloat(curr.compensation_income)
  const savingsContribs = parseFloat(curr.retirement_contributions)
  const savingsRate = compensation > 0 ? (savingsContribs / compensation) * 100 : 0

  const prevNetIncome = prev ? parseFloat(prev.total_income) - parseFloat(prev.total_expenses) : null
  const prevNetWorth = prev ? parseFloat(prev.net_worth) : null
  const prevCompensation = prev ? parseFloat(prev.compensation_income) : null
  const prevSavingsContribs = prev ? parseFloat(prev.retirement_contributions) : null
  const prevSavingsRate = prev && prevCompensation && prevCompensation > 0 && prevSavingsContribs != null
    ? (prevSavingsContribs / prevCompensation) * 100
    : null

  const netIncomeDelta = prevNetIncome != null ? netIncome - prevNetIncome : null
  const netWorthDelta = prevNetWorth != null ? netWorth - prevNetWorth : null
  const savingsRateDelta = prevSavingsRate != null ? savingsRate - prevSavingsRate : null

  const categories = curr.top_expense_categories
  const topCategory = categories[0]
  const topCategoryShare = topCategory && totalExpenses > 0 ? (parseFloat(topCategory.amount) / totalExpenses) * 100 : null

  const lifestyleRatio = totalExpenses > 0 ? (parseFloat(curr.lifestyle_expenses) / totalExpenses) * 100 : null

  const liquidAssets = parseFloat(curr.liquid_assets)
  const cashRunwayMonths = totalExpenses > 0 ? liquidAssets / totalExpenses : null
  const expenseToIncomeRatio = totalIncome > 0 ? (totalExpenses / totalIncome) * 100 : null
  const operatingCashFlow = parseFloat(cf.operating_total)
  const operatingCoverage = totalExpenses > 0 ? operatingCashFlow / totalExpenses : null

  return (
    <>
      <div className="hero hero--period count-anim mb-4">
        <div className="stack gap-2" style={{ justifyContent: 'space-between', gridColumn: '1 / -1' }}>
          <div>
            <div className="hero-eyebrow">Period · {selectedPeriod ? fmtPeriod(selectedPeriod.period_start) : ''}</div>
            <div className="hero-number">{fmtMoney(String(netIncome))}</div>
            <div className="hero-delta">
              {netIncomeDelta != null ? (
                <>
                  <SvgIcon name={netIncomeDelta >= 0 ? 'trend-up' : 'trend-down'} size={14} />
                  {netIncomeDelta >= 0 ? '+' : ''}{fmtMoney(String(netIncomeDelta))} vs prior period
                </>
              ) : (
                <span style={{ opacity: 0.8 }}>Net income · no prior period to compare</span>
              )}
            </div>
          </div>
          <div className="hero-stats hero-stats--spaced" style={{ gridTemplateColumns: 'repeat(7, 1fr)' }}>
            <div className="hero-stat" data-tip="Retirement contributions as a % of compensation income. Higher is better — aim for 15–20%.">
              <div className="hero-stat-label">Savings Rate</div>
              <div className="hero-stat-value">{savingsRate.toFixed(1)}%</div>
            </div>
            <div className="hero-stat" data-tip="Total assets minus total liabilities as of this period. Higher is better.">
              <div className="hero-stat-label">Net Worth</div>
              <div className="hero-stat-value">{fmtMoney(String(netWorth))}</div>
            </div>
            <div className="hero-stat" data-tip="Total liabilities divided by net worth. Lower is better — less debt relative to what you own.">
              <div className="hero-stat-label">Debt to Equity</div>
              <div className="hero-stat-value">{debtToEquity !== null ? debtToEquity.toFixed(2) : '—'}</div>
            </div>
            <div className="hero-stat" data-tip="Cash on hand at the end of this period. Higher is generally better.">
              <div className="hero-stat-label">Ending Cash</div>
              <div className="hero-stat-value">{fmtMoney(cf.ending_cash)}</div>
            </div>
            <div className="hero-stat" data-tip="Liquid assets divided by this period's expenses — months of spending your liquid cash would cover. Higher is better.">
              <div className="hero-stat-label">Cash Runway</div>
              <div className="hero-stat-value">{cashRunwayMonths !== null ? `${cashRunwayMonths.toFixed(1)} mo` : '—'}</div>
            </div>
            <div className="hero-stat" data-tip="Total expenses as a % of total income this period. Lower is better.">
              <div className="hero-stat-label">Expense / Income</div>
              <div className="hero-stat-value">{expenseToIncomeRatio !== null ? `${expenseToIncomeRatio.toFixed(1)}%` : '—'}</div>
            </div>
            <div className="hero-stat" data-tip="Operating cash flow divided by expenses. Above 1.0× means operations alone covered spending. Higher is better.">
              <div className="hero-stat-label">Op. CF Coverage</div>
              <div className="hero-stat-value">{operatingCoverage !== null ? `${operatingCoverage.toFixed(2)}×` : '—'}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-12 mb-4">
        <div className="card col-4">
          <div className="card-hd">
            <div>
              <div className="card-title">Income Statement Snapshot</div>
              <div className="card-sub">{selectedPeriod ? fmtPeriod(selectedPeriod.period_start) : ''}</div>
            </div>
          </div>
          <div className="card-bd stack gap-3">
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Revenue</span>
              <span className="mono fw-600" style={{ fontSize: 13, color: 'var(--green)' }}>{fmtMoney(curr.total_income)}</span>
            </div>
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Expenses</span>
              <span className="mono fw-600" style={{ fontSize: 13, color: 'var(--red)' }}>({fmtMoney(curr.total_expenses)})</span>
            </div>
            <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
            <div className="spread">
              <span style={{ fontSize: 13, fontWeight: 600 }}>Net Income</span>
              <span className="mono fw-600" style={{ fontSize: 15, color: netIncome >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {netIncome >= 0 ? '' : '('}{fmtMoney(String(Math.abs(netIncome)))}{netIncome < 0 ? ')' : ''}
              </span>
            </div>
            {oci !== 0 && (
              <>
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>OCI</span>
                  <span className="mono fw-600" style={{ fontSize: 13, color: oci >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {oci >= 0 ? '' : '('}{fmtMoney(String(Math.abs(oci)))}{oci < 0 ? ')' : ''}
                  </span>
                </div>
                <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
                <div className="spread">
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Comprehensive Income</span>
                  <span className="mono fw-600" style={{ fontSize: 15, color: comprehensive >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {comprehensive >= 0 ? '' : '('}{fmtMoney(String(Math.abs(comprehensive)))}{comprehensive < 0 ? ')' : ''}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="card col-4">
          <div className="card-hd">
            <div>
              <div className="card-title">Balance Sheet Snapshot</div>
              <div className="card-sub">as of {selectedPeriod ? fmtPeriod(selectedPeriod.period_start) : ''}</div>
            </div>
          </div>
          <div className="card-bd stack gap-3">
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Total Assets</span>
              <span className="mono fw-600">{fmtMoney(curr.total_assets)}</span>
            </div>
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Total Liabilities</span>
              <span className="mono fw-600">{fmtMoney(curr.total_liabilities)}</span>
            </div>
            <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
            <div className="spread">
              <span style={{ fontSize: 13, fontWeight: 600 }}>Net Worth</span>
              <span className="mono fw-600" style={{ fontSize: 15 }}>{fmtMoney(String(netWorth))}</span>
              {netWorthDelta != null && <DeltaBadge delta={netWorthDelta} pctVal={pct(netWorthDelta, prevNetWorth ?? 0)} />}
            </div>
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Liquid Assets</span>
              <span className="mono fw-600">{fmtMoney(curr.liquid_assets)}</span>
            </div>
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Tax-Advantaged</span>
              <span className="mono fw-600">{fmtMoney(curr.tax_advantaged)}</span>
            </div>
          </div>
        </div>

        <div className="card col-4">
          <div className="card-hd">
            <div>
              <div className="card-title">Cash Flow Snapshot</div>
              <div className="card-sub">{selectedPeriod ? fmtPeriod(selectedPeriod.period_start) : ''}</div>
            </div>
          </div>
          <div className="card-bd stack gap-3">
            {[
              { label: 'Operating', value: parseFloat(cf.operating_total) },
              { label: 'Investing', value: parseFloat(cf.investing_total) },
              { label: 'Financing', value: parseFloat(cf.financing_total) },
              { label: 'Net Change', value: parseFloat(cf.net_change_in_cash) },
            ].map((s) => (
              <div key={s.label} className="spread">
                <span className="muted" style={{ fontSize: 12.5 }}>{s.label}</span>
                <span className="mono fw-600" style={{ fontSize: 13, color: s.value >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {s.value >= 0 ? '+' : '-'}{fmtMoney(String(Math.abs(s.value)))}
                </span>
              </div>
            ))}
            <div style={{ height: 1, background: 'var(--line)', margin: '2px 0' }} />
            <div className="spread">
              <span className="muted" style={{ fontSize: 12.5 }}>Beginning → Ending</span>
              <span className="mono fw-600">{fmtMoney(cf.beginning_cash)} → {fmtMoney(cf.ending_cash)}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb-4">
        <div className="card-hd">
          <div>
            <div className="card-title">Spend Categories</div>
            <div className="card-sub">{selectedPeriod ? fmtPeriod(selectedPeriod.period_start) : ''}</div>
          </div>
        </div>
        <div className="card-bd">
          {categories.length ? (
            <div style={{ height: 260 }}><canvas ref={spendChartRef} /></div>
          ) : <EmptyState message="No expenses recorded this period." />}
        </div>
      </div>

      <div className="card">
        <div className="card-hd"><div className="card-title">Insights</div></div>
        <div className="card-bd stack gap-3">
          <div className="row gap-2" style={{ fontSize: 13 }}>
            <SvgIcon name="trending" size={14} />
            {netIncomeDelta != null ? (
              <span>
                Net income {netIncomeDelta >= 0 ? 'increased' : 'decreased'} by {fmtMoney(String(Math.abs(netIncomeDelta)))}
                {pct(netIncomeDelta, prevNetIncome ?? 0) != null ? ` (${Math.abs(pct(netIncomeDelta, prevNetIncome ?? 0)!).toFixed(1)}%)` : ''} vs the prior period.
              </span>
            ) : (
              <span>First tracked period — no prior comparison.</span>
            )}
          </div>

          <div className="row gap-2" style={{ fontSize: 13 }}>
            <SvgIcon name="trending" size={14} />
            {compensation === 0 ? (
              <span>No compensation income recorded this period.</span>
            ) : savingsRateDelta != null ? (
              <span>
                Savings rate is {savingsRate.toFixed(1)}%, {savingsRateDelta >= 0 ? 'up' : 'down'} {Math.abs(savingsRateDelta).toFixed(1)} pts from the prior period.
              </span>
            ) : (
              <span>Savings rate is {savingsRate.toFixed(1)}% — no prior period to compare.</span>
            )}
          </div>

          <div className="row gap-2" style={{ fontSize: 13 }}>
            <SvgIcon name="trending" size={14} />
            {netWorthDelta != null ? (
              <span>
                Net worth {netWorthDelta >= 0 ? 'grew' : 'shrank'} by {fmtMoney(String(Math.abs(netWorthDelta)))}
                {pct(netWorthDelta, prevNetWorth ?? 0) != null ? ` (${Math.abs(pct(netWorthDelta, prevNetWorth ?? 0)!).toFixed(1)}%)` : ''} vs the prior period.
              </span>
            ) : (
              <span>No prior period to compare net worth against.</span>
            )}
          </div>

          {topCategory && topCategoryShare != null && (
            <div className="row gap-2" style={{ fontSize: 13 }}>
              <SvgIcon name="trending" size={14} />
              <span>
                {topCategory.category} was your largest expense at {fmtMoney(topCategory.amount)} ({topCategoryShare.toFixed(0)}% of total spend).
              </span>
            </div>
          )}

          {lifestyleRatio != null && (
            <div className="row gap-2" style={{ fontSize: 13 }}>
              <SvgIcon name="trending" size={14} />
              <span>Discretionary (lifestyle) spending made up {lifestyleRatio.toFixed(0)}% of total expenses.</span>
            </div>
          )}

          {oci !== 0 && (
            <div className="row gap-2" style={{ fontSize: 13 }}>
              <SvgIcon name="trending" size={14} />
              <span>
                Other comprehensive income of {fmtMoney(String(oci))} brought comprehensive income to {fmtMoney(String(comprehensive))}.
              </span>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
