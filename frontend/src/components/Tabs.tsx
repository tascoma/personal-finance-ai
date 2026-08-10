interface Tab {
  key: string
  label: string
  count?: number
}

interface Props {
  tabs: Tab[]
  active: string
  onChange: (key: string) => void
  /** Extra classes for the container, e.g. `print-hide`. */
  className?: string
}

export default function Tabs({ tabs, active, onChange, className }: Props) {
  return (
    <div className={className ? `tabs ${className}` : 'tabs'}>
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
