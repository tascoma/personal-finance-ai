import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import SvgIcon from './SvgIcon'
import UserAvatar from './UserAvatar'
import { useAuth } from '../contexts/AuthContext'
import { getMe } from '../api/auth'
import type { Period } from '../types'
import { fmtPeriod } from '../utils/format'

interface Props {
  activePeriod?: Period | null
}

export default function AppHeader({ activePeriod }: Props) {
  const { logout, token } = useAuth()
  const { data: me } = useQuery({
    queryKey: ['auth-me'],
    queryFn: getMe,
    enabled: !!token,
    staleTime: Infinity,
  })

  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => {
      const saved = localStorage.getItem('fa-theme') || localStorage.getItem('pf-theme')
      return saved === 'light' ? 'light' : 'dark'
    },
  )

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('fa-theme', next)
  }

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const periodLabel = activePeriod ? fmtPeriod(activePeriod.period_start) : null
  const initials = 'TS'

  return (
    <header className="header">
      <Link to="/" className="brand">
        <span className="brand-mark">F</span>
        <span>Finance AI</span>
      </Link>

      {activePeriod ? (
        <Link to="/periods" className="header-period" title="View periods">
          <span className="header-period-dot" />
          <span style={{ fontSize: 12 }}>active period {periodLabel}</span>
        </Link>
      ) : (
        <Link to="/periods" className="header-period" title="View periods" style={{ opacity: 0.6 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--text-3)', flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>workflow · no active period</span>
        </Link>
      )}

      <button className="header-search" onClick={() => {}} aria-label="Search">
        <SvgIcon name="search" size={14} />
        <span>Search transactions, accounts…</span>
        <kbd>⌘K</kbd>
      </button>

      <div className="header-right">
        <button
          className="icon-btn"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
        >
          {theme === 'dark' ? <SvgIcon name="sun" size={16} /> : <SvgIcon name="moon" size={16} />}
        </button>

        <div className="header-user">
          <UserAvatar email={me?.email} initials={initials} />
          {me && (
            <span className="header-user-email">{me.email}</span>
          )}
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  )
}
