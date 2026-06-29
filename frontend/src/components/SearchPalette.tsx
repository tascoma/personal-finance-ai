import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import SvgIcon from './SvgIcon'
import { searchGlobal, type SearchHit } from '../api/search'

interface Props {
  onClose: () => void
}

interface PaletteItem {
  key: string
  group: string
  icon: string
  title: string
  subtitle: string | null
  url: string
}

const NAV: { label: string; path: string; icon: string }[] = [
  { label: 'Dashboard', path: '/', icon: 'dashboard' },
  { label: 'Accounts', path: '/accounts', icon: 'accounts' },
  { label: 'Statements', path: '/statements', icon: 'statements' },
  { label: 'Ledger', path: '/ledger', icon: 'journal' },
  { label: 'Periods', path: '/periods', icon: 'periods' },
]

function hitToItem(hit: SearchHit, query: string): PaletteItem {
  const base = { key: `${hit.type}-${hit.id}`, title: hit.title, subtitle: hit.subtitle }
  // Transactions and journal entries live in the general ledger once posted, so
  // route them to the ledger filtered by what the user typed — surfacing all
  // matching posted entries rather than a single period's working journal.
  const ledgerUrl = `/ledger?q=${encodeURIComponent(query)}`
  switch (hit.type) {
    case 'account':
      return { ...base, group: 'Accounts', icon: 'accounts', url: '/accounts' }
    case 'transaction':
      return { ...base, group: 'Transactions', icon: 'trending', url: ledgerUrl }
    case 'journal_entry':
      return { ...base, group: 'Journal entries', icon: 'journal', url: ledgerUrl }
    case 'document':
      return { ...base, group: 'Documents', icon: 'file', url: `/periods/${hit.period_id}` }
    case 'period':
      return { ...base, group: 'Periods', icon: 'periods', url: `/periods/${hit.period_id}` }
  }
}

export default function SearchPalette({ onClose }: Props) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [active, setActive] = useState(0)
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 200)
    return () => clearTimeout(t)
  }, [query])

  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => searchGlobal(debounced),
    enabled: debounced.length > 0,
    staleTime: 30_000,
  })

  const items = useMemo<PaletteItem[]>(() => {
    const q = query.trim().toLowerCase()
    const navItems: PaletteItem[] = NAV
      .filter((n) => !q || n.label.toLowerCase().includes(q))
      .map((n) => ({ key: `nav-${n.path}`, group: 'Pages', icon: n.icon, title: n.label, subtitle: null, url: n.path }))
    if (!q) return navItems
    const hitItems = (data?.hits ?? []).map((h) => hitToItem(h, query.trim()))
    return [...navItems, ...hitItems]
  }, [query, data])

  // Keep the highlighted row valid and visible as results change.
  useEffect(() => {
    setActive((i) => (i >= items.length ? 0 : i))
  }, [items.length])

  useEffect(() => {
    rowRefs.current[active]?.scrollIntoView({ block: 'nearest' })
  }, [active])

  function activate(item: PaletteItem | undefined) {
    if (!item) return
    navigate(item.url)
    onClose()
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      activate(items[active])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  const showEmpty = query.trim().length > 0 && !isFetching && items.length === 0

  let lastGroup = ''

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--palette" onClick={(e) => e.stopPropagation()}>
        <div className="palette-input">
          <SvgIcon name="search" size={16} />
          <input
            className="palette-field"
            placeholder="Search transactions, accounts, documents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            autoFocus
          />
          <kbd>Esc</kbd>
        </div>

        <div className="palette-results">
          {items.map((item, i) => {
            const header = item.group !== lastGroup ? item.group : null
            lastGroup = item.group
            return (
              <div key={item.key}>
                {header && <div className="palette-group">{header}</div>}
                <button
                  ref={(el) => { rowRefs.current[i] = el }}
                  className={`palette-row${i === active ? ' is-active' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => activate(item)}
                >
                  <SvgIcon name={item.icon} size={15} />
                  <span className="palette-row-title">{item.title}</span>
                  {item.subtitle && <span className="palette-row-sub">{item.subtitle}</span>}
                </button>
              </div>
            )
          })}

          {showEmpty && (
            <div className="palette-empty">No results for “{query.trim()}”</div>
          )}
          {isFetching && query.trim() && (
            <div className="palette-empty">Searching…</div>
          )}
        </div>
      </div>
    </div>
  )
}
