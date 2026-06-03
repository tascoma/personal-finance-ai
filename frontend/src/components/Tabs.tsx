interface Tab {
  key: string
  label: string
  count?: number
}

interface Props {
  tabs: Tab[]
  active: string
  onChange: (key: string) => void
}

export default function Tabs({ tabs, active, onChange }: Props) {
  return (
    <div className="tabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`tab${active === t.key ? ' active' : ''}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="mono muted" style={{ marginLeft: 5, fontSize: 11 }}>
              {t.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
