import { useEffect, useRef, useState } from 'react'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import HeroSparkline from '../../components/HeroSparkline'
import RingChart from '../../components/RingChart'
import { fmtMoney } from '../../utils/format'
import { getChartPalette, moneyTick } from './chartTheme'
import type { DashboardTabProps } from './constants'

export default function ExpensesTab({ data, scopeLabel }: DashboardTabProps) {
  const [trendScale, setTrendScale] = useState<'all' | 'under1k'>('all')
  const stackRef = useRef<HTMLCanvasElement>(null)
  const compRef = useRef<HTMLCanvasElement>(null)

  // Expense trendlines (per sub-category) — redraws when the scale toggle changes.
  useEffect(() => {
    if (!stackRef.current || !data.expense_category_series.length) return
    const palette = getChartPalette()
    const { red, accent, green, amber } = palette
    const catColors = [red, amber, accent, green, '#a78bfa', '#38bdf8', '#fb923c', '#34d399']
    // Stable map keyed by top_expense_categories order — same order used by donut + comp charts
    const stableCatMap = new Map<string, string>(
      data.top_expense_categories.map((d, i) => [d.category, catColors[i % catColors.length]]),
    )
    const colorOf = (cat: string, fallbackIdx: number) =>
      stableCatMap.get(cat) ?? catColors[(data.top_expense_categories.length + fallbackIdx) % catColors.length]
    const periodLabels = [...new Set(data.expense_category_series.map((p) => p.period_label))]
    const allCategories = [...new Set(data.expense_category_series.map((p) => p.category))]
    const seriesByKey = new Map<string, number>()
    for (const row of data.expense_category_series) seriesByKey.set(`${row.period_label}|${row.category}`, parseFloat(row.amount))
    const extraCategories = allCategories.filter((c) => !stableCatMap.has(c))
    const categories = trendScale === 'under1k' ? allCategories.filter((cat) => Math.max(...periodLabels.map((pl) => seriesByKey.get(`${pl}|${cat}`) ?? 0)) < 1000) : allCategories
    const datasets = categories.map((cat) => {
      const color = colorOf(cat, extraCategories.indexOf(cat))
      return { label: cat, data: periodLabels.map((pl) => seriesByKey.get(`${pl}|${cat}`) ?? 0), backgroundColor: color + '99', borderColor: color, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: color, pointBorderColor: color, fill: true, tension: 0.3 }
    })
    const chart = new Chart(stackRef.current, {
      type: 'line',
      data: { labels: periodLabels, datasets },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { grid: { display: false } }, y: { stacked: true, ticks: { callback: moneyTick } } } },
    })
    return () => chart.destroy()
  }, [data, trendScale])

  // Category spend as % of compensation.
  useEffect(() => {
    if (!compRef.current || !data.top_expense_categories.length) return
    const palette = getChartPalette()
    const { red, accent, green, amber } = palette
    const catColors = [red, amber, accent, green, '#a78bfa', '#38bdf8', '#fb923c', '#34d399']
    const comp = parseFloat(data.compensation_income)
    const pcts = data.top_expense_categories.map((d) => comp > 0 ? (parseFloat(d.amount) / comp) * 100 : 0)
    const chart = new Chart<'bar'>(compRef.current, {
      type: 'bar',
      data: { labels: data.top_expense_categories.map((d) => d.category), datasets: [{ label: '% of salary + bonus', data: pcts, backgroundColor: data.top_expense_categories.map((_, i) => catColors[i % catColors.length] + 'bb'), borderColor: data.top_expense_categories.map((_, i) => catColors[i % catColors.length]), borderWidth: 1, borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => { const idx = ctx.dataIndex; const amt = parseFloat(data.top_expense_categories[idx].amount); return ` ${(ctx.parsed.y ?? 0).toFixed(1)}% · $${amt.toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: (v) => `${Number(v).toFixed(0)}%` }, grace: '10%' } } },
    })
    return () => chart.destroy()
  }, [data])

  const bars = data.period_bars
  const comp = parseFloat(data.compensation_income)
  const lifestyle = parseFloat(data.lifestyle_expenses)
  const lifestylePct = comp !== 0 ? (lifestyle / comp) * 100 : 0
  const totalExp = parseFloat(data.total_expenses)
  const totalInc = parseFloat(data.total_income)
  const avgExpPerPeriod = data.period_count > 0 ? totalExp / data.period_count : 0
  const expToIncomePct = totalInc > 0 ? (totalExp / totalInc) * 100 : 0
  const lastBarData = bars[bars.length - 1]
  const prevBarData = bars[bars.length - 2]
  const periodDeltaPct = prevBarData && lastBarData && prevBarData.expenses ? ((parseFloat(lastBarData.expenses) - parseFloat(prevBarData.expenses)) / parseFloat(prevBarData.expenses)) * 100 : null
  const expenseCatColors = ['var(--red)', 'var(--amber)', 'var(--accent)', 'var(--green)', 'var(--purple)', 'var(--pink)', '#38bdf8', '#fb923c']
  const expenseRingData = data.top_expense_categories.slice(0, 8).map((d, i) => ({
    amount: parseFloat(d.amount),
    color: expenseCatColors[i % expenseCatColors.length],
    name: d.category,
  }))

  return (
    <>
      <div className="hero hero--expenses count-anim mb-4">
        <div className="stack gap-2" style={{ justifyContent: 'space-between' }}>
          <div>
            <div className="hero-eyebrow">Total Expenses · {scopeLabel}</div>
            <div className="hero-number">{fmtMoney(data.total_expenses)}</div>
            <div className="hero-delta">
              <SvgIcon name={periodDeltaPct != null && periodDeltaPct < 0 ? 'trend-down' : 'trend-up'} size={14} />
              {periodDeltaPct != null ? `${periodDeltaPct >= 0 ? '+' : ''}${periodDeltaPct.toFixed(1)}% vs prior period` : 'No prior period data'}
            </div>
          </div>
          <div className="hero-stats">
            <div className="hero-stat">
              <div className="hero-stat-label">Lifestyle Rate</div>
              <div className="hero-stat-value">{lifestylePct.toFixed(1)}%</div>
            </div>
            <div className="hero-stat">
              <div className="hero-stat-label">Exp / Income</div>
              <div className="hero-stat-value">{expToIncomePct.toFixed(1)}%</div>
            </div>
            <div className="hero-stat">
              <div className="hero-stat-label">Avg / Period</div>
              <div className="hero-stat-value">{fmtMoney(String(avgExpPerPeriod))}</div>
            </div>
          </div>
        </div>
        <div style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column' }}>
          <HeroSparkline data={bars.map((b) => parseFloat(b.expenses))} labels={bars.map((b) => b.period_label)} />
        </div>
      </div>
      <div className="grid grid-12">
        <div className="card col-7">
          <div className="card-hd">
            <div>
              <div className="card-title">Expense Mix</div>
              <div className="card-sub">{fmtMoney(data.total_expenses)} across {data.top_expense_categories.length} categories</div>
            </div>
            <span className="badge badge--ghost">{scopeLabel}</span>
          </div>
          <div className="card-bd">
            {data.top_expense_categories.length ? (
              <div className="ring-wrap">
                <RingChart
                  data={expenseRingData}
                  size={200}
                  centerLabel="Total"
                  centerValue={<span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{fmtMoney(data.total_expenses)}</span>}
                />
                <div className="legend">
                  {expenseRingData.map((d, i) => {
                    const pct = totalExp > 0 ? (d.amount / totalExp) * 100 : 0
                    return (
                      <div key={i} className="legend-row">
                        <span className="legend-swatch" style={{ background: d.color }} />
                        <span>{d.name}</span>
                        <span className="legend-pct">{fmtMoney(String(d.amount))} · {pct.toFixed(0)}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : <EmptyState message="No expenses yet." />}
          </div>
        </div>
        <div className="card col-5">
          <div className="card-hd">
            <div><div className="card-title">Expense Trendlines</div><div className="card-sub">by sub-category</div></div>
            <div className="row gap-2">
              <button className={`btn btn-sm ${trendScale === 'all' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTrendScale('all')}>All</button>
              <button className={`btn btn-sm ${trendScale === 'under1k' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTrendScale('under1k')}>Under $1k</button>
            </div>
          </div>
          <div className="card-bd">{data.expense_category_series.length ? <div style={{ height: 200 }}><canvas ref={stackRef} /></div> : <EmptyState message="No expenses yet." />}</div>
        </div>
      </div>
      <div className="card mt-4">
        <div className="card-hd"><div><div className="card-title">Category Spend vs Compensation</div><div className="card-sub">each category as % of salary + bonus</div></div></div>
        <div className="card-bd">{data.top_expense_categories.length && parseFloat(data.compensation_income) > 0 ? <div style={{ height: 170 }}><canvas ref={compRef} /></div> : <EmptyState message="No data yet." hint="Needs both expenses and compensation income." />}</div>
      </div>
    </>
  )
}
