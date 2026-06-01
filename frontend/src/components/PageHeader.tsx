import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import SvgIcon from './SvgIcon'

interface Props {
  title: string
  eyebrow?: string
  subtitle?: string
  backTo?: string
  backLabel?: string
  badge?: ReactNode
  right?: ReactNode
  actions?: ReactNode
}

export default function PageHeader({ title, eyebrow, subtitle, backTo, backLabel, badge, right, actions }: Props) {
  return (
    <div className="page-header">
      <div>
        {backTo && (
          <Link to={backTo} className="btn btn-ghost btn-sm" style={{ marginBottom: 8, marginLeft: -8 }}>
            <SvgIcon name="arrowLeft" size={14} />
            {backLabel ?? 'Back'}
          </Link>
        )}
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <div className="row gap-3">
          <h1 className="page-title">{title}</h1>
          {badge}
        </div>
        {subtitle && <div className="page-sub">{subtitle}</div>}
      </div>
      {(right || actions) && (
        <div className="page-actions">
          {right}
          {actions}
        </div>
      )}
    </div>
  )
}
