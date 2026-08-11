import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchJournalPage,
  classifyTransactions,
  postTransactions,
  createManualJournalEntry,
  deleteJournalEntry,
} from '../api/journal'
import { approveTransaction, unapproveTransaction, rejectTransaction, approveAllStaged, unapproveAll, rejectAllStaged, updateTransactionAccount } from '../api/transactions'
import { setDocumentSourceAccount } from '../api/documents'
import { updatePeriodStatus, stepBackPeriod } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import PeriodStepper from '../components/PeriodStepper'
import WorkflowHint from '../components/WorkflowHint'
import Banner from '../components/Banner'
import EmptyState from '../components/EmptyState'
import Tabs from '../components/Tabs'
import ConfidencePill from '../components/ConfidencePill'
import SvgIcon from '../components/SvgIcon'
import { useConfirm } from '../hooks/useConfirm'
import { fmtDebitCredit, fmtMoney, fmtPeriod, fmtStatus } from '../utils/format'
import type { JournalLineCreate, JournalPageResponse, RawTransaction } from '../types'

type Tab = 'staged' | 'approved' | 'posted'

interface Props {
  embedded?: boolean
  periodId?: string
}

export default function JournalPage({ embedded, periodId: propPeriodId }: Props) {
  const params = useParams<{ periodId: string }>()
  const periodId = propPeriodId ?? params.periodId
  const qc = useQueryClient()
  const { ask, confirmDialog } = useConfirm()
  const [activeTab, setActiveTab] = useState<Tab>('staged')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [entryDate, setEntryDate] = useState('')
  const [entryDesc, setEntryDesc] = useState('')
  const [entryType, setEntryType] = useState('manual')
  const [lines, setLines] = useState<Array<{ acct: string; debit: string; credit: string; memo: string }>>([
    { acct: '', debit: '', credit: '', memo: '' },
    { acct: '', debit: '', credit: '', memo: '' },
  ])

  const journalKey = ['journal', periodId] as const
  const invalidate = () => qc.invalidateQueries({ queryKey: journalKey })

  const patchJournal = (mutator: (prev: JournalPageResponse) => JournalPageResponse) => {
    const prev = qc.getQueryData<JournalPageResponse>(journalKey)
    if (prev) qc.setQueryData<JournalPageResponse>(journalKey, mutator(prev))
    return prev
  }
  const rollback = (prev: JournalPageResponse | undefined) => {
    if (prev) qc.setQueryData<JournalPageResponse>(journalKey, prev)
  }

  const { data, isLoading } = useQuery({
    queryKey: journalKey,
    queryFn: () => fetchJournalPage(periodId!),
    staleTime: 30_000,
    enabled: !!periodId,
  })

  const classify = useMutation({ mutationFn: () => classifyTransactions(periodId!), onSuccess: (r) => { setSuccess(`Classified ${r.classified} transaction(s).`); invalidate() }, onError: (e: Error) => setError(e.message) })
  const post = useMutation({ mutationFn: () => postTransactions(periodId!), onSuccess: (r) => { setSuccess(`Posted ${r.posted} transaction(s).`); invalidate() }, onError: (e: Error) => setError(e.message) })

  const approve = useMutation({
    mutationFn: (id: string) => approveTransaction(periodId!, id),
    onMutate: (id) => ({ prev: patchJournal((p) => { const txn = p.staged.find((t) => t.raw_txn_id === id); if (!txn) return p; return { ...p, staged: p.staged.filter((t) => t.raw_txn_id !== id), approved: [...p.approved, { ...txn, status: 'approved' }] } }) }),
    onError: (e: Error, _id, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const unapprove = useMutation({
    mutationFn: (id: string) => unapproveTransaction(periodId!, id),
    onMutate: (id) => ({ prev: patchJournal((p) => { const txn = p.approved.find((t) => t.raw_txn_id === id); if (!txn) return p; return { ...p, approved: p.approved.filter((t) => t.raw_txn_id !== id), staged: [...p.staged, { ...txn, status: 'staged' }] } }) }),
    onError: (e: Error, _id, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const reject = useMutation({
    mutationFn: (id: string) => rejectTransaction(periodId!, id),
    onMutate: (id) => ({ prev: patchJournal((p) => ({ ...p, staged: p.staged.filter((t) => t.raw_txn_id !== id) })) }),
    onError: (e: Error, _id, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const approveAll = useMutation({
    mutationFn: () => approveAllStaged(periodId!),
    onMutate: () => ({ prev: patchJournal((p) => ({ ...p, staged: [], approved: [...p.approved, ...p.staged.map((t): RawTransaction => ({ ...t, status: 'approved' }))] })) }),
    onSuccess: (r) => setSuccess(`Approved ${r.updated} transaction(s).`),
    onError: (e: Error, _v, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const unapproveAllMut = useMutation({
    mutationFn: () => unapproveAll(periodId!),
    onMutate: () => ({ prev: patchJournal((p) => ({ ...p, approved: [], staged: [...p.staged, ...p.approved.map((t): RawTransaction => ({ ...t, status: 'staged' }))] })) }),
    onError: (e: Error, _v, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const rejectAll = useMutation({
    mutationFn: () => rejectAllStaged(periodId!),
    onMutate: () => ({ prev: patchJournal((p) => ({ ...p, staged: [] })) }),
    onError: (e: Error, _v, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const updateAcct = useMutation({
    mutationFn: ({ id, code }: { id: string; code: number }) => updateTransactionAccount(periodId!, id, code),
    onMutate: ({ id, code }) => ({ prev: patchJournal((p) => ({ ...p, staged: p.staged.map((t) => t.raw_txn_id === id ? { ...t, suggested_account_code: code, classifier_confidence: '1.000' } : t) })) }),
    onError: (e: Error, _v, ctx) => { rollback(ctx?.prev); setError(e.message) },
  })
  const deleteEntry = useMutation({ mutationFn: (id: string) => deleteJournalEntry(periodId!, id), onSuccess: invalidate, onError: (e: Error) => setError(e.message) })
  const advanceStatus = useMutation({ mutationFn: (s: string) => updatePeriodStatus(periodId!, s), onSuccess: invalidate, onError: (e: Error) => setError(e.message) })
  const stepBack = useMutation({ mutationFn: () => stepBackPeriod(periodId!), onSuccess: invalidate, onError: (e: Error) => setError(e.message) })
  const setDocSource = useMutation({ mutationFn: ({ docId, code }: { docId: string; code: number }) => setDocumentSourceAccount(periodId!, docId, code), onSuccess: invalidate })
  const postManualEntry = useMutation({
    mutationFn: () => createManualJournalEntry(periodId!, {
      entry_date: entryDate, description: entryDesc, source_type: entryType,
      lines: lines.filter((l) => l.acct).map((l): JournalLineCreate => ({ account_code: parseInt(l.acct, 10), debit: l.debit || '0', credit: l.credit || '0', memo: l.memo || undefined })),
    }),
    onSuccess: () => {
      setSuccess('Entry posted.')
      setEntryDate(''); setEntryDesc(''); setEntryType('manual')
      setLines([{ acct: '', debit: '', credit: '', memo: '' }, { acct: '', debit: '', credit: '', memo: '' }])
      invalidate()
    },
    onError: (e: Error) => setError(e.message),
  })

  if (isLoading || !data) {
    if (embedded) return <p className="muted">Loading…</p>
    return <Layout><p className="muted">Loading…</p></Layout>
  }

  const { period, accounts, staged, approved, entries, has_unclassified, documents, docs_missing_source, next_status, prev_status } = data
  const accountsByCode = Object.fromEntries(accounts.map((a) => [a.account_code, a]))
  const documentsById = Object.fromEntries(documents.map((d) => [d.document_id, d]))
  const canEdit = period.status === 'open' || period.status === 'pending_close'

  const balanceIndicator = () => {
    const dr = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0)
    const cr = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0)
    const diff = Math.abs(dr - cr)
    if (dr === 0 && cr === 0) return null
    if (diff < 0.005) return <span className="mono color-green" style={{ fontSize: 12 }}>Balanced ✓</span>
    return <span className="mono color-red" style={{ fontSize: 12 }}>Out of balance by ${diff.toFixed(2)}</span>
  }

  const content = (
    <>
      {error && <Banner variant="red" style={{ marginBottom: 12 }}>{error}</Banner>}
      {success && <Banner variant="green" style={{ marginBottom: 12 }}>{success}</Banner>}

      {docs_missing_source.length > 0 && (
        <Banner variant="amber" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
          <div>
            <strong>{docs_missing_source.length} document{docs_missing_source.length > 1 ? 's' : ''} missing a deposit account</strong>
            {' — '}set the account that receives net proceeds before posting.
          </div>
          {docs_missing_source.map((doc) => (
            <div key={doc.document_id} className="row gap-2">
              <span className="muted" style={{ fontSize: 12.5, minWidth: 180 }}>{doc.file_name}</span>
              <select className="inp" style={{ fontSize: 12, padding: '4px 8px', minWidth: 220 }} defaultValue=""
                onChange={(e) => { if (e.target.value) setDocSource.mutate({ docId: doc.document_id, code: parseInt(e.target.value, 10) }) }}>
                <option value="">— select account —</option>
                {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
              </select>
            </div>
          ))}
        </Banner>
      )}

      <div className="kpi-grid kpi-4 mb-4">
        <div className="kpi"><div className="kpi-label">Staged</div><div className="kpi-value">{staged.length}</div><div className="kpi-sub">awaiting review</div></div>
        <div className="kpi"><div className="kpi-label">Approved</div><div className="kpi-value">{approved.length}</div><div className="kpi-sub">ready to post</div></div>
        <div className="kpi"><div className="kpi-label">Low confidence</div><div className="kpi-value">{staged.filter(t => parseFloat(t.classifier_confidence ?? '1') < 0.7).length}</div><div className="kpi-sub">below 70%</div></div>
        <div className="kpi"><div className="kpi-label">Posted</div><div className="kpi-value">{entries.length}</div><div className="kpi-sub">this period</div></div>
      </div>

      <Tabs
        active={activeTab}
        onChange={(k) => setActiveTab(k as typeof activeTab)}
        tabs={[
          { key: 'staged', label: 'To review', count: staged.length },
          { key: 'approved', label: 'Approved', count: approved.length },
          { key: 'posted', label: 'Posted', count: entries.length },
        ]}
      />

      {/* Staged tab */}
      {activeTab === 'staged' && (
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">Staged Transactions</div>
              <div className="card-sub">Awaiting review and approval</div>
            </div>
            <div className="row gap-2">
              {canEdit && has_unclassified && (
                <button className="btn btn-secondary btn-sm" disabled={classify.isPending} onClick={() => classify.mutate()}>
                  <SvgIcon name="sparkles" size={13} />{classify.isPending ? 'Classifying…' : 'Classify with AI'}
                </button>
              )}
              {canEdit && staged.length > 0 && (
                <>
                  <button className="btn btn-secondary btn-sm" disabled={approveAll.isPending} onClick={() => approveAll.mutate()}>
                    <SvgIcon name="sparkles" size={13} /> Approve high-confidence
                  </button>
                  <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)' }} disabled={rejectAll.isPending}
                    onClick={() => ask({ title: 'Reject all staged transactions?', message: `All ${staged.length} staged transaction(s) will be deleted.`, danger: true, confirmLabel: 'Reject All', onConfirm: () => rejectAll.mutate() })}>
                    Reject All
                  </button>
                </>
              )}
            </div>
          </div>
          {staged.length === 0 ? (
            <EmptyState icon="check" message="No staged transactions." hint="All transactions have been approved, rejected, or posted." />
          ) : (
            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Date</th><th>Description</th><th>Suggested account</th><th>Confidence</th>
                    <th className="text-right">Amount</th><th className="text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {staged.map((txn) => {
                    const n = parseFloat(txn.amount)
                    const doc = documentsById[txn.document_id]
                    return (
                      <tr key={txn.raw_txn_id} style={txn.is_flagged ? { background: 'rgba(251,191,36,0.04)' } : undefined}>
                        <td className="mono muted" style={{ fontSize: 12 }}>{txn.txn_date}</td>
                        <td>
                          <div className="row gap-2">
                            {txn.is_flagged && <SvgIcon name="alert" size={13} style={{ color: 'var(--amber)', flexShrink: 0 }} />}
                            <span>{txn.description}</span>
                            {txn.is_duplicate && <span className="muted" style={{ fontSize: 11 }}>(dup)</span>}
                          </div>
                          {doc && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{doc.document_type.replace(/_/g, ' ')}</div>}
                        </td>
                        <td>
                          {canEdit ? (
                            <select className="inp" style={{ fontSize: 12, padding: '4px 8px', minWidth: 200 }}
                              value={txn.suggested_account_code ?? ''}
                              onChange={(e) => { if (e.target.value) updateAcct.mutate({ id: txn.raw_txn_id, code: parseInt(e.target.value, 10) }) }}>
                              <option value="">— unclassified —</option>
                              {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
                            </select>
                          ) : (
                            <span className="badge badge--ghost">{accountsByCode[txn.suggested_account_code ?? 0]?.account_name ?? '—'}</span>
                          )}
                        </td>
                        <td><ConfidencePill confidence={txn.classifier_confidence} /></td>
                        <td className="mono text-right" style={{ color: n < 0 ? 'var(--red)' : 'var(--green)' }}>
                          {fmtMoney(n)}
                        </td>
                        <td className="text-right">
                          {canEdit ? (
                            <div className="row gap-2" style={{ justifyContent: 'flex-end' }}>
                              <button className="btn btn-ghost btn-sm" onClick={() => reject.mutate(txn.raw_txn_id)}>
                                <SvgIcon name="x" size={12} />
                              </button>
                              <button className="btn btn-secondary btn-sm" onClick={() => approve.mutate(txn.raw_txn_id)}>Approve</button>
                            </div>
                          ) : <StatusBadge status="staged" />}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Approved tab */}
      {activeTab === 'approved' && (
        <div className="card">
          <div className="card-hd">
            <div><div className="card-title">Approved Transactions</div><div className="card-sub">Ready to post to the ledger</div></div>
            {canEdit && approved.length > 0 && (
              <div className="row gap-2">
                <button className="btn btn-ghost btn-sm" disabled={unapproveAllMut.isPending} onClick={() => unapproveAllMut.mutate()}>Undo All</button>
                <button className="btn btn-primary btn-sm" disabled={post.isPending} onClick={() => post.mutate()}>Post All →</button>
              </div>
            )}
          </div>
          {approved.length === 0 ? (
            <EmptyState icon="journal" message="Nothing approved yet." hint="Approve staged transactions to post them." />
          ) : (
            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr><th>Date</th><th>Description</th><th>Account</th><th>Confidence</th><th className="text-right">Amount</th>{canEdit && <th />}</tr>
                </thead>
                <tbody>
                  {approved.map((txn) => {
                    const n = parseFloat(txn.amount)
                    const acct = txn.suggested_account_code ? accountsByCode[txn.suggested_account_code] : null
                    return (
                      <tr key={txn.raw_txn_id}>
                        <td className="mono muted" style={{ fontSize: 12 }}>{txn.txn_date}</td>
                        <td>{txn.description}</td>
                        <td><span className="badge badge--ghost">{txn.suggested_account_code ? `${txn.suggested_account_code}${acct ? ` · ${acct.account_name}` : ''}` : '—'}</span></td>
                        <td><ConfidencePill confidence={txn.classifier_confidence} /></td>
                        <td className="mono text-right" style={{ color: n < 0 ? 'var(--red)' : 'var(--green)' }}>
                          {fmtMoney(n)}
                        </td>
                        {canEdit && <td><button className="btn btn-ghost btn-sm" onClick={() => unapprove.mutate(txn.raw_txn_id)}>Undo</button></td>}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Posted tab */}
      {activeTab === 'posted' && (
        <div className="stack gap-4">
          {entries.length === 0 ? (
            <div className="card"><EmptyState icon="statements" message="No entries posted yet." hint="Approve transactions and click Post All to create journal entries." /></div>
          ) : (
            entries.map((entry) => {
              const totalDebit = entry.lines.reduce((s, l) => s + parseFloat(l.debit_amount), 0)
              const totalCredit = entry.lines.reduce((s, l) => s + parseFloat(l.credit_amount), 0)
              return (
                <div key={entry.entry_id} className="card">
                  <div className="card-hd">
                    <div>
                      <div className="card-title">{entry.description}</div>
                      <div className="card-sub mono">{entry.entry_date} · {entry.entry_id}</div>
                    </div>
                    <div className="row gap-3">
                      <span className="badge badge--ghost">{entry.source_type.replace(/_/g, ' ')}</span>
                      <span className="mono fw-600">${totalDebit.toFixed(2)}</span>
                      {period.status !== 'closed' && (
                        <button className="icon-btn" disabled={deleteEntry.isPending} style={{ color: 'var(--red)' }}
                          onClick={() => ask({ title: 'Delete this entry?', message: 'This journal entry will be permanently deleted.', danger: true, confirmLabel: 'Delete', onConfirm: () => deleteEntry.mutate(entry.entry_id) })}>
                          <SvgIcon name="trash" size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="tbl-scroll">
                    <table className="tbl">
                      <thead>
                        <tr><th>Account</th><th>Memo</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr>
                      </thead>
                      <tbody>
                        {[...entry.lines]
                          .sort((a, b) => { const aD = parseFloat(a.debit_amount) > 0; const bD = parseFloat(b.debit_amount) > 0; if (aD !== bD) return aD ? -1 : 1; return a.account_code - b.account_code })
                          .map((line) => {
                            const acct = accountsByCode[line.account_code]
                            return (
                              <tr key={line.line_id}>
                                <td className="mono" style={{ fontSize: 13 }}>
                                  <span className="muted">{line.account_code}</span>{acct ? ` · ${acct.account_name}` : ''}
                                </td>
                                <td className="muted" style={{ fontSize: 12 }}>{line.memo ?? ''}</td>
                                <td className="mono text-right" style={{ color: parseFloat(line.debit_amount) > 0 ? 'var(--text)' : 'var(--text-3)' }}>{fmtDebitCredit(line.debit_amount)}</td>
                                <td className="mono text-right" style={{ color: parseFloat(line.credit_amount) > 0 ? 'var(--text)' : 'var(--text-3)' }}>{fmtDebitCredit(line.credit_amount)}</td>
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
                </div>
              )
            })
          )}

          {/* Manual journal entry form */}
          {period.status !== 'closed' && (
            <div className="card">
              <div className="card-hd">
                <div>
                  <div className="card-title">New Manual Journal Entry</div>
                  <div className="card-sub">Directly post a balanced debit/credit entry for adjustments or accruals</div>
                </div>
                <button className="btn btn-secondary btn-sm"><SvgIcon name="plus" size={13} /> Manual entry</button>
              </div>
              <div className="card-bd">
                <div className="form-row mb-4">
                  <div className="field-group">
                    <label className="field-label">Date</label>
                    <input type="date" className="inp" style={{ width: 140 }} value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
                  </div>
                  <div className="field-group" style={{ flex: 1, minWidth: 220 }}>
                    <label className="field-label">Description</label>
                    <input type="text" className="inp" style={{ width: '100%' }} placeholder="e.g. Depreciation — December" value={entryDesc} onChange={(e) => setEntryDesc(e.target.value)} />
                  </div>
                  <div className="field-group">
                    <label className="field-label">Type</label>
                    <select className="inp" style={{ width: 140 }} value={entryType} onChange={(e) => setEntryType(e.target.value)}>
                      <option value="manual">Manual</option>
                      <option value="adjusting">Adjusting</option>
                      <option value="closing">Closing</option>
                    </select>
                  </div>
                </div>
                <div className="tbl-scroll">
                  <table className="tbl" style={{ marginBottom: 8 }}>
                    <thead>
                      <tr><th>Account</th><th style={{ width: 110 }}>Debit ($)</th><th style={{ width: 110 }}>Credit ($)</th><th style={{ width: 200 }}>Memo</th><th style={{ width: 36 }} /></tr>
                    </thead>
                    <tbody>
                      {lines.map((line, i) => (
                        <tr key={i}>
                          <td>
                            <select className="inp" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={line.acct}
                              onChange={(e) => setLines((ls) => ls.map((l, j) => j === i ? { ...l, acct: e.target.value } : l))}>
                              <option value="">— account —</option>
                              {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
                            </select>
                          </td>
                          <td><input type="number" step="0.01" min="0" className="inp mono" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={line.debit} placeholder="0.00" onChange={(e) => setLines((ls) => ls.map((l, j) => j === i ? { ...l, debit: e.target.value } : l))} /></td>
                          <td><input type="number" step="0.01" min="0" className="inp mono" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={line.credit} placeholder="0.00" onChange={(e) => setLines((ls) => ls.map((l, j) => j === i ? { ...l, credit: e.target.value } : l))} /></td>
                          <td><input type="text" className="inp" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={line.memo} onChange={(e) => setLines((ls) => ls.map((l, j) => j === i ? { ...l, memo: e.target.value } : l))} /></td>
                          <td><button className="icon-btn" style={{ color: 'var(--red)' }} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}><SvgIcon name="x" size={12} /></button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="row gap-3 mt-3">
                  <button className="btn btn-ghost btn-sm" onClick={() => setLines((ls) => [...ls, { acct: '', debit: '', credit: '', memo: '' }])}>
                    <SvgIcon name="plus" size={12} /> Add Line
                  </button>
                  {balanceIndicator()}
                </div>
                <button className="btn btn-primary btn-sm mt-3" disabled={postManualEntry.isPending} onClick={() => postManualEntry.mutate()}>
                  {postManualEntry.isPending ? 'Posting…' : 'Post Entry'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )

  /* Embedded mode: skip Layout + PageHeader */
  if (embedded) {
    return (
      <div className="stack gap-4">
        <div className="spread mb-2">
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em' }}>Journal</div>
            <div className="muted" style={{ fontSize: 12.5 }}>Review extracted transactions and posted entries for this period</div>
          </div>
          <div className="row gap-2">
            {canEdit && has_unclassified && (
              <button className="btn btn-secondary btn-sm" disabled={classify.isPending} onClick={() => classify.mutate()}>
                <SvgIcon name="sparkles" size={13} />{classify.isPending ? 'Classifying…' : 'Classify with AI'}
              </button>
            )}
            {canEdit && approved.length > 0 && (
              <button className="btn btn-primary btn-sm" disabled={post.isPending} onClick={() => post.mutate()}>
                {post.isPending ? 'Posting…' : 'Post All Approved →'}
              </button>
            )}
          </div>
        </div>
        {content}
        {confirmDialog}
      </div>
    )
  }

  return (
    <Layout activePeriod={period}>
      <div className="page">
        <PageHeader
          eyebrow={fmtPeriod(period.period_start)}
          title="Journal"
          subtitle="Classify transactions and post to the ledger"
          backTo={`/periods/${periodId}`}
          backLabel={fmtPeriod(period.period_start)}
          badge={<StatusBadge status={period.status} />}
          actions={
            <div className="row gap-2">
              {canEdit && has_unclassified && (
                <button className="btn btn-secondary btn-sm" disabled={classify.isPending} onClick={() => classify.mutate()}>
                  <SvgIcon name="sparkles" size={13} />{classify.isPending ? 'Classifying…' : 'Classify with AI'}
                </button>
              )}
              {canEdit && approved.length > 0 && (
                <button className="btn btn-primary btn-sm" disabled={post.isPending} onClick={() => post.mutate()}>
                  {post.isPending ? 'Posting…' : 'Post All Approved →'}
                </button>
              )}
              {prev_status && <button className="btn btn-ghost btn-sm" disabled={stepBack.isPending} onClick={() => stepBack.mutate()}>← {fmtStatus(prev_status)}</button>}
              {next_status && <button className="btn btn-secondary btn-sm" disabled={advanceStatus.isPending} onClick={() => advanceStatus.mutate(next_status)}>{fmtStatus(next_status)} →</button>}
            </div>
          }
        />
        <PeriodStepper period={period} />
        <WorkflowHint period={period} page="journal" />
        <div className="mt-4">{content}</div>
      </div>
      {confirmDialog}
    </Layout>
  )
}
