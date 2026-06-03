import SvgIcon from './SvgIcon'
import type { ComponentProps, ReactNode } from 'react'

interface Props {
  icon?: ComponentProps<typeof SvgIcon>['name']
  message: string
  hint?: string
  children?: ReactNode
}

export default function EmptyState({ icon = 'file', message, hint, children }: Props) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <SvgIcon name={icon} size={20} />
      </div>
      <div className="empty-title">{message}</div>
      {hint && <div className="empty-sub">{hint}</div>}
      {children}
    </div>
  )
}
