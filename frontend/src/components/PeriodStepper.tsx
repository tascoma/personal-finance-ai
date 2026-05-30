import type { Period } from '../types'
import SvgIcon from './SvgIcon'

const STEPS = [
  { status: 'open',           name: 'Documents & balances', meta: 'Upload statements' },
  { status: 'pending_review', name: 'Review transactions',  meta: 'Classify & approve' },
  { status: 'pending_close',  name: 'Reconcile & post',     meta: 'Close the period' },
  { status: 'closed',         name: 'Closed',               meta: '' },
]

const ORDER: Record<string, number> = { open: 0, pending_review: 1, pending_close: 2, closed: 3 }

interface Props {
  period: Period
}

export default function PeriodStepper({ period }: Props) {
  const current = ORDER[period.status] ?? 0
  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        const cls = i < current ? 'done' : i === current ? 'active' : ''
        return (
          <div key={s.status} className={`step ${cls}`}>
            <div className="step-circle">
              {i < current ? <SvgIcon name="check" size={14} strokeWidth={2.5} /> : i + 1}
            </div>
            <div className="stack">
              <div className="step-name">{s.name}</div>
              {s.meta && <div className="step-meta">{s.meta}</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
