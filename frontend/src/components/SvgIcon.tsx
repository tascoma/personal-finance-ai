import type { CSSProperties } from 'react'

interface IconDef {
  path?: string
  paths?: string[]
  fill?: boolean
}

const ICONS: Record<string, IconDef> = {
  dashboard:  { paths: ['M3 3h7v9H3z', 'M14 3h7v5h-7z', 'M14 12h7v9h-7z', 'M3 16h7v5H3z'] },
  periods:    { path: 'M3 4h18a2 2 0 012 2v14a2 2 0 01-2 2H3a2 2 0 01-2-2V6a2 2 0 012-2zM8 2v4M16 2v4M1 10h22' },
  journal:    { path: 'M4 4h12a4 4 0 014 4v12a4 4 0 00-4-4H4zM4 4v16' },
  statements: { path: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 13h8M8 17h5' },
  accounts:   { path: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
  spark:      { path: 'M13 2L3 14h9l-1 8 10-12h-9z' },
  check:      { path: 'M20 6L9 17l-5-5' },
  back:       { path: 'M19 12H5M12 19l-7-7 7-7' },
  arrowLeft:  { path: 'M19 12H5M11 18l-6-6 6-6' },
  arrow:      { path: 'M5 12h14M13 6l6 6-6 6' },
  alert:      { path: 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01' },
  file:       { path: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8' },
  pdf:        { path: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6' },
  csv:        { path: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M9 13h6M9 17h6' },
  plus:       { path: 'M12 5v14M5 12h14' },
  x:          { path: 'M18 6L6 18M6 6l12 12' },
  trash:      { path: 'M3 6h18M8 6V4h8v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6' },
  more:       { paths: ['M12 12m-1 0a1 1 0 102 0 1 1 0 10-2 0', 'M19 12m-1 0a1 1 0 102 0 1 1 0 10-2 0', 'M5 12m-1 0a1 1 0 102 0 1 1 0 10-2 0'], fill: true },
  search:     { path: 'M21 21l-5-5M11 11m-7 0a7 7 0 1014 0 7 7 0 00-14 0' },
  moon:       { path: 'M21 12.79A9 9 0 1111.21 3a7 7 0 009.79 9.79z' },
  sun:        { path: 'M12 3v1M12 20v1M4.22 4.22l.71.71M18.36 18.36l.71.71M1 12h1M20 12h2M4.22 19.78l.71-.71M18.36 5.64l.71-.71M12 8a4 4 0 100 8 4 4 0 000-8z' },
  bell:       { path: 'M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M14 21a2 2 0 01-4 0' },
  trending:   { path: 'M3 17l6-6 4 4 8-8M14 7h7v7' },
  download:   { path: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3' },
  upload:     { path: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12' },
  zap:        { path: 'M13 2L3 14h9l-1 8 10-12h-9z' },
  refresh:    { path: 'M3 12a9 9 0 0115-6.7L21 8M21 3v5h-5M21 12a9 9 0 01-15 6.7L3 16M3 21v-5h5' },
  sparkles:   { path: 'M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1' },
  filter:     { path: 'M3 4h18l-8 10v6l-2 1v-7z' },
  'arrow-right': { path: 'M5 12h14M12 5l7 7-7 7' },
  'chevron-right': { path: 'M9 18l6-6-6-6' },
  'chevron-down': { path: 'M6 9l6 6 6-6' },
  lock:       { path: 'M19 11H5a2 2 0 00-2 2v7a2 2 0 002 2h14a2 2 0 002-2v-7a2 2 0 00-2-2zM7 11V7a5 5 0 0110 0v4' },
  'trend-up': { path: 'M23 6l-9.5 9.5-5-5L1 18M17 6h6v6' },
  'trend-down': { path: 'M23 18l-9.5-9.5-5 5L1 6M17 18h6v-6' },
  menu:       { path: 'M4 6h16M4 12h16M4 18h16' },
  ai:         { path: 'M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4' },
  brain:      { path: 'M9.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 01-4.96-.44 2.5 2.5 0 01-2.96-3.08 3 3 0 01-.34-5.58 2.5 2.5 0 011.32-4.24 2.5 2.5 0 014.44-2.66zM14.5 2A2.5 2.5 0 0012 4.5v15a2.5 2.5 0 004.96-.44 2.5 2.5 0 002.96-3.08 3 3 0 00.34-5.58 2.5 2.5 0 00-1.32-4.24 2.5 2.5 0 00-4.44-2.66z' },
}

interface Props {
  name: string
  size?: number
  className?: string
  style?: CSSProperties
  strokeWidth?: number
}

export default function SvgIcon({ name, size = 16, className, style, strokeWidth = 1.6 }: Props) {
  const def = ICONS[name]
  if (!def) return null
  const isFill = def.fill

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={isFill ? 'currentColor' : 'none'}
      stroke={isFill ? 'none' : 'currentColor'}
      strokeWidth={isFill ? 0 : strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
    >
      {def.path && <path d={def.path} />}
      {def.paths && def.paths.map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}
