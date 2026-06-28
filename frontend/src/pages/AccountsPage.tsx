import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchAccounts, createAccount, updateAccount } from '../api/accounts'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import StatusBadge from '../components/StatusBadge'
import AccountModal from '../components/AccountModal'
import { useConfirm } from '../hooks/useConfirm'
import { nextAccountCode } from '../utils/accountCode'
import type { Account, AccountCreate, AccountUpdate } from '../types'

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

type ModalState = { mode: 'add' } | { mode: 'edit'; account: Account } | null

export default function AccountsPage() {
  const qc = useQueryClient()
  const { ask, confirmDialog } = useConfirm()
  const [activeFilter, setActiveFilter] = useState<string>('All')
  const [showInactive, setShowInactive] = useState(false)
  const [modal, setModal] = useState<ModalState>(null)
  const [modalError, setModalError] = useState<string | null>(null)
  const [pageError, setPageError] = useState<string | null>(null)

  const { data: accounts = [], isLoading, error } = useQuery({
    queryKey: ['accounts', 'all'],
    queryFn: () => fetchAccounts(true),
    staleTime: 30_000,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['accounts'] })

  const createMut = useMutation({
    mutationFn: createAccount,
    onSuccess: () => { setModal(null); invalidate() },
    onError: (e: Error) => setModalError(e.message),
  })
  const updateMut = useMutation({
    mutationFn: ({ code, body }: { code: number; body: AccountUpdate }) => updateAccount(code, body),
    onSuccess: () => { setModal(null); invalidate() },
    onError: (e: Error) => setModalError(e.message),
  })
  const toggleMut = useMutation({
    mutationFn: ({ code, active }: { code: number; active: boolean }) => updateAccount(code, { is_active: active }),
    onSuccess: invalidate,
    onError: (e: Error) => setPageError(e.message),
  })

  const openAdd = () => { setModalError(null); setPageError(null); setModal({ mode: 'add' }) }
  const openEdit = (a: Account) => { setModalError(null); setPageError(null); setModal({ mode: 'edit', account: a }) }

  const archive = (a: Account) => {
    setPageError(null)
    ask({
      title: 'Archive account',
      message: `Archive ${a.account_name} (${a.account_code})? It will be hidden from new transactions, but its history is preserved. You can restore it later.`,
      confirmLabel: 'Archive',
      danger: true,
      onConfirm: () => toggleMut.mutate({ code: a.account_code, active: false }),
    })
  }

  const handleSubmit = (payload: AccountCreate | AccountUpdate) => {
    if (!modal) return
    if (modal.mode === 'add') createMut.mutate(payload as AccountCreate)
    else updateMut.mutate({ code: modal.account.account_code, body: payload as AccountUpdate })
  }

  const displayed = showInactive ? accounts : accounts.filter((a) => a.is_active)
  const existingCodes = accounts.map((a) => a.account_code)
  const suggestCode = (type: string) => nextAccountCode(existingCodes, type)

  const subCategoriesByType = accounts.reduce<Record<string, string[]>>((acc, a) => {
    const list = (acc[a.account_type] ??= [])
    if (!list.includes(a.sub_category)) list.push(a.sub_category)
    return acc
  }, {})
  Object.values(subCategoriesByType).forEach((l) => l.sort())

  const grouped = displayed.reduce<Record<string, Account[]>>((acc, a) => {
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
        actions={<button className="btn btn-primary btn-sm" onClick={openAdd}>+ Add Account</button>}
      />

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="color-red">Failed to load accounts.</p>}
      {pageError && <p className="color-red">{pageError}</p>}

      {!isLoading && !error && (
        <>
          <div className="row gap-2 mb-4 wrap" style={{ justifyContent: 'space-between' }}>
            <div className="row gap-2 wrap">
              {filters.map((t) => {
                const color = TYPE_COLORS[t]
                const active = activeFilter === t
                const count = t === 'All' ? displayed.length : (grouped[t]?.length ?? 0)
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
            <label className="row gap-2" style={{ alignItems: 'center', cursor: 'pointer', fontSize: 13, color: 'var(--text-2)' }}>
              <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
              Show archived
            </label>
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
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTypes.flatMap((t) => {
                    const accts = grouped[t] ?? []
                    return accts.map((a) => (
                      <tr key={a.account_code} style={a.is_active ? undefined : { opacity: 0.55 }}>
                        <td className="mono muted" style={{ fontSize: 12.5, width: 70 }}>{a.account_code}</td>
                        <td style={{ fontWeight: 500 }}>
                          {a.account_name}
                          {!a.is_active && <span className="badge muted" style={{ marginLeft: 8, fontSize: 11 }}>Archived</span>}
                        </td>
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
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => openEdit(a)}>Edit</button>
                          {a.is_active ? (
                            <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)' }} onClick={() => archive(a)}>Archive</button>
                          ) : (
                            <button className="btn btn-ghost btn-sm" style={{ color: 'var(--accent)' }} onClick={() => toggleMut.mutate({ code: a.account_code, active: true })}>Restore</button>
                          )}
                        </td>
                      </tr>
                    ))
                  })}
                </tbody>
              </table>
            </div>

            {!displayed.length && (
              <EmptyState icon="accounts" message="No accounts configured." hint="Add accounts to your chart of accounts." />
            )}
          </div>
        </>
      )}

      {modal && (
        <AccountModal
          mode={modal.mode}
          initial={modal.mode === 'edit' ? modal.account : undefined}
          existingCodes={existingCodes}
          subCategoriesByType={subCategoriesByType}
          suggestCode={suggestCode}
          pending={createMut.isPending || updateMut.isPending}
          error={modalError}
          onSubmit={handleSubmit}
          onClose={() => setModal(null)}
        />
      )}
      {confirmDialog}
    </Layout>
  )
}
