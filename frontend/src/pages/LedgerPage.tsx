import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { fetchLedger } from '../api/ledger'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import { fmtPeriod, fmtDate, fmtDebitCredit } from '../utils/format'

export default function LedgerPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['ledger'],
    queryFn: fetchLedger,
    staleTime: 30_000,
  })

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const toggle = (id: string) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <Layout>
      <PageHeader
        eyebrow="General Ledger"
        title="All posted entries"
        subtitle={data ? `${data.periods.length} closed periods` : undefined}
        actions={
          <button className="btn btn-secondary btn-sm">
            <SvgIcon name="download" size={13} /> Export CSV
          </button>
        }
      />

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="color-red">Failed to load ledger.</p>}

      {!isLoading && !error && !data?.periods.length && (
        <div className="card">
          <EmptyState icon="journal" message="No periods yet." hint="Create a period under Workflow to begin recording entries." />
        </div>
      )}

      <div className="stack gap-4">
        {data?.periods.map((period) => {
          const entries = data.entries_by_period[period.period_id] ?? []
          const isCollapsed = collapsed[period.period_id]

          return (
            <div key={period.period_id} className="card">
              <div className="card-hd">
                <div>
                  <div className="row gap-3">
                    <div className="card-title">{fmtPeriod(period.period_start)}</div>
                    <StatusBadge status={period.status} />
                  </div>
                  <div className="card-sub">
                    {period.period_start} → {period.period_end} · {entries.length}{' '}
                    {entries.length === 1 ? 'entry' : 'entries'}
                  </div>
                </div>
                <div className="row gap-2">
                  <Link to={`/periods/${period.period_id}`} className="btn btn-ghost btn-sm">
                    Open period <SvgIcon name="arrow" size={13} />
                  </Link>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => toggle(period.period_id)}
                    aria-expanded={!isCollapsed}
                  >
                    <SvgIcon
                      name="chevron-down"
                      size={14}
                      style={{ transition: 'transform .2s', transform: isCollapsed ? 'rotate(-90deg)' : undefined }}
                    />
                    {isCollapsed ? 'Expand' : 'Collapse'}
                  </button>
                </div>
              </div>

              {!isCollapsed && (
                entries.length ? (
                  <div className="stack gap-3" style={{ padding: '14px 16px' }}>
                    {entries.map((entry) => {
                      const totalDebit = entry.lines.reduce((s, l) => s + parseFloat(l.debit_amount), 0)
                      const totalCredit = entry.lines.reduce((s, l) => s + parseFloat(l.credit_amount), 0)
                      return (
                        <div key={entry.entry_id} className="card" style={{ margin: 0 }}>
                          <div className="card-hd">
                            <div>
                              <div className="card-title">{entry.description}</div>
                              <div className="card-sub mono">{fmtDate(entry.entry_date)}</div>
                            </div>
                            <div className="row gap-3">
                              <span className="badge badge--ghost">{entry.source_type.replace(/_/g,' ')}</span>
                              <span className="mono fw-600">${totalDebit.toFixed(2)}</span>
                            </div>
                          </div>
                          {entry.lines.length > 0 && (
                            <div className="tbl-scroll">
                              <table className="tbl">
                                <thead>
                                  <tr>
                                    <th>Account</th>
                                    <th>Memo</th>
                                    <th className="text-right">Debit</th>
                                    <th className="text-right">Credit</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {entry.lines.map((line) => {
                                    const acct = data.accounts_by_code[line.account_code]
                                    return (
                                      <tr key={line.line_id}>
                                        <td className="mono" style={{ fontSize: 13 }}>
                                          <span className="muted">{line.account_code}</span>
                                          {acct ? ` · ${acct.account_name}` : ''}
                                        </td>
                                        <td className="muted" style={{ fontSize: 12 }}>{line.memo ?? ''}</td>
                                        <td className="mono text-right" style={{ color: parseFloat(line.debit_amount) > 0 ? 'var(--text)' : 'var(--text-3)' }}>
                                          {fmtDebitCredit(line.debit_amount)}
                                        </td>
                                        <td className="mono text-right" style={{ color: parseFloat(line.credit_amount) > 0 ? 'var(--text)' : 'var(--text-3)' }}>
                                          {fmtDebitCredit(line.credit_amount)}
                                        </td>
                                      </tr>
                                    )
                                  })}
                                </tbody>
                                <tfoot>
                                  <tr>
                                    <td colSpan={2} className="muted" style={{ fontSize: 12 }}>Total</td>
                                    <td className="mono text-right fw-600">${totalDebit.toFixed(2)}</td>
                                    <td className="mono text-right fw-600">${totalCredit.toFixed(2)}</td>
                                  </tr>
                                </tfoot>
                              </table>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <EmptyState message="No entries posted yet." hint="Approve transactions and post them from the period workflow." />
                )
              )}
            </div>
          )
        })}
      </div>
    </Layout>
  )
}
