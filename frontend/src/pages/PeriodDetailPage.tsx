import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPeriodDetail, updatePeriodStatus, stepBackPeriod, reopenPeriod, deletePeriod, orchestrateParse, saveBalances } from '../api/periods'
import { deleteDocument, parseDocument, unpostDocument, setDocumentSourceAccount } from '../api/documents'
import { addManualTransactions, clearAllTransactions } from '../api/transactions'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import PeriodStepper from '../components/PeriodStepper'
import WorkflowHint from '../components/WorkflowHint'
import Banner from '../components/Banner'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import JournalPage from './JournalPage'
import ReconcilePage from './ReconcilePage'
import { fmtPeriod, fmtStatus } from '../utils/format'
import type { OrchestrationResult, StatedBalanceItem } from '../types'

type Tab = 'documents' | 'journal' | 'balances' | 'reconcile' | 'lifecycle'

const EDITABLE = (status: string) => status === 'open' || status === 'pending_close'

const STATUS_HINTS: Record<string, string> = {
  open: 'Upload and parse all your documents, then enter your stated balances. Advance when everything is parsed and ready for review.',
  pending_review: 'Open the journal tab to review extracted transactions — approve or remove as needed.',
  pending_close: 'Post approved journal entries to the ledger from the journal tab. Then run reconciliation and close.',
  closed: 'This period is closed. All journal entries have been posted to the ledger.',
}

interface ParsingDoc {
  id: string
  name: string
  progress: number
  type: string
}

export default function PeriodDetailPage() {
  const { periodId } = useParams<{ periodId: string }>()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<Tab>('documents')
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [parsing, setParsing] = useState<ParsingDoc[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [balances, setBalances] = useState<Record<number, string>>({})
  const [balancesInitialized, setBalancesInitialized] = useState(false)
  const [orchestrationResult, setOrchestrationResult] = useState<OrchestrationResult | null>(null)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [txnRows, setTxnRows] = useState([{ date: '', desc: '', amount: '', acct: '' }])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['period', periodId] })

  const { data, isLoading } = useQuery({
    queryKey: ['period', periodId],
    queryFn: () => fetchPeriodDetail(periodId!),
    staleTime: 30_000,
    enabled: !!periodId,
  })

  useEffect(() => {
    if (data && !balancesInitialized) {
      const init: Record<number, string> = {}
      data.balance_accounts.forEach((a) => { init[a.account_code] = data.stated_balances[a.account_code] ?? '' })
      setBalances(init)
      setBalancesInitialized(true)
    }
  }, [data, balancesInitialized])

  const period = data?.period
  const canEdit = period ? EDITABLE(period.status) : false

  // File handling with progress simulation for drag-drop UX
  const handleFiles = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files)
    const guesses = arr.map((f) => {
      const lower = f.name.toLowerCase()
      let type = 'bank_statement'
      if (lower.includes('paystub') || lower.includes('payroll')) type = 'paystub'
      else if (lower.includes('mortgage')) type = 'mortgage'
      else if (lower.includes('amex') || lower.includes('chase') || lower.includes('credit')) type = 'credit_card'
      else if (lower.includes('fidelity') || lower.includes('vanguard') || lower.includes('schwab')) type = 'investment'
      return { id: `p-${Math.random().toString(36).slice(2, 8)}`, name: f.name, progress: 0, type }
    })
    setParsing((p) => [...p, ...guesses])

    // Upload the actual files
    const uploadMut = async () => {
      for (const [idx, f] of arr.entries()) {
        const gId = guesses[idx].id
        const start = Date.now()
        const duration = 1200 + Math.random() * 1600

        // Simulate progress while uploading
        const tick = () => {
          const elapsed = Date.now() - start
          const pct = Math.min(95, (elapsed / duration) * 100)
          setParsing((cur) => cur.map((c) => c.id === gId ? { ...c, progress: pct } : c))
          if (pct < 95) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)

        const fd = new FormData()
        fd.append('file', f)
        try {
          await (await import('../api/documents')).uploadDocument(periodId!, fd)
          setParsing((cur) => cur.map((c) => c.id === gId ? { ...c, progress: 100 } : c))
          setTimeout(() => {
            setParsing((cur) => cur.filter((c) => c.id !== gId))
            invalidate()
          }, 500)
        } catch {
          setParsing((cur) => cur.filter((c) => c.id !== gId))
          setError('Failed to upload file.')
        }
      }
    }
    uploadMut()
  }, [periodId])

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files)
  }

  const deleteDoc = useMutation({
    mutationFn: (docId: string) => deleteDocument(periodId!, docId),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const parseDoc = useMutation({
    mutationFn: (docId: string) => parseDocument(periodId!, docId),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const unpost = useMutation({
    mutationFn: (docId: string) => unpostDocument(periodId!, docId),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const setDocSource = useMutation({
    mutationFn: ({ docId, code }: { docId: string; code: number | null }) => setDocumentSourceAccount(periodId!, docId, code),
    onSuccess: invalidate,
  })
  const parseAll = useMutation({
    mutationFn: () => orchestrateParse(periodId!),
    onSuccess: (result) => { setOrchestrationResult(result); invalidate() },
    onError: (e: Error) => setError(e.message),
  })
  const saveBalance = useMutation({
    mutationFn: () => {
      const items: StatedBalanceItem[] = Object.entries(balances).filter(([, v]) => v !== '').map(([k, v]) => ({ account_code: parseInt(k, 10), stated_balance: v }))
      return saveBalances(periodId!, items)
    },
    onError: (e: Error) => setError(e.message),
  })
  const advanceStatus = useMutation({
    mutationFn: (s: string) => updatePeriodStatus(periodId!, s),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const stepBack = useMutation({
    mutationFn: () => stepBackPeriod(periodId!),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const reopen = useMutation({
    mutationFn: () => reopenPeriod(periodId!),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const clearAll = useMutation({
    mutationFn: () => clearAllTransactions(periodId!),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  })
  const del = useMutation({
    mutationFn: () => deletePeriod(periodId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['periods'] }); navigate('/periods') },
    onError: (e: Error) => setError(e.message),
  })
  const addManual = useMutation({
    mutationFn: () => addManualTransactions(periodId!, {
      transactions: txnRows.filter((r) => r.date && r.desc && r.amount && r.acct).map((r) => ({ txn_date: r.date, description: r.desc, amount: r.amount, account_code: parseInt(r.acct, 10) })),
    }),
    onSuccess: () => { invalidate(); setTxnRows([{ date: '', desc: '', amount: '', acct: '' }]) },
    onError: (e: Error) => setError(e.message),
  })

  if (isLoading || !data) return <Layout><p className="muted">Loading…</p></Layout>

  const { documents, accounts, balance_accounts, has_pending_documents, posted_doc_ids, staged_count, approved_count, posted_count, transaction_count, next_status, prev_status } = data

  return (
    <Layout activePeriod={period}>
      <div className="page">
        <Link to="/periods" className="btn btn-ghost btn-sm" style={{ marginBottom: 12, marginLeft: -8 }}>
          <SvgIcon name="arrowLeft" size={14} /> All periods
        </Link>

        <PageHeader
          eyebrow="Workflow"
          title={period ? fmtPeriod(period.period_start) : ''}
          subtitle={period ? `${period.period_start} → ${period.period_end}` : ''}
          badge={period && <StatusBadge status={period.status} />}
          actions={
            <div className="row gap-2">
              <Link to={`/periods/${periodId}/close`} className="btn btn-primary">
                <SvgIcon name="zap" size={14} /> Guided close
              </Link>
              <button className="btn btn-secondary"><SvgIcon name="more" size={14} /></button>
            </div>
          }
        />

        {error && <Banner variant="red" style={{ marginBottom: 16 }}>{error}</Banner>}

        {period && (
          <div className="mb-4">
            <PeriodStepper period={period} />
          </div>
        )}

        {period && <WorkflowHint period={period} page="detail" />}

        <div className="tabs">
          {(['documents', 'journal', 'balances', 'reconcile', 'lifecycle'] as Tab[]).map((t) => (
            <button key={t} className={`tab${activeTab === t ? ' active' : ''}`} onClick={() => setActiveTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {t === 'journal' && transaction_count > 0 && (
                <span className="mono muted" style={{ marginLeft: 5, fontSize: 11 }}>{transaction_count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Documents tab */}
        {activeTab === 'documents' && (
          <>
            {canEdit && (
              <div
                className={`dropzone ${dragging ? 'dragging' : ''}`}
                style={{ marginBottom: 16 }}
                onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                onDragEnter={(e) => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="dropzone-icon"><SvgIcon name="upload" size={20} /></div>
                <div className="dropzone-title">Drop statements, paystubs, or mortgage docs</div>
                <div className="dropzone-hint">PDF, CSV, or XLSX · We'll auto-detect type and route to the right AI agent</div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.csv,.xlsx"
                  style={{ display: 'none' }}
                  onChange={(e) => { if (e.target.files) handleFiles(e.target.files) }}
                />
                <div className="mt-3 row gap-3" style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  <span className="row gap-2"><SvgIcon name="sparkles" size={12} /> Orchestrator routes per-document</span>
                  <span style={{ opacity: 0.4 }}>·</span>
                  <span>Classifier auto-runs after parse</span>
                </div>
              </div>
            )}

            {/* Parsing in-flight */}
            {parsing.length > 0 && (
              <div className="card mb-4">
                <div className="card-hd">
                  <div>
                    <div className="card-title row gap-2">
                      <span className="parsing-dots"><span/><span/><span/></span>
                      Uploading {parsing.length} file{parsing.length > 1 ? 's' : ''}
                    </div>
                    <div className="card-sub">Uploading and queuing for parse</div>
                  </div>
                </div>
                <div className="card-bd-flush">
                  {parsing.map((p) => (
                    <div className="doc-row" key={p.id}>
                      <div className="doc-icon" style={{ color: 'var(--accent)' }}><SvgIcon name="pdf" size={16} /></div>
                      <div>
                        <div className="doc-name">{p.name}</div>
                        <div className="doc-meta row gap-2">
                          <span className="badge badge--accent">{p.progress < 35 ? 'Uploading' : p.progress < 75 ? 'Processing' : 'Finishing'}</span>
                        </div>
                      </div>
                      <div className="doc-bar">
                        <div className="doc-bar-fill" style={{ transform: `scaleX(${p.progress / 100})` }} />
                        <div className="parsing-shimmer" />
                      </div>
                      <div className="mono muted" style={{ fontSize: 11.5 }}>{Math.floor(p.progress)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Document list */}
            <div className="card">
              <div className="card-hd">
                <div>
                  <div className="card-title">Uploaded documents</div>
                  <div className="card-sub">{documents.length} total · {documents.filter(d => d.parse_status === 'parsed' || d.parse_status === 'complete').length} parsed</div>
                </div>
                <div className="row gap-2">
                  {canEdit && has_pending_documents && (
                    <button className="btn btn-secondary btn-sm" disabled={parseAll.isPending} onClick={() => { setOrchestrationResult(null); parseAll.mutate() }}>
                      {parseAll.isPending && <span className="spinner" />}
                      {parseAll.isPending ? 'Parsing…' : 'Parse all'}
                    </button>
                  )}
                </div>
              </div>
              {(parseDoc.isPending || parseAll.isPending) && <div className="progress-bar"><div className="progress-bar-fill" /></div>}
              {documents.length === 0 ? (
                <EmptyState icon="file" message="No documents uploaded yet." hint={canEdit ? 'Drag-and-drop PDFs or click the upload area above.' : 'This period is no longer open for uploads.'} />
              ) : (
                <div className="card-bd-flush">
                  {documents.map((doc) => (
                    <div className="doc-row" key={doc.document_id}>
                      <div className="doc-icon"><SvgIcon name={doc.file_name.endsWith('.csv') ? 'csv' : 'pdf'} size={16} /></div>
                      <div>
                        <div className="doc-name">{doc.file_name}</div>
                        <div className="doc-meta row gap-2">
                          <span className="badge badge--ghost">{doc.document_type.replace(/_/g, ' ')}</span>
                          {canEdit ? (
                            <select
                              className="inp inp--xs"
                              style={{ fontSize: 12, width: 'auto', minWidth: 180 }}
                              value={doc.source_account_code ?? ''}
                              onChange={(e) => setDocSource.mutate({ docId: doc.document_id, code: e.target.value ? parseInt(e.target.value, 10) : null })}
                            >
                              <option value="">— source account —</option>
                              {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
                            </select>
                          ) : (
                            <span className="muted">→ {doc.source_account_code ?? '—'}</span>
                          )}
                        </div>
                      </div>
                      <StatusBadge status={doc.parse_status} />
                      <div className="row gap-2">
                        {canEdit && doc.document_type !== 'manual' && (doc.parse_status === 'pending' || doc.parse_status === 'failed') && (
                          <button className="btn btn-primary btn-sm" disabled={parseDoc.isPending || parseAll.isPending} onClick={() => { if (doc.document_type === 'unknown') parseAll.mutate(); else parseDoc.mutate(doc.document_id) }}>
                            {parseDoc.isPending && parseDoc.variables === doc.document_id && <span className="spinner" />}
                            Parse
                          </button>
                        )}
                        {canEdit && doc.document_type !== 'manual' && (doc.parse_status === 'parsed' || doc.parse_status === 'complete') && (
                          <button className="btn btn-secondary btn-sm" disabled={parseDoc.isPending || parseAll.isPending} onClick={() => { if (window.confirm('Reparse? Existing transactions will be replaced.')) parseDoc.mutate(doc.document_id) }}>
                            Reparse
                          </button>
                        )}
                        {period?.status === 'pending_close' && posted_doc_ids.includes(doc.document_id) && (
                          <button className="btn btn-secondary btn-sm" disabled={unpost.isPending} onClick={() => { if (window.confirm('Unpost all transactions from this document?')) unpost.mutate(doc.document_id) }}>Unpost</button>
                        )}
                        <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)' }} disabled={deleteDoc.isPending} onClick={() => { if (window.confirm('Delete this document?')) deleteDoc.mutate(doc.document_id) }}>
                          <SvgIcon name="trash" size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {orchestrationResult && (
              <div className="card mt-4">
                <div className="card-hd">
                  <div>
                    <div className="card-title">Orchestration Result</div>
                    <div className="card-sub">{orchestrationResult.parsed} parsed · {orchestrationResult.failed} failed{orchestrationResult.needs_review > 0 ? ` · ${orchestrationResult.needs_review} need review` : ''}</div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={() => setOrchestrationResult(null)}>Dismiss</button>
                </div>
                <div className="tbl-scroll">
                  <table className="tbl">
                    <thead><tr><th>File</th><th>Type</th><th>Source Account</th><th>Status</th></tr></thead>
                    <tbody>
                      {orchestrationResult.steps.map((s) => (
                        <tr key={s.document_id}>
                          <td style={{ fontSize: 13 }}>{s.file_name}</td>
                          <td className="muted" style={{ fontSize: 12.5 }}>
                            <div>{s.resolved_type.replace(/_/g, ' ')}</div>
                            {s.type_reason && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{s.type_reason}</div>}
                          </td>
                          <td className="muted" style={{ fontSize: 12.5 }}>
                            {s.resolved_account_name ? `${s.resolved_source_account_code} · ${s.resolved_account_name}` : <span className="muted">— unresolved —</span>}
                          </td>
                          <td><StatusBadge status={s.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Manual transactions */}
            {canEdit && (
              <div className="card mt-4">
                <div className="card-hd">
                  <div>
                    <div className="card-title">Add Manual Transactions</div>
                    <div className="card-sub">Record transactions not captured in a statement</div>
                  </div>
                </div>
                <div className="card-bd-sm">
                  <div className="tbl-scroll">
                    <table className="tbl" style={{ marginBottom: 8 }}>
                      <thead>
                        <tr><th style={{ width: 140 }}>Date</th><th>Description</th><th style={{ width: 120 }}>Amount</th><th style={{ width: 240 }}>Account</th><th style={{ width: 36 }} /></tr>
                      </thead>
                      <tbody>
                        {txnRows.map((row, i) => (
                          <tr key={i}>
                            <td><input type="date" className="inp" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={row.date} onChange={(e) => setTxnRows((rs) => rs.map((r, j) => j === i ? { ...r, date: e.target.value } : r))} /></td>
                            <td><input type="text" className="inp" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} placeholder="e.g. Mortgage Payment" value={row.desc} onChange={(e) => setTxnRows((rs) => rs.map((r, j) => j === i ? { ...r, desc: e.target.value } : r))} /></td>
                            <td><input type="number" className="inp mono" step="0.01" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} placeholder="-1234.56" value={row.amount} onChange={(e) => setTxnRows((rs) => rs.map((r, j) => j === i ? { ...r, amount: e.target.value } : r))} /></td>
                            <td>
                              <select className="inp" style={{ fontSize: 12, padding: '4px 8px', width: '100%' }} value={row.acct} onChange={(e) => setTxnRows((rs) => rs.map((r, j) => j === i ? { ...r, acct: e.target.value } : r))}>
                                <option value="">— account —</option>
                                {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
                              </select>
                            </td>
                            <td><button className="icon-btn" style={{ color: 'var(--red)' }} onClick={() => setTxnRows((rs) => rs.filter((_, j) => j !== i))}><SvgIcon name="x" size={12} /></button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="row gap-3 mb-3">
                    <button className="btn btn-ghost btn-sm" onClick={() => setTxnRows((rs) => [...rs, { date: '', desc: '', amount: '', acct: '' }])}>
                      <SvgIcon name="plus" size={12} /> Add Row
                    </button>
                  </div>
                  <button className="btn btn-primary btn-sm" disabled={addManual.isPending} onClick={() => addManual.mutate()}>
                    {addManual.isPending ? 'Adding…' : 'Add All'}
                  </button>
                  <p className="muted mt-2" style={{ fontSize: 11.5 }}><strong>Negative amount</strong>: outflow. <strong>Positive amount</strong>: inflow.</p>
                </div>
              </div>
            )}

            {transaction_count > 0 && (
              <Banner variant="accent" style={{ marginTop: 16 }}>
                {staged_count} staged · {approved_count} approved · {posted_count} posted ·{' '}
                <button className="fw-600" style={{ color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', fontSize: 'inherit' }} onClick={() => setActiveTab('journal')}>
                  Review Journal →
                </button>
              </Banner>
            )}
          </>
        )}

        {/* Journal tab (embedded) */}
        {activeTab === 'journal' && <JournalPage embedded periodId={periodId} />}

        {/* Balances tab */}
        {activeTab === 'balances' && (
          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">Month-end Stated Balances</div>
                <div className="card-sub">Enter the closing balances from your statements to reconcile against the ledger</div>
              </div>
              {period?.status === 'open' && (
                <button className="btn btn-primary btn-sm" disabled={saveBalance.isPending} onClick={() => saveBalance.mutate()}>
                  {saveBalance.isPending ? 'Saving…' : <><SvgIcon name="check" size={13} /> Save balances</>}
                </button>
              )}
            </div>
            <div className="card-bd">
              {balance_accounts.length === 0 ? (
                <p className="muted">No balance-sheet accounts configured.</p>
              ) : (
                <div className="balance-grid">
                  {balance_accounts.map((a) => (
                    <div key={a.account_code} className="balance-row">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="balance-account-name">{a.account_name}</div>
                        <div className="balance-account-sub">{a.account_code} · {a.sub_category}</div>
                      </div>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="0.00"
                        className="inp balance-inp"
                        value={balances[a.account_code] ?? ''}
                        disabled={period?.status !== 'open'}
                        onChange={(e) => setBalances((prev) => ({ ...prev, [a.account_code]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Reconcile tab (embedded) */}
        {activeTab === 'reconcile' && <ReconcilePage embedded periodId={periodId} />}

        {/* Lifecycle tab */}
        {activeTab === 'lifecycle' && period && (
          <div className="stack gap-4">
            <div className="card">
              <div className="card-hd"><div><div className="card-title">Progress This Period</div><div className="card-sub">Advance through the workflow when each phase is complete</div></div></div>
              <div className="card-bd">
                <div className="lc-panel">
                  <div className="lc-eyebrow">Current phase</div>
                  <div className="lc-phase-row">
                    <StatusBadge status={period.status} />
                    <span className="lc-phase-name">{fmtStatus(period.status)}</span>
                  </div>
                  <p className="lc-hint">{STATUS_HINTS[period.status] ?? ''}</p>
                  {next_status && (
                    <button className="btn btn-primary lc-advance-btn" disabled={advanceStatus.isPending} onClick={() => advanceStatus.mutate(next_status)}>
                      <span>{advanceStatus.isPending ? 'Advancing…' : `Advance to ${fmtStatus(next_status)}`}</span>
                      <span>→</span>
                    </button>
                  )}
                  {period.status === 'closed' && (
                    <button className="btn btn-secondary" disabled={reopen.isPending} onClick={() => reopen.mutate()}>
                      Reopen Period
                    </button>
                  )}
                  {prev_status && (
                    <div className="lc-back-row">
                      <span className="lc-back-label">Need to go back?</span>
                      <button className="btn btn-ghost btn-sm" disabled={stepBack.isPending} onClick={() => stepBack.mutate()}>
                        ← Back to {fmtStatus(prev_status)}
                      </button>
                    </div>
                  )}
                  <p className="muted mt-4" style={{ fontSize: 11.5 }}>
                    Started {period.period_start}
                    {period.closed_at && ` · Closed ${period.closed_at.slice(0, 16)} UTC`}
                  </p>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-hd"><div className="card-title">Period Summary</div></div>
              <div className="card-bd">
                <div className="summary-stats">
                  <div className="summary-stat">
                    <div className="summary-stat-value">{documents.length}</div>
                    <div className="summary-stat-label">Documents</div>
                    <div className="summary-stat-sub">{documents.filter(d => d.parse_status === 'parsed' || d.parse_status === 'complete').length} parsed</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-stat-value">{transaction_count}</div>
                    <div className="summary-stat-label">Transactions</div>
                    <div className="summary-stat-sub">{approved_count} approved · {staged_count} staged</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-stat-value">{posted_count}</div>
                    <div className="summary-stat-label">Journal Entries</div>
                    <div className="summary-stat-sub">Posted to ledger</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-hd"><div className="card-title" style={{ color: 'var(--red)' }}>Danger Zone</div></div>
              <div className="card-bd stack gap-4">
                {canEdit && (staged_count > 0 || approved_count > 0) && (
                  <div>
                    <button className="btn btn-danger" disabled={clearAll.isPending} onClick={() => { if (window.confirm(`Delete all ${staged_count + approved_count} staged/approved transaction(s)?`)) clearAll.mutate() }}>
                      Clear All Transactions
                    </button>
                    <p className="muted mt-2" style={{ fontSize: 12 }}>Deletes all staged and approved transactions. Posted transactions are not affected.</p>
                  </div>
                )}
                <div>
                  <button className="btn btn-danger" onClick={() => { setDeleteConfirmText(''); setShowDeleteModal(true) }}>Delete Period</button>
                  <p className="muted mt-2" style={{ fontSize: 12 }}>Permanently deletes this period and all related data.</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Delete modal */}
        {showDeleteModal && period && (() => {
          const expected = fmtPeriod(period.period_start)
          const matches = deleteConfirmText === expected
          return (
            <div className="modal-backdrop" onClick={() => setShowDeleteModal(false)}>
              <div className="modal" onClick={(e) => e.stopPropagation()}>
                <div className="modal-hd">
                  <div className="modal-title">Delete period</div>
                  <div className="modal-sub">This action cannot be undone.</div>
                </div>
                <div className="modal-bd">
                  <p className="modal-confirm-label">All documents, transactions, and journal entries for this period will be permanently deleted. Type <strong>{expected}</strong> to confirm.</p>
                  <input className="inp" style={{ width: '100%' }} placeholder={expected} value={deleteConfirmText} onChange={(e) => setDeleteConfirmText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && matches) del.mutate() }} autoFocus />
                </div>
                <div className="modal-ft">
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowDeleteModal(false)}>Cancel</button>
                  <button className="btn btn-danger btn-sm" disabled={!matches || del.isPending} onClick={() => del.mutate()}>
                    {del.isPending ? 'Deleting…' : 'Delete this period'}
                  </button>
                </div>
              </div>
            </div>
          )
        })()}
      </div>
    </Layout>
  )
}
