import { NavLink, useLocation } from 'react-router-dom'
import SvgIcon from './SvgIcon'

const NAV = [
  { to: '/',            icon: 'dashboard',  tip: 'Dashboard' },
  { to: '/periods',     icon: 'periods',    tip: 'Workflow' },
  { to: '/ledger',      icon: 'journal',    tip: 'Ledger' },
  { to: '/statements',  icon: 'statements', tip: 'Statements' },
  { to: '/accounts',    icon: 'accounts',   tip: 'Accounts' },
]

export default function Sidebar() {
  const { pathname } = useLocation()

  return (
    <nav className="sidebar">
      {NAV.map((item) => {
        const isActive = item.to === '/'
          ? pathname === '/'
          : pathname.startsWith(item.to)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={`nav-link${isActive ? ' active' : ''}`}
            data-tip={item.tip}
            aria-label={item.tip}
            end={item.to === '/'}
          >
            <SvgIcon name={item.icon} size={18} />
          </NavLink>
        )
      })}
    </nav>
  )
}
