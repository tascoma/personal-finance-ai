import type { CSSProperties, ReactNode } from 'react'
import SvgIcon from './SvgIcon'

interface Props {
  variant: 'amber' | 'green' | 'accent' | 'red'
  children: ReactNode
  style?: CSSProperties
  noIcon?: boolean
}

const ICONS = { amber: 'alert', green: 'check', accent: 'spark', red: 'alert' } as const

export default function Banner({ variant, children, style, noIcon }: Props) {
  return (
    <div className={`banner banner--${variant}`} style={style}>
      {!noIcon && <SvgIcon name={ICONS[variant]} size={14} />}
      <span>{children}</span>
    </div>
  )
}
