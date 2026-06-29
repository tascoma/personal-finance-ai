import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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

  const [searchParams, setSearchParams] = useSearchParams()
  const [filter, setFilter] = useState(searchParams.get('q') ?? '')
  // Keep the box in sync when arriving via a ?q= link (e.g. from global search).
  useEffect(() => {
    setFilter(searchParams.get('q') ?? '')
  }, [searchParams])

  const term = filter.trim().toLowerCase()
  const accounts = data?.accounts_by_code ?? {}

  function entryMatches(entry: { description: string; lines: { memo: string | null; account_code: number }[] }): boolean {
    if (!term) return true
    if (entry.description.toLowerCase().includes(term)) return true
    return entry.lines.some(
      (l) =>
        (l.memo ?? '').toLowerCase().includes(term) ||
        (accounts[l.account_code]?.account_name ?? '').toLowerCase().includes(term),
    )
  }

  function highlight(text: string): ReactNode {
    if (!term) return text
    const idx = text.toLowerCase().indexOf(term)
    if (idx === -1) return text
    return (
      <>
        {text.slice(0, idx)}
        <mark className="hl">{text.slice(idx, idx + term.length)}</mark>
        {text.slice(idx + term.length)}
      </>
    )
  }

  const visiblePeriods = (data?.periods ?? [])
    .map((period) => ({
      period,
      entries: (data?.entries_by_period[period.period_id] ?? []).filter(entryMatches),
    }))
    .filter(({ entries }) => !term || entries.length > 0)

  const matchCount = term ? visiblePeriods.reduce((s, p) => s + p.entries.length, 0) : null

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

      {data && (
        <div className="ledger-filter">
          <SvgIcon name="search" size={14} />
          <input
            className="ledger-filter-field"
            placeholder="Filter posted entries by description, memo, or account…"
            value={filter}
            onChange={(e) => {
              const v = e.target.value
              setFilter(v)
              setSearchParams(v ? { q: v } : {}, { replace: true })
            }}
          />
          {term && (
            <span className="muted" style={{ fontSize: 12 }}>
              {matchCount} {matchCount === 1 ? 'match' : 'matches'}
            </span>
          )}
          {filter && (
            <button
              className="icon-btn"
              aria-label="Clear filter"
              onClick={() => { setFilter(''); setSearchParams({}, { replace: true }) }}
            >
              <SvgIcon name="x" size={14} />
            </button>
          )}
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="color-red">Failed to load ledger.</p>}

      {!isLoading && !error && !data?.periods.length && (
        <div className="card">
          <EmptyState icon="journal" message="No periods yet." hint="Create a period under Workflow to begin recording entries." />
        </div>
      )}

      {!isLoading && !error && term && data?.periods.length && visiblePeriods.length === 0 && (
        <div className="card">
          <EmptyState icon="journal" message={`No posted entries match “${filter.trim()}”.`} hint="Try a different term, or clear the filter." />
        </div>
      )}

      <div className="stack gap-4">
        {visiblePeriods.map(({ period, entries }) => {
          // While filtering, force-expand so matches are always visible.
          const isCollapsed = term ? false : collapsed[period.period_id]

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
                              <div className="card-title">{highlight(entry.description)}</div>
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
                                    const acct = accounts[line.account_code]
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
