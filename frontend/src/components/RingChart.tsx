import type { ReactNode } from 'react'

interface Segment {
  amount: number
  color: string
  name?: string
}

interface Props {
  data: Segment[]
  size?: number
  thickness?: number
  centerLabel?: string
  centerValue?: ReactNode
  goalPct?: number
}

export default function RingChart({ data, size = 168, thickness = 18, centerLabel, centerValue, goalPct }: Props) {
  const total = data.reduce((s, d) => s + d.amount, 0)
  const r = size / 2 - thickness / 2 - 2
  const c = 2 * Math.PI * r
  let offset = 0

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--line)" strokeWidth={thickness} />
        {data.map((d, i) => {
          const len = total > 0 ? (d.amount / total) * c : 0
          const segOffset = offset
          offset += len
          if (len < 2) return null
          return (
            <circle key={i}
              cx={size/2} cy={size/2} r={r} fill="none"
              stroke={d.color} strokeWidth={thickness}
              strokeDasharray={`${len + 1} ${Math.max(0, c - len - 1)}`}
              strokeDashoffset={-segOffset}
              strokeLinecap="butt"
              transform={`rotate(-90 ${size/2} ${size/2})`}
            />
          )
        })}
        {goalPct !== undefined && (() => {
          const angle = -Math.PI / 2 + (goalPct / 100) * 2 * Math.PI
          const cx = size / 2
          const cy = size / 2
          const outerR = r + thickness / 2 + 4
          const innerR = r - thickness / 2 - 4
          return (
            <line
              x1={cx + outerR * Math.cos(angle)} y1={cy + outerR * Math.sin(angle)}
              x2={cx + innerR * Math.cos(angle)} y2={cy + innerR * Math.sin(angle)}
              stroke="var(--amber)" strokeWidth={2.5} strokeLinecap="round"
            />
          )
        })()}
      </svg>
      {(centerValue || centerLabel) && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          {centerValue && <div className="ring-pct">{centerValue}</div>}
          {centerLabel && <div className="ring-label">{centerLabel}</div>}
        </div>
      )}
    </div>
  )
}
