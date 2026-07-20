import { useEffect, useRef, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import Sparkline from '../../components/Sparkline'
import RingChart from '../../components/RingChart'
import { fetchCashflow } from '../../api/statements'
import { fetchPeriods } from '../../api/periods'
import { fmtMoney, fmtPeriod } from '../../utils/format'
import { getChartPalette, moneyTick } from './chartTheme'
import type { DashboardTabProps } from './constants'

interface AssetsTabProps extends DashboardTabProps {
  selectedYear: number | null
}

export default function AssetsTab({ data, scopeLabel, selectedYear }: AssetsTabProps) {
  const assetStackRef = useRef<HTMLCanvasElement>(null)
  const cashflowRef = useRef<HTMLCanvasElement>(null)

  // In-progress periods' numbers aren't final, so cash flow only ever draws from closed periods.
  const [cfMode, setCfMode] = useState<'rolling' | 'aggregate'>('rolling')
  const [cfAnchorId, setCfAnchorId] = useState('')
  const periodsQ = useQuery({ queryKey: ['periods'], queryFn: fetchPeriods, staleTime: 60_000 })
  const closedPeriodsDesc = (periodsQ.data ?? []).filter((p) => p.status === 'closed') // API returns newest-first

  // Aggregate: every closed period within the selected year (or all closed periods for "All Years").
  // Rolling: a 3-period trailing window ending at the chosen anchor period, independent of the year filter.
  const cfPeriods = cfMode === 'aggregate'
    ? closedPeriodsDesc
        .filter((p) => selectedYear == null || p.period_start.startsWith(String(selectedYear)))
        .slice().sort((a, b) => a.period_start.localeCompare(b.period_start))
    : (() => {
        if (!closedPeriodsDesc.length) return []
        const anchorIdx = cfAnchorId ? Math.max(0, closedPeriodsDesc.findIndex((p) => p.period_id === cfAnchorId)) : 0
        return [anchorIdx + 2, anchorIdx + 1, anchorIdx]
          .filter((i) => i >= 0 && i < closedPeriodsDesc.length)
          .map((i) => closedPeriodsDesc[i]) // already oldest-to-newest, ending at the anchor
      })()

  const cfQs = useQueries({
    queries: cfPeriods.map((p) => ({ queryKey: ['cashflow', p.period_id], queryFn: () => fetchCashflow(p.period_id), staleTime: 30_000 })),
  })
  const cfLoading = periodsQ.isLoading || cfQs.some((q) => q.isLoading)
  const cfError = periodsQ.error || cfQs.some((q) => q.error)
  const cfResponses = cfQs.map((q) => q.data).filter((r): r is NonNullable<typeof r> => !!r)

  const cf = cfResponses.length ? {
    beginning_cash: cfResponses[0].beginning_cash,
    ending_cash: cfResponses[cfResponses.length - 1].ending_cash,
    operating_total: String(cfResponses.reduce((s, r) => s + parseFloat(r.operating_total), 0)),
    investing_total: String(cfResponses.reduce((s, r) => s + parseFloat(r.investing_total), 0)),
    financing_total: String(cfResponses.reduce((s, r) => s + parseFloat(r.financing_total), 0)),
    net_change_in_cash: String(cfResponses.reduce((s, r) => s + parseFloat(r.net_change_in_cash), 0)),
  } : null

  useEffect(() => {
    if (!assetStackRef.current || !data.asset_series.length) return
    const palette = getChartPalette()
    const { green, accent, amber, purple, pink } = palette
    const catColors = [accent, green, amber, purple, '#38bdf8', pink, '#fb923c', '#34d399']
    const periodLabels = [...new Set(data.asset_series.map((p) => p.period_label))]
    const subCategories = [...new Set(data.asset_series.map((p) => p.sub_category))]
    if (!periodLabels.length || !subCategories.length) return
    const seriesByKey = new Map<string, number>()
    for (const row of data.asset_series) seriesByKey.set(`${row.period_label}|${row.sub_category}`, parseFloat(row.amount))
    const subCatColor = new Map<string, string>(data.asset_composition.map((d, i) => [d.sub_category, catColors[i % catColors.length]]))
    const colorOf = (sc: string) => subCatColor.get(sc) ?? catColors[0]
    const datasets = subCategories.map((sc) => { const color = colorOf(sc); return { label: sc, data: periodLabels.map((pl) => seriesByKey.get(`${pl}|${sc}`) ?? 0), backgroundColor: color + '99', borderColor: color, borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: color, pointBorderColor: color, fill: true, tension: 0.3 } })
    const chart = new Chart(assetStackRef.current, { type: 'line', data: { labels: periodLabels, datasets }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { grid: { display: false } }, y: { stacked: true, ticks: { callback: moneyTick } } } } })
    return () => chart.destroy()
  }, [data])

  // Cash flow waterfall for the scoped closed periods: Beginning -> Operating -> Investing -> Financing -> Ending.
  useEffect(() => {
    if (!cashflowRef.current || !cf) return
    const palette = getChartPalette()
    const beginning = parseFloat(cf.beginning_cash)
    const operating = parseFloat(cf.operating_total)
    const investing = parseFloat(cf.investing_total)
    const financing = parseFloat(cf.financing_total)
    const ending = parseFloat(cf.ending_cash)
    const afterOperating = beginning + operating
    const afterInvesting = afterOperating + investing
    const afterFinancing = afterInvesting + financing
    const segments = [
      { label: 'Beginning', range: [0, beginning], amount: beginning, isTotal: true },
      { label: '+ Operating', range: [beginning, afterOperating], amount: operating, isTotal: false },
      { label: '+ Investing', range: [afterOperating, afterInvesting], amount: investing, isTotal: false },
      { label: '+ Financing', range: [afterInvesting, afterFinancing], amount: financing, isTotal: false },
      { label: 'Ending', range: [0, ending], amount: ending, isTotal: true },
    ]
    const colorOf = (s: (typeof segments)[number]) => s.isTotal ? palette.accent : s.amount >= 0 ? palette.green : palette.red
    const chart = new Chart(cashflowRef.current, {
      type: 'bar',
      data: {
        labels: segments.map((s) => s.label),
        datasets: [{
          data: segments.map((s) => [Math.min(...s.range), Math.max(...s.range)]),
          backgroundColor: segments.map((s) => colorOf(s) + '99'),
          borderColor: segments.map((s) => colorOf(s)),
          borderWidth: 1.5,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const s = segments[ctx.dataIndex]
                const sign = !s.isTotal && s.amount >= 0 ? '+' : ''
                return ` ${sign}$${s.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
              },
            },
          },
        },
        scales: { x: { grid: { display: false } }, y: { ticks: { callback: moneyTick } } },
      },
    })
    return () => chart.destroy()
  }, [cf])

  const composition = data.asset_composition
  const totalAssets = parseFloat(data.total_assets)
  const assetColors = ['var(--accent)', 'var(--green)', 'var(--amber)', 'var(--purple)', '#38bdf8', 'var(--pink)', '#fb923c', '#34d399']
  const ringData = composition.slice(0, 6).map((d, i) => ({ amount: parseFloat(d.amount), color: assetColors[i % assetColors.length], name: d.sub_category }))

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
      <div className="card mt-4">
        <div className="card-hd">
          <div>
            <div className="card-title">Statement of Cash Flows</div>
            <div className="card-sub">
              {cfPeriods.length
                ? cfPeriods.length === 1
                  ? fmtPeriod(cfPeriods[0].period_start)
                  : `${fmtPeriod(cfPeriods[0].period_start)} – ${fmtPeriod(cfPeriods[cfPeriods.length - 1].period_start)}`
                : 'No closed periods'}
              {cfMode === 'rolling' ? ' · rolling' : ` · aggregate, ${scopeLabel}`}
            </div>
          </div>
          <div className="row gap-3">
            <div className="seg">
              <button className={cfMode === 'rolling' ? 'active' : ''} onClick={() => setCfMode('rolling')}>Rolling 3</button>
              <button className={cfMode === 'aggregate' ? 'active' : ''} onClick={() => setCfMode('aggregate')}>Aggregate</button>
            </div>
            {cfMode === 'rolling' && closedPeriodsDesc.length > 0 && (
              <>
                <span className="muted-2" style={{ fontSize: 13 }}>Ending:</span>
                <select className="inp" style={{ width: 140 }} value={cfAnchorId || closedPeriodsDesc[0].period_id} onChange={(e) => setCfAnchorId(e.target.value)}>
                  {closedPeriodsDesc.map((p) => <option key={p.period_id} value={p.period_id}>{p.period_start.slice(0, 7)}</option>)}
                </select>
              </>
            )}
          </div>
        </div>
        <div className="card-bd">
          {cfLoading ? (
            <EmptyState message="Loading cash flow…" />
          ) : cfError ? (
            <EmptyState message="Couldn't load cash flow data." />
          ) : !cf ? (
            <EmptyState message="No closed periods yet." hint="Cash flow only reflects periods that have been closed." />
          ) : (
            <>
              <div style={{ height: 220 }}><canvas ref={cashflowRef} /></div>
              <div className="row gap-4" style={{ marginTop: 16, flexWrap: 'wrap' }}>
                {[
                  { label: 'Operating', value: parseFloat(cf.operating_total) },
                  { label: 'Investing', value: parseFloat(cf.investing_total) },
                  { label: 'Financing', value: parseFloat(cf.financing_total) },
                  { label: 'Net Change', value: parseFloat(cf.net_change_in_cash) },
                ].map((s) => (
                  <div key={s.label} className="stack gap-1">
                    <span className="muted" style={{ fontSize: 11 }}>{s.label}</span>
                    <span className="mono fw-600" style={{ fontSize: 14, color: s.value >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {s.value >= 0 ? '+' : '-'}{fmtMoney(String(Math.abs(s.value)))}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
