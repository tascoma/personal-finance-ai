import {
  Chart,
  BarElement, LineElement, PointElement, ArcElement,
  BarController, LineController, DoughnutController,
  CategoryScale, LinearScale,
  Tooltip, Legend, Filler,
} from 'chart.js'

Chart.register(BarElement, LineElement, PointElement, ArcElement, BarController, LineController, DoughnutController, CategoryScale, LinearScale, Tooltip, Legend, Filler)

export interface ChartPalette {
  text3: string
  border: string
  green: string
  red: string
  accent: string
  amber: string
  purple: string
  pink: string
}

/** Resolve the chart palette from the current light/dark theme. */
export function getChartPalette(): ChartPalette {
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
  return {
    text3:  isDark ? '#5e6a82' : '#7a8499',
    border: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(8,15,30,0.07)',
    green:  isDark ? '#4ade80' : '#16a34a',
    red:    isDark ? '#fb7185' : '#dc2626',
    accent: isDark ? '#56c8f0' : '#0284c7',
    amber:  isDark ? '#fbbf24' : '#b45309',
    purple: isDark ? '#a78bfa' : '#7c3aed',
    pink:   isDark ? '#f472b6' : '#db2777',
  }
}

/** Apply the shared Chart.js global defaults (fonts + palette-driven colors). */
export function applyChartDefaults(palette: ChartPalette): void {
  Chart.defaults.color = palette.text3
  Chart.defaults.borderColor = palette.border
  Chart.defaults.font.family = "'Inter', sans-serif"
  Chart.defaults.font.size = 12
}

export const moneyTick = (v: number | string) => `$${Number(v).toLocaleString()}`

export const moneyTip = (ctx: { parsed: { y?: number | null; x?: number | null } }) => {
  const n = ctx.parsed.y ?? ctx.parsed.x ?? 0
  return ` $${n.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
}
