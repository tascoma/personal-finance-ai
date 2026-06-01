import { Link } from 'react-router-dom'
import type { Period, PeriodStatus } from '../types'
import SvgIcon from './SvgIcon'

type Page = 'detail' | 'journal' | 'reconcile'

interface Props {
  period: Period
  page: Page
}

interface Hint {
  phase: string
  text: string
  cta?: { label: string; to: string; direction?: 'back' | 'forward' }
}

const HINTS: Record<PeriodStatus, Record<Page, Hint>> = {
  open: {
    detail:    { phase: 'Step 1 · Input', text: 'Upload your statements and click Parse — the orchestrator identifies each document, picks the source account, and extracts transactions. Add stated balances on the Balances tab, then advance when ready.' },
    journal:   { phase: 'Step 1 · Input', text: 'No transactions yet — return to the period detail page to upload and parse documents first.', cta: { label: 'Back to Period', to: '', direction: 'back' } },
    reconcile: { phase: 'Step 1 · Input', text: 'Reconciliation runs after journal entries are posted. Finish parsing, approving, and posting first.', cta: { label: 'Back to Period', to: '', direction: 'back' } },
  },
  pending_review: {
    detail:    { phase: 'Step 2 · Review', text: 'Documents are parsed. Open the Journal tab to classify, review, and approve transactions.', cta: { label: 'Review Journal', to: '/journal', direction: 'forward' } },
    journal:   { phase: 'Step 2 · Review', text: 'Each transaction needs a category. Click Classify with AI for a first-pass, fix any wrong ones, then Approve. Advance to Pending Close when Staged is empty.' },
    reconcile: { phase: 'Step 2 · Review', text: 'Not ready yet — approve all staged transactions in the Journal, then advance the period.', cta: { label: 'Open Journal', to: '/journal', direction: 'back' } },
  },
  pending_close: {
    detail:    { phase: 'Step 3 · Post', text: 'Transactions are approved. Head to the Journal tab to Post them to the ledger, then run reconciliation.', cta: { label: 'Open Journal', to: '/journal', direction: 'forward' } },
    journal:   { phase: 'Step 3 · Post', text: 'Click Post All Approved to write entries to the ledger. Once posted, move to Reconcile to verify balances and close.', cta: { label: 'Open Reconcile', to: '/reconcile', direction: 'forward' } },
    reconcile: { phase: 'Step 4 · Reconcile & Close', text: 'Run reconciliation to compare computed vs stated balances. Resolve gaps, post closing entries, then Close.' },
  },
  closed: {
    detail:    { phase: 'Closed', text: 'This period is locked. All journal entries have been posted to the ledger. Reopen from the Lifecycle tab if needed.' },
    journal:   { phase: 'Closed', text: 'This period is closed and read-only.', cta: { label: 'Period Detail', to: '', direction: 'back' } },
    reconcile: { phase: 'Closed', text: 'This period is closed. Reconciliation data remains visible.', cta: { label: 'Period Detail', to: '', direction: 'back' } },
  },
}

export default function WorkflowHint({ period, page }: Props) {
  const hint = HINTS[period.status][page]
  const ctaPath = hint.cta ? `/periods/${period.period_id}${hint.cta.to}` : null

  return (
    <div className="wf-hint" role="status">
      <div className="wf-hint-icon">
        <SvgIcon name="spark" size={14} />
      </div>
      <div className="wf-hint-body">
        <div className="wf-hint-phase">{hint.phase}</div>
        <p className="wf-hint-text">{hint.text}</p>
      </div>
      {hint.cta && ctaPath && (
        <Link to={ctaPath} className="btn btn-secondary btn-sm wf-hint-cta">
          {hint.cta.direction === 'back' ? '← ' : ''}{hint.cta.label}{hint.cta.direction === 'forward' ? ' →' : ''}
        </Link>
      )}
    </div>
  )
}
