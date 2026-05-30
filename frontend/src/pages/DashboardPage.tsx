import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  Chart,
  BarElement, LineElement, PointElement, ArcElement,
  BarController, LineController, DoughnutController,
  CategoryScale, LinearScale,
  Tooltip, Legend, Filler,
} from 'chart.js'
import { fetchDashboard } from '../api/dashboard'
import { fetchPeriods } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import Sparkline from '../components/Sparkline'
import RingChart from '../components/RingChart'
import { fmtMoney } from '../utils/format'

Chart.register(BarElement, LineElement, PointElement, ArcElement, BarController, LineController, DoughnutController, CategoryScale, LinearScale, Tooltip, Legend, Filler)

type DashboardTab = 'overview' | 'expenses' | 'assets' | 'forecast'

// `null` selected year means "All Years".
const ALL_YEARS = null

export default function DashboardPage() {
  const [selectedYear, setSelectedYear] = useState<number | null>(ALL_YEARS)
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview')
  const [trendScale, setTrendScale] = useState<'all' | 'under1k'>('all')

  const initialised = useRef(false)
  const queryClient = useQueryClient()
  const { data: allPeriods } = useQuery({ queryKey: ['periods'], queryFn: fetchPeriods, staleTime: 60_000 })
  const closedPeriods = useMemo(() => (allPeriods ?? []).filter((p) => p.status === 'closed'), [allPeriods])

  // Years with at least one closed period, newest first.
  const availableYears = useMemo(
    () => [...new Set(closedPeriods.map((p) => Number(p.period_start.slice(0, 4))))].sort((a, b) => b - a),
    [closedPeriods],
  )

  // Default to the current year if it has data, else the most recent year, else All Years.
  useEffect(() => {
    if (initialised.current || availableYears.length === 0) return
    initialised.current = true
    const currentYear = new Date().getFullYear()
    setSelectedYear(availableYears.includes(currentYear) ? currentYear : availableYears[0])
  }, [availableYears])

  const scopeLabel = selectedYear == null ? 'All Years' : String(selectedYear)

  const DASHBOARD_STALE_TIME = 5 * 60_000

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['dashboard', selectedYear],
    queryFn: () => fetchDashboard(selectedYear ?? undefined),
    staleTime: DASHBOARD_STALE_TIME,
    placeholderData: keepPreviousData,
  })

  // Warm the cache for every other filter option in the background so switching
  // years is instant (mirrors the iOS dashboard's prefetchOthers()).
  useEffect(() => {
    if (availableYears.length === 0) return
    const options: (number | null)[] = [...availableYears, ALL_YEARS]
    for (const year of options) {
      if (year === selectedYear) continue
      queryClient.prefetchQuery({
        queryKey: ['dashboard', year],
        queryFn: () => fetchDashboard(year ?? undefined),
        staleTime: DASHBOARD_STALE_TIME,
      })
    }
  }, [availableYears, selectedYear, queryClient])

  const forecast = useMemo(() => {
    if (!data?.net_worth_series?.length) return null
    const histVals = data.net_worth_series.map((p) => parseFloat(p.net_worth))
    const n = histVals.length
    const lastNw = histVals[n - 1]
    const lastLabel = data.net_worth_series[n - 1].period_label
    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    const parseLabel = (label: string): [number, number] | null => {
      const dash = label.match(/^(\d{4})-(\d{2})$/)
      if (dash) return [parseInt(dash[1], 10), parseInt(dash[2], 10)]
      const space = label.match(/^([A-Z][a-z]{2}) (\d{4})$/)
      if (space) { const idx = monthNames.indexOf(space[1]); if (idx >= 0) return [parseInt(space[2], 10), idx + 1] }
      return null
    }
    const parsed = parseLabel(lastLabel)
    if (!parsed) return null
    const [ly, lm] = parsed
    const targetYear = 2026
    const monthsRemaining = Math.max(0, (targetYear - ly) * 12 + (12 - lm))
    const bars = data.period_bars.slice(-12)
    const avgMonthlyNet = bars.length ? bars.reduce((s, b) => s + parseFloat(b.net), 0) / bars.length : 0
    const trailingFuture = Array.from({ length: monthsRemaining }, (_, k) => lastNw + (k + 1) * avgMonthlyNet)
    const eoy = trailingFuture[trailingFuture.length - 1] ?? lastNw
    return { avgMonthlyNet, currentNw: lastNw, trailingEoy: eoy, monthsRemaining }
  }, [data])

  // Chart.js refs for complex charts
  const ieRef = useRef<HTMLCanvasElement>(null)
  const ecRef = useRef<HTMLCanvasElement>(null)
  const stackRef = useRef<HTMLCanvasElement>(null)
  const compRef = useRef<HTMLCanvasElement>(null)
  const assetStackRef = useRef<HTMLCanvasElement>(null)
  const forecastRef = useRef<HTMLCanvasElement>(null)
  const chartRefs = useRef<Chart[]>([])
  const trendChartRef = useRef<Chart | null>(null)
  const assetChartsRef = useRef<Chart[]>([])
  const forecastChartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!data) return
    chartRefs.current.forEach((c) => c.destroy())
    chartRefs.current = []
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
    const text3  = isDark ? '#5e6a82' : '#7a8499'
    const border = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(8,15,30,0.07)'
    const green  = isDark ? '#4ade80' : '#16a34a'
    const red    = isDark ? '#fb7185' : '#dc2626'
    const accent = isDark ? '#56c8f0' : '#0284c7'
    const amber  = isDark ? '#fbbf24' : '#b45309'

    Chart.defaults.color = text3
    Chart.defaults.borderColor = border
    Chart.defaults.font.family = "'Inter', sans-serif"
    Chart.defaults.font.size = 12

    const moneyTick = (v: number | string) => `$${Number(v).toLocaleString()}`
    const moneyTip  = (ctx: { parsed: { y?: number | null; x?: number | null } }) => {
      const n = ctx.parsed.y ?? ctx.parsed.x ?? 0
      return ` $${n.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
    }

    if (ieRef.current && data.period_bars.length) {
      chartRefs.current.push(new Chart(ieRef.current, {
        type: 'bar',
        data: {
          labels: data.period_bars.map((d) => d.period_label),
          datasets: [
            { label: 'Income', data: data.period_bars.map((d) => parseFloat(d.income)), backgroundColor: green + '99', borderColor: green, borderWidth: 1, borderRadius: 4 },
            { label: 'Expenses', data: data.period_bars.map((d) => parseFloat(d.expenses)), backgroundColor: red + '99', borderColor: red, borderWidth: 1, borderRadius: 4 },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', labels: { boxWidth: 12, padding: 16 } }, tooltip: { callbacks: { label: moneyTip } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick } } } },
      }))
    }

    const catColors = [red, amber, accent, green, '#a78bfa', '#38bdf8', '#fb923c', '#34d399']

    if (ecRef.current && data.top_expense_categories.length) {
      chartRefs.current.push(new Chart(ecRef.current, {
        type: 'bar',
        data: {
          labels: data.top_expense_categories.map((d) => d.category),
          datasets: [{ label: 'Expenses', data: data.top_expense_categories.map((d) => parseFloat(d.amount)), backgroundColor: catColors.map((c) => c + 'bb'), borderColor: catColors, borderWidth: 1, borderRadius: 4 }],
        },
        options: { indexAxis: 'y', responsive: true, maintainAspectRatio: true, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ` $${(ctx.parsed.x ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { ticks: { callback: moneyTick } }, y: { grid: { display: false } } } },
      }))
    }

    if (compRef.current && data.top_expense_categories.length) {
      const comp = parseFloat(data.compensation_income)
      const pcts = data.top_expense_categories.map((d) => comp > 0 ? (parseFloat(d.amount) / comp) * 100 : 0)
      chartRefs.current.push(new Chart<'bar'>(compRef.current, {
        type: 'bar',
        data: { labels: data.top_expense_categories.map((d) => d.category), datasets: [{ label: '% of salary + bonus', data: pcts, backgroundColor: data.top_expense_categories.map((_, i) => catColors[i % catColors.length] + 'bb'), borderColor: data.top_expense_categories.map((_, i) => catColors[i % catColors.length]), borderWidth: 1, borderRadius: 4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => { const idx = ctx.dataIndex; const amt = parseFloat(data.top_expense_categories[idx].amount); return ` ${(ctx.parsed.y ?? 0).toFixed(1)}% · $${amt.toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: (v) => `${Number(v).toFixed(0)}%` }, grace: '10%' } } },
      }))
    }

    return () => { chartRefs.current.forEach((c) => c.destroy()); chartRefs.current = [] }
  }, [data, activeTab])

  useEffect(() => {
    if (!data || activeTab !== 'expenses') return
    if (!stackRef.current || !data.expense_category_series.length) return
    trendChartRef.current?.destroy()
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
    const red = isDark ? '#fb7185' : '#dc2626'; const accent = isDark ? '#56c8f0' : '#0284c7'; const green = isDark ? '#4ade80' : '#16a34a'; const amber = isDark ? '#fbbf24' : '#b45309'
    const catColors = [red, amber, accent, green, '#a78bfa', '#38bdf8', '#fb923c', '#34d399']
    // Stable map keyed by top_expense_categories order — same order used by donut + comp charts
    const stableCatMap = new Map<string, string>(
      data.top_expense_categories.map((d, i) => [d.category, catColors[i % catColors.length]])
    )
    const colorOf = (cat: string, fallbackIdx: number) =>
      stableCatMap.get(cat) ?? catColors[(data.top_expense_categories.length + fallbackIdx) % catColors.length]
    const moneyTick = (v: number | string) => `$${Number(v).toLocaleString()}`
    const periodLabels = [...new Set(data.expense_category_series.map((p) => p.period_label))]
    const allCategories = [...new Set(data.expense_category_series.map((p) => p.category))]
    const seriesByKey = new Map<string, number>()
    for (const row of data.expense_category_series) seriesByKey.set(`${row.period_label}|${row.category}`, parseFloat(row.amount))
    const extraCategories = allCategories.filter((c) => !stableCatMap.has(c))
    const categories = trendScale === 'under1k' ? allCategories.filter((cat) => Math.max(...periodLabels.map((pl) => seriesByKey.get(`${pl}|${cat}`) ?? 0)) < 1000) : allCategories
    const datasets = categories.map((cat) => {
      const color = colorOf(cat, extraCategories.indexOf(cat))
      return { label: cat, data: periodLabels.map((pl) => seriesByKey.get(`${pl}|${cat}`) ?? 0), borderColor: color, backgroundColor: color, borderWidth: 1.5, pointRadius: 2, fill: false, tension: 0.3 }
    })
    trendChartRef.current = new Chart(stackRef.current, {
      type: 'line',
      data: { labels: periodLabels, datasets },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick } } } },
    })
    return () => { trendChartRef.current?.destroy(); trendChartRef.current = null }
  }, [data, activeTab, trendScale])

  useEffect(() => {
    if (!data || activeTab !== 'assets') return
    assetChartsRef.current.forEach((c) => c.destroy()); assetChartsRef.current = []
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
    const green = isDark ? '#4ade80' : '#16a34a'; const accent = isDark ? '#56c8f0' : '#0284c7'; const amber = isDark ? '#fbbf24' : '#b45309'
    const purple = isDark ? '#a78bfa' : '#7c3aed'; const pink = isDark ? '#f472b6' : '#db2777'
    const catColors = [accent, green, amber, purple, '#38bdf8', pink, '#fb923c', '#34d399']
    const moneyTick = (v: number | string) => `$${Number(v).toLocaleString()}`
    const periodLabels = [...new Set(data.asset_series.map((p) => p.period_label))]
    const subCategories = [...new Set(data.asset_series.map((p) => p.sub_category))]
    const seriesByKey = new Map<string, number>()
    for (const row of data.asset_series) seriesByKey.set(`${row.period_label}|${row.sub_category}`, parseFloat(row.amount))
    const subCatColor = new Map<string, string>(data.asset_composition.map((d, i) => [d.sub_category, catColors[i % catColors.length]]))
    const colorOf = (sc: string) => subCatColor.get(sc) ?? catColors[0]

    if (assetStackRef.current && periodLabels.length && subCategories.length) {
      const datasets = subCategories.map((sc) => { const color = colorOf(sc); return { label: sc, data: periodLabels.map((pl) => seriesByKey.get(`${pl}|${sc}`) ?? 0), backgroundColor: color + 'cc', borderColor: color, borderWidth: 1, borderRadius: 2 } })
      assetChartsRef.current.push(new Chart(assetStackRef.current, { type: 'bar', data: { labels: periodLabels, datasets }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: moneyTick } } } } }))
    }

    return () => { assetChartsRef.current.forEach((c) => c.destroy()); assetChartsRef.current = [] }
  }, [data, activeTab])

  useEffect(() => {
    if (!data || activeTab !== 'forecast' || !forecast || !forecastRef.current) return
    forecastChartRef.current?.destroy()
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
    const accent = isDark ? '#56c8f0' : '#0284c7'; const green = isDark ? '#4ade80' : '#16a34a'; const red = isDark ? '#fb7185' : '#dc2626'
    const moneyTick = (v: number | string) => `$${Number(v).toLocaleString()}`
    const histVals = data.net_worth_series.map((p) => parseFloat(p.net_worth))
    const n = histVals.length
    const lastNw = histVals[n - 1]
    const avgMonthlyNet = forecast.avgMonthlyNet
    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    const lastLabel = data.net_worth_series[n - 1].period_label
    const space = lastLabel.match(/^([A-Z][a-z]{2}) (\d{4})$/)
    const [ly, lm] = space ? [parseInt(space[2], 10), monthNames.indexOf(space[1]) + 1] : [2026, 12]
    const monthsRemaining = Math.max(0, (2026 - ly) * 12 + (12 - lm))
    const histLabels = data.net_worth_series.map((p) => p.period_label)
    const futureLabels: string[] = []
    for (let k = 1; k <= monthsRemaining; k++) { const total = lm + k; const year = ly + Math.floor((total - 1) / 12); const month = ((total - 1) % 12) + 1; futureLabels.push(`${monthNames[month - 1]} ${year}`) }
    const trailingFuture = Array.from({ length: monthsRemaining }, (_, k) => lastNw + (k + 1) * avgMonthlyNet)
    const labels = [...histLabels, ...futureLabels]
    const historical: (number | null)[] = [...histVals, ...futureLabels.map(() => null)]
    const padNulls = histLabels.slice(0, -1).map(() => null) as (number | null)[]
    const trailingProjection: (number | null)[] = [...padNulls, lastNw, ...trailingFuture]
    const projColor = avgMonthlyNet >= 0 ? green : red

    forecastChartRef.current = new Chart(forecastRef.current, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Historical', data: historical, borderColor: accent, backgroundColor: accent, borderWidth: 2, pointRadius: 3, pointBackgroundColor: accent, tension: 0.3, spanGaps: false },
          { label: 'Trailing-avg projection', data: trailingProjection, borderColor: projColor, backgroundColor: projColor, borderWidth: 2, borderDash: [6, 4], pointRadius: 2, pointBackgroundColor: projColor, tension: 0, spanGaps: false },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick } } } },
    })
    return () => { forecastChartRef.current?.destroy(); forecastChartRef.current = null }
  }, [data, activeTab, forecast])

  if (isLoading && !data) return <Layout><p className="muted">Loading…</p></Layout>
  if (error || !data) return <Layout><p className="color-red">Failed to load dashboard.</p></Layout>

  // Hero data
  const nwSeries = data.net_worth_series.map((p) => parseFloat(p.net_worth))
  const nwLabels = data.net_worth_series.map((p) => p.period_label)
  const currentNw = parseFloat(data.net_worth)
  const yoyDelta = nwSeries.length > 1 ? currentNw - nwSeries[0] : 0
  const yoyPct = nwSeries.length > 1 && nwSeries[0] ? (yoyDelta / nwSeries[0]) * 100 : 0

  const bars = data.period_bars
  const compensation = parseFloat(data.compensation_income)
  const savingsContribs = parseFloat(data.retirement_contributions)
  const savingsRate = compensation > 0 ? (savingsContribs / compensation) * 100 : 0
  const lastBar = bars[bars.length - 1]
  const lastMonthNwDelta = nwSeries.length >= 2 ? nwSeries[nwSeries.length - 1] - nwSeries[nwSeries.length - 2] : null
  const totalLiabilities = parseFloat(data.total_assets) - currentNw
  const debtToEquity = currentNw !== 0 ? totalLiabilities / currentNw : null


  // Asset composition for ring chart
  const composition = data.asset_composition
  const totalAssets = parseFloat(data.total_assets)
  const assetColors = ['var(--accent)', 'var(--green)', 'var(--amber)', 'var(--purple)', '#38bdf8', 'var(--pink)', '#fb923c', '#34d399']
  const ringData = composition.slice(0, 6).map((d, i) => ({ amount: parseFloat(d.amount), color: assetColors[i % assetColors.length], name: d.sub_category }))

  // Retirement ring — progress toward 2026 annual contribution limits
  const CONTRIB_LIMIT_401K = 24_500
  const CONTRIB_LIMIT_IRA  = 7_500
  const CONTRIB_LIMIT_HSA  = 4_400
  const CONTRIB_LIMIT_TOTAL = CONTRIB_LIMIT_401K + CONTRIB_LIMIT_IRA + CONTRIB_LIMIT_HSA

  function accountLimit(name: string): number {
    const n = name.toLowerCase()
    if (n.includes('401')) return CONTRIB_LIMIT_401K
    if (n.includes('ira'))  return CONTRIB_LIMIT_IRA
    if (n.includes('hsa'))  return CONTRIB_LIMIT_HSA
    return 0
  }

  const retirementContribs = data.ytd_retirement_contributions ?? []
  const retirementTotal = retirementContribs.reduce((s, c) => s + Math.max(0, parseFloat(c.amount)), 0)
  const retirementPct = (retirementTotal / CONTRIB_LIMIT_TOTAL) * 100

  return (
    <Layout activePeriod={data.active_period}>
      <div className="page">
        <PageHeader
          eyebrow="Overview"
          title="Welcome back"
          subtitle={`Financial snapshot · ${data.period_count} period${data.period_count !== 1 ? 's' : ''} tracked`}
          actions={
            <div className="row gap-2 wrap">
              <div className="seg">
                <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>Overview</button>
                <button className={activeTab === 'expenses' ? 'active' : ''} onClick={() => setActiveTab('expenses')}>Expenses</button>
                <button className={activeTab === 'assets' ? 'active' : ''} onClick={() => setActiveTab('assets')}>Assets</button>
                <button className={activeTab === 'forecast' ? 'active' : ''} onClick={() => setActiveTab('forecast')}>Forecast</button>
              </div>
              {availableYears.length > 0 && (
                <div className="row gap-2">
                  <SvgIcon name="periods" size={14} />
                  <select
                    className="inp inp-fit"
                    style={{ minWidth: 120 }}
                    value={selectedYear == null ? 'all' : String(selectedYear)}
                    onChange={(e) => setSelectedYear(e.target.value === 'all' ? null : Number(e.target.value))}
                  >
                    {availableYears.map((y) => <option key={y} value={y}>{y}</option>)}
                    <option value="all">All Years</option>
                  </select>
                  {isFetching && <span className="muted" style={{ fontSize: 12 }}>Updating…</span>}
                </div>
              )}
            </div>
          }
        />

        {!data.has_data && !data.active_period ? (
          <div className="card">
            <EmptyState icon="periods" message="No open period yet." hint="Create a period to start tracking your finances.">
              <Link to="/periods" className="btn btn-primary" style={{ marginTop: 8 }}>Go to Workflow</Link>
            </EmptyState>
          </div>
        ) : (
          <>
            {/* ── Overview tab ── */}
            {activeTab === 'overview' && (
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
                      <Sparkline data={nwSeries} labels={nwLabels} showAxes fillContainer color="white" fill="rgba(255,255,255,0.22)" strokeWidth={2.2} />
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
                            <div className="card-sub">2026 contribution limits</div>
                          </div>
                          <span className="badge badge--accent"><span className="badge-dot" />On track</span>
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

                {/* Income vs Expenses + Active period */}
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
            )}

            {/* ── Expenses tab ── */}
            {activeTab === 'expenses' && (() => {
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
                      <Sparkline data={bars.map((b) => parseFloat(b.expenses))} labels={bars.map((b) => b.period_label)} showAxes fillContainer color="white" fill="rgba(255,255,255,0.22)" strokeWidth={2.2} />
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
            })()}

            {/* ── Assets tab ── */}
            {activeTab === 'assets' && (() => {
              const totalAssetsCurr = parseFloat(data.total_assets)
              const totalAssetsPrev = parseFloat(data.total_assets_prev)
              const totalAssetsDelta = totalAssetsCurr - totalAssetsPrev
              const hasTotalAssetsPrev = totalAssetsPrev !== 0
              const periodLabels = [...new Set(data.asset_series.map((p) => p.period_label))]
              const assetSubCats = [...new Set(data.asset_series.map((p) => p.sub_category))]
              const assetSeriesKey = new Map<string, number>(data.asset_series.map((row) => [`${row.period_label}|${row.sub_category}`, parseFloat(row.amount)]))
              const assetTotals = periodLabels.map((pl) => assetSubCats.reduce((acc, sc) => acc + (assetSeriesKey.get(`${pl}|${sc}`) ?? 0), 0))
              const ytdAssetDelta = assetTotals.length > 1 ? totalAssetsCurr - assetTotals[0] : null
              const ytdAssetPct = ytdAssetDelta != null && assetTotals[0] ? (ytdAssetDelta / assetTotals[0]) * 100 : null
              return (
                <>
                  <div className="hero hero--assets count-anim mb-4">
                    <div className="stack gap-2" style={{ justifyContent: 'space-between' }}>
                      <div>
                        <div className="hero-eyebrow">Total Assets · {scopeLabel}</div>
                        <div className="hero-number">{fmtMoney(data.total_assets)}</div>
                        <div className="hero-delta">
                          {ytdAssetDelta != null && ytdAssetPct != null ? (
                            <>
                              <SvgIcon name={ytdAssetDelta >= 0 ? 'trend-up' : 'trend-down'} size={14} />
                              {ytdAssetDelta >= 0 ? '+' : ''}{fmtMoney(String(ytdAssetDelta))} ({ytdAssetPct >= 0 ? '+' : ''}{ytdAssetPct.toFixed(1)}%) · YTD
                            </>
                          ) : (
                            <span style={{ opacity: 0.8 }}>{scopeLabel}</span>
                          )}
                        </div>
                      </div>
                      <div className="hero-stats">
                        <div className="hero-stat">
                          <div className="hero-stat-label">This month</div>
                          <div className="hero-stat-value">{hasTotalAssetsPrev ? `${totalAssetsDelta >= 0 ? '+' : ''}${fmtMoney(String(totalAssetsDelta))}` : '—'}</div>
                        </div>
                        <div className="hero-stat">
                          <div className="hero-stat-label">Tax Advantaged</div>
                          <div className="hero-stat-value">{fmtMoney(data.tax_advantaged)}</div>
                        </div>
                        <div className="hero-stat">
                          <div className="hero-stat-label">Liquid</div>
                          <div className="hero-stat-value">{fmtMoney(data.liquid_assets)}</div>
                        </div>
                      </div>
                    </div>
                    <div style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column' }}>
                      <Sparkline data={assetTotals.length ? assetTotals : [totalAssetsCurr]} labels={periodLabels.length ? periodLabels : undefined} showAxes fillContainer color="white" fill="rgba(255,255,255,0.22)" strokeWidth={2.2} />
                    </div>
                  </div>
                  <div className="grid grid-12">
                    <div className="card col-7">
                      <div className="card-hd">
                        <div>
                          <div className="card-title">Asset Mix</div>
                          <div className="card-sub">{fmtMoney(data.total_assets)} across {composition.length} buckets</div>
                        </div>
                        <span className="badge badge--ghost">{scopeLabel}</span>
                      </div>
                      <div className="card-bd">
                        {composition.length ? (
                          <div className="ring-wrap">
                            <RingChart
                              data={ringData}
                              size={200}
                              centerLabel="Total"
                              centerValue={<span className="mono" style={{ fontSize: 22, fontWeight: 600 }}>{fmtMoney(data.total_assets)}</span>}
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
                        ) : <EmptyState message="No assets yet." />}
                      </div>
                    </div>
                    <div className="card col-5">
                      <div className="card-hd"><div><div className="card-title">Composition Over Time</div><div className="card-sub">by sub-category</div></div></div>
                      <div className="card-bd">{data.asset_series.length ? <div style={{ height: 240 }}><canvas ref={assetStackRef} /></div> : <EmptyState message="No asset data yet." />}</div>
                    </div>
                  </div>
                </>
              )
            })()}

            {/* ── Forecast tab ── */}
            {activeTab === 'forecast' && (
              !forecast ? (
                <div className="card"><EmptyState message="Not enough data to forecast." hint="Close at least one period to enable a projection." /></div>
              ) : (() => {
                const gain = forecast.trailingEoy - forecast.currentNw
                const gainPct = forecast.currentNw !== 0 ? (gain / forecast.currentNw) * 100 : 0
                return (
                  <>
                    <div className="hero hero--forecast count-anim mb-4">
                      <div className="stack gap-2" style={{ justifyContent: 'space-between' }}>
                        <div>
                          <div className="hero-eyebrow">Projected Net Worth · {scopeLabel}</div>
                          <div className="hero-number">{fmtMoney(String(forecast.trailingEoy))}</div>
                          <div className="hero-delta">
                            <SvgIcon name={gain >= 0 ? 'trending' : 'trend-down'} size={14} />
                            {gain >= 0 ? '+' : ''}{fmtMoney(String(gain))} ({gainPct >= 0 ? '+' : ''}{gainPct.toFixed(1)}%) · EOY 2026
                          </div>
                        </div>
                        <div className="hero-stats">
                          <div className="hero-stat">
                            <div className="hero-stat-label">Current NW</div>
                            <div className="hero-stat-value">{fmtMoney(String(forecast.currentNw))}</div>
                          </div>
                          <div className="hero-stat">
                            <div className="hero-stat-label">Avg Monthly Net</div>
                            <div className="hero-stat-value">{forecast.avgMonthlyNet >= 0 ? '+' : ''}{fmtMoney(String(forecast.avgMonthlyNet))}</div>
                          </div>
                          <div className="hero-stat">
                            <div className="hero-stat-label">Months Remaining</div>
                            <div className="hero-stat-value">{forecast.monthsRemaining}</div>
                          </div>
                        </div>
                      </div>
                      <div style={{ alignSelf: 'stretch', display: 'flex', flexDirection: 'column' }}>
                        <Sparkline data={nwSeries} labels={nwLabels} showAxes fillContainer color="white" fill="rgba(255,255,255,0.22)" strokeWidth={2.2} />
                      </div>
                    </div>
                    <div className="card">
                      <div className="card-hd"><div><div className="card-title">Net Worth Forecast</div><div className="card-sub">historical + projected through Dec 2026</div></div></div>
                      <div className="card-bd"><div style={{ height: 280 }}><canvas ref={forecastRef} /></div></div>
                    </div>
                  </>
                )
              })()
            )}
          </>
        )}
      </div>
    </Layout>
  )
}

