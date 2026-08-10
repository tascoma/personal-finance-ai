import { useEffect, useMemo, useRef } from 'react'
import { Chart } from 'chart.js'
import EmptyState from '../../components/EmptyState'
import SvgIcon from '../../components/SvgIcon'
import HeroSparkline from '../../components/HeroSparkline'
import { fmtMoney } from '../../utils/format'
import { getChartPalette, moneyTick } from './chartTheme'
import { TARGET_YEAR, type DashboardTabProps } from './constants'

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function parseLabel(label: string): [number, number] | null {
  const dash = label.match(/^(\d{4})-(\d{2})$/)
  if (dash) return [parseInt(dash[1], 10), parseInt(dash[2], 10)]
  const space = label.match(/^([A-Z][a-z]{2}) (\d{4})$/)
  if (space) {
    const idx = MONTH_NAMES.indexOf(space[1])
    if (idx >= 0) return [parseInt(space[2], 10), idx + 1]
  }
  return null
}

export default function ForecastTab({ data, scopeLabel }: DashboardTabProps) {
  const forecastRef = useRef<HTMLCanvasElement>(null)

  const forecast = useMemo(() => {
    if (!data.net_worth_series?.length) return null
    const histVals = data.net_worth_series.map((p) => parseFloat(p.net_worth))
    const n = histVals.length
    const lastNw = histVals[n - 1]
    const lastLabel = data.net_worth_series[n - 1].period_label
    const parsed = parseLabel(lastLabel)
    if (!parsed) return null
    const [ly, lm] = parsed
    const monthsRemaining = Math.max(0, (TARGET_YEAR - ly) * 12 + (12 - lm))
    const bars = data.period_bars.slice(-12)
    const avgMonthlyNet = bars.length ? bars.reduce((s, b) => s + parseFloat(b.net), 0) / bars.length : 0
    const trailingFuture = Array.from({ length: monthsRemaining }, (_, k) => lastNw + (k + 1) * avgMonthlyNet)
    const eoy = trailingFuture[trailingFuture.length - 1] ?? lastNw
    return { avgMonthlyNet, currentNw: lastNw, trailingEoy: eoy, monthsRemaining, ly, lm }
  }, [data])

  useEffect(() => {
    if (!forecast || !forecastRef.current) return
    const palette = getChartPalette()
    const { accent, green, red } = palette
    const histVals = data.net_worth_series.map((p) => parseFloat(p.net_worth))
    const n = histVals.length
    const lastNw = histVals[n - 1]
    const avgMonthlyNet = forecast.avgMonthlyNet
    // Reuse the memo's parse rather than re-deriving it: a second, weaker copy
    // here handled only "Mon YYYY" and fell back to monthsRemaining = 0 for
    // "YYYY-MM" labels, so the hero showed an EOY projection that the chart
    // below drew zero future points for.
    const { ly, lm, monthsRemaining } = forecast
    const histLabels = data.net_worth_series.map((p) => p.period_label)
    const futureLabels: string[] = []
    for (let k = 1; k <= monthsRemaining; k++) { const total = lm + k; const year = ly + Math.floor((total - 1) / 12); const month = ((total - 1) % 12) + 1; futureLabels.push(`${MONTH_NAMES[month - 1]} ${year}`) }
    const trailingFuture = Array.from({ length: monthsRemaining }, (_, k) => lastNw + (k + 1) * avgMonthlyNet)
    const labels = [...histLabels, ...futureLabels]
    const historical: (number | null)[] = [...histVals, ...futureLabels.map(() => null)]
    const padNulls = histLabels.slice(0, -1).map(() => null) as (number | null)[]
    const trailingProjection: (number | null)[] = [...padNulls, lastNw, ...trailingFuture]
    const projColor = avgMonthlyNet >= 0 ? green : red
    const chart = new Chart(forecastRef.current, {
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
    return () => chart.destroy()
  }, [data, forecast])

  if (!forecast) {
    return <div className="card"><EmptyState message="Not enough data to forecast." hint="Close at least one period to enable a projection." /></div>
  }

  const nwSeries = data.net_worth_series.map((p) => parseFloat(p.net_worth))
  const nwLabels = data.net_worth_series.map((p) => p.period_label)
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
              {gain >= 0 ? '+' : ''}{fmtMoney(String(gain))} ({gainPct >= 0 ? '+' : ''}{gainPct.toFixed(1)}%) · EOY {TARGET_YEAR}
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
          <HeroSparkline data={nwSeries} labels={nwLabels} />
        </div>
      </div>
      <div className="card">
        <div className="card-hd"><div><div className="card-title">Net Worth Forecast</div><div className="card-sub">historical + projected through Dec {TARGET_YEAR}</div></div></div>
        <div className="card-bd"><div style={{ height: 280 }}><canvas ref={forecastRef} /></div></div>
      </div>
    </>
  )
}
