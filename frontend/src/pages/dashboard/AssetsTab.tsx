import { useEffect, useRef } from 'react'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import Sparkline from '../../components/Sparkline'
import RingChart from '../../components/RingChart'
import { fmtMoney } from '../../utils/format'
import { getChartPalette, moneyTick } from './chartTheme'
import type { DashboardTabProps } from './constants'

export default function AssetsTab({ data, scopeLabel }: DashboardTabProps) {
  const assetStackRef = useRef<HTMLCanvasElement>(null)

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
    const datasets = subCategories.map((sc) => { const color = colorOf(sc); return { label: sc, data: periodLabels.map((pl) => seriesByKey.get(`${pl}|${sc}`) ?? 0), backgroundColor: color + 'cc', borderColor: color, borderWidth: 1, borderRadius: 2 } })
    const chart = new Chart(assetStackRef.current, { type: 'bar', data: { labels: periodLabels, datasets }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.dataset.label}: $${(ctx.parsed.y ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}` } } }, scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, ticks: { callback: moneyTick } } } } })
    return () => chart.destroy()
  }, [data])

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
    </>
  )
}
