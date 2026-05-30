import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchAccounts } from '../api/accounts'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import StatusBadge from '../components/StatusBadge'
import type { Account } from '../types'

const TYPE_ORDER = ['Asset', 'Liability', 'Equity', 'Income', 'Expense', 'Memo Asset*']
const TYPE_LABELS: Record<string, string> = {
  Asset: 'Assets',
  Liability: 'Liabilities',
  Equity: 'Equity',
  Income: 'Income',
  Expense: 'Expenses',
  'Memo Asset*': 'Memo (Off-Balance-Sheet)',
}
const TYPE_COLORS: Record<string, string> = {
  Asset: 'var(--accent)',
  Liability: 'var(--red)',
  Equity: 'var(--purple)',
  Income: 'var(--green)',
  Expense: 'var(--amber)',
  'Memo Asset*': 'var(--text-3)',
}

export default function AccountsPage() {
  const [activeFilter, setActiveFilter] = useState<string>('All')

  const { data: accounts = [], isLoading, error } = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    staleTime: 30_000,
  })

  const grouped = accounts.reduce<Record<string, Account[]>>((acc, a) => {
    ;(acc[a.account_type] ??= []).push(a)
    return acc
  }, {})

  const filters = ['All', ...TYPE_ORDER.filter(t => (grouped[t]?.length ?? 0) > 0)]
  const visibleTypes = activeFilter === 'All' ? TYPE_ORDER : [activeFilter]

  return (
    <Layout>
      <PageHeader
        eyebrow="Setup"
        title="Chart of Accounts"
        subtitle="The accounts your transactions post to"
      />

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="color-red">Failed to load accounts.</p>}

      {!isLoading && !error && (
        <>
          <div className="row gap-2 mb-4 wrap">
            {filters.map((t) => {
              const color = TYPE_COLORS[t]
              const active = activeFilter === t
              const count = t === 'All' ? accounts.length : (grouped[t]?.length ?? 0)
              return (
                <button
                  key={t}
                  className="badge"
                  onClick={() => setActiveFilter(t)}
                  style={{
                    fontSize: 12, padding: '6px 12px', cursor: 'pointer',
                    background: active ? 'var(--accent-tint)' : 'var(--bg-1)',
                    border: active ? '1px solid var(--accent-glow)' : '1px solid var(--line)',
                    color: active ? 'var(--accent)' : 'var(--text-2)',
                  }}
                >
                  {t !== 'All' && (
                    <span className="badge-dot" style={{ background: color }} />
                  )}
                  {TYPE_LABELS[t] ?? t}
                  <span className="mono muted" style={{ marginLeft: 6, fontSize: 11 }}>{count}</span>
                </button>
              )
            })}
          </div>

          <div className="card">
            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Account Name</th>
                    <th>Type</th>
                    <th>Sub-Category</th>
                    <th>Normal Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTypes.flatMap((t) => {
                    const accts = grouped[t] ?? []
                    return accts.map((a) => (
                      <tr key={a.account_code}>
                        <td className="mono muted" style={{ fontSize: 12.5, width: 70 }}>{a.account_code}</td>
                        <td style={{ fontWeight: 500 }}>{a.account_name}</td>
                        <td>
                          <span className="badge" style={{
                            background: (TYPE_COLORS[a.account_type] ?? 'var(--text-3)') + '20',
                            color: TYPE_COLORS[a.account_type] ?? 'var(--text-3)',
                            border: 'none',
                          }}>
                            <span className="badge-dot" />
                            {a.account_type}
                          </span>
                        </td>
                        <td className="muted">{a.sub_category}</td>
                        <td><StatusBadge status={a.normal_balance} /></td>
                      </tr>
                    ))
                  })}
                </tbody>
              </table>
            </div>

            {!accounts.length && (
              <EmptyState icon="accounts" message="No accounts configured." hint="Add accounts to your chart of accounts." />
            )}
          </div>
        </>
      )}
    </Layout>
  )
}
