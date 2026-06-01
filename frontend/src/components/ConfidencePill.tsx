interface Props {
  confidence: string | null
}

export default function ConfidencePill({ confidence }: Props) {
  if (confidence === null) return <span className="muted">—</span>
  const pct = parseFloat(confidence)
  const color = pct >= 0.85 ? 'var(--green)' : pct >= 0.7 ? 'var(--amber)' : 'var(--red)'
  return (
    <span className="conf" style={{ color }}>
      {Math.round(pct * 100)}%
      <span className="conf-bar">
        <span className="conf-bar-fill" style={{ width: `${Math.round(pct * 100)}%`, background: color }} />
      </span>
    </span>
  )
}
