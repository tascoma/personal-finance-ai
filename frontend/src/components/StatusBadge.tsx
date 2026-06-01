interface Props { status: string }

const MAP: Record<string, { cls: string; label: string }> = {
  open:           { cls: 'badge--green',  label: 'Open' },
  pending_review: { cls: 'badge--amber',  label: 'Review' },
  pending_close:  { cls: 'badge--accent', label: 'Pending Close' },
  closed:         { cls: 'badge--ghost',  label: 'Closed' },
  parsed:         { cls: 'badge--green',  label: 'Parsed' },
  complete:       { cls: 'badge--green',  label: 'Parsed' },
  pending:        { cls: 'badge--amber',  label: 'Pending' },
  failed:         { cls: 'badge--red',    label: 'Failed' },
  reconciled:     { cls: 'badge--green',  label: 'Reconciled' },
  adjusted:       { cls: 'badge--accent', label: 'Adjusted' },
  staged:         { cls: 'badge--amber',  label: 'Staged' },
  approved:       { cls: 'badge--accent', label: 'Approved' },
  debit:          { cls: 'badge--accent', label: 'Debit' },
  credit:         { cls: 'badge--purple', label: 'Credit' },
}

export default function StatusBadge({ status }: Props) {
  const m = MAP[status] ?? { cls: '', label: status.replace(/_/g, ' ') }
  return (
    <span className={`badge ${m.cls}`}>
      <span className="badge-dot" />
      {m.label}
    </span>
  )
}
