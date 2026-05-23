import { useState, useRef, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPeriodDetail, updatePeriodStatus, stepBackPeriod, reopenPeriod, deletePeriod, orchestrateParse, saveBalances } from '../api/periods'
import { uploadDocument, deleteDocument, parseDocument, unpostDocument, setDocumentSourceAccount } from '../api/documents'
import { addManualTransactions, clearAllTransactions } from '../api/transactions'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import PeriodStepper from '../components/PeriodStepper'
import WorkflowHint from '../components/WorkflowHint'
import Banner from '../components/Banner'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import { fmtPeriod, fmtStatus } from '../utils/format'
import type { OrchestrationResult, StatedBalanceItem } from '../types'

const EDITABLE = (status: string) => status === 'open' || status === 'pending_close'

const STATUS_HINTS: Record<string, string> = {
  open: 'Upload and parse all your documents, then enter your stated balances. Advance when everything is parsed and ready for review.',
  pending_review: 'Open the journal to review extracted transactions — approve or remove as needed. Advance when the journal looks correct.',
  pending_close: 'Post approved journal entries to the ledger from the journal page. Advance to close the period once all entries are posted.',
  closed: 'This period is closed. All journal entries have been posted to the ledger.',
}

export default function PeriodDetailPage() {
  const { periodId } = useParams<{ periodId: string }>()
  const qc = useQueryClient()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<'documents' | 'balances' | 'lifecycle'>('documents')
  const [error, setError] = useState<string | null>(null)
  const PICK_LABEL = 'Choose files (.pdf, .csv, .xlsx)'
  const [pickedFiles, setPickedFiles] = useState<File[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const [balances, setBalances] = useState<Record<number, string>>({})
  const [balancesInitialized, setBalancesInitialized] = useState(false)
  const [orchestrationResult, setOrchestrationResult] = useState<OrchestrationResult | null>(null)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

  // Manual transaction row state
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
      data.balance_accounts.forEach((a) => {
        init[a.account_code] = data.stated_balances[a.account_code] ?? ''
      })
      setBalances(init)
      setBalancesInitialized(true)
    }
  }, [data, balancesInitialized])

  const period = data?.period
  const canEdit = period ? EDITABLE(period.status) : false

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        const fd = new FormData()
        fd.append('file', f)
        await uploadDocument(periodId!, fd)
      }
    },
    onSuccess: () => {
      invalidate()
      setPickedFiles([])
      if (fileRef.current) fileRef.current.value = ''
    },
    onError: (e: Error) => setError(e.message),
  })

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
    mutationFn: ({ docId, code }: { docId: string; code: number | null }) =>
      setDocumentSourceAccount(periodId!, docId, code),
    onSuccess: invalidate,
  })

  const parseAll = useMutation({
    mutationFn: () => orchestrateParse(periodId!),
    onSuccess: (result) => { setOrchestrationResult(result); invalidate() },
    onError: (e: Error) => setError(e.message),
  })

  const saveBalance = useMutation({
    mutationFn: () => {
      const items: StatedBalanceItem[] = Object.entries(balances)
        .filter(([, v]) => v !== '')
        .map(([k, v]) => ({ account_code: parseInt(k, 10), stated_balance: v }))
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
      transactions: txnRows
        .filter((r) => r.date && r.desc && r.amount && r.acct)
        .map((r) => ({ txn_date: r.date, description: r.desc, amount: r.amount, account_code: parseInt(r.acct, 10) })),
    }),
    onSuccess: () => { invalidate(); setTxnRows([{ date: '', desc: '', amount: '', acct: '' }]) },
    onError: (e: Error) => setError(e.message),
  })

  function handleUpload() {
    if (pickedFiles.length === 0) return
    upload.mutate(pickedFiles)
  }

  if (isLoading || !data) return <Layout><p className="color-text3">Loading…</p></Layout>

  const { documents, accounts, balance_accounts, has_pending_documents, posted_doc_ids, staged_count, approved_count, posted_count, transaction_count, next_status, prev_status } = data

  return (
    <Layout activePeriod={period}>
      <PageHeader
        title={period ? fmtPeriod(period.period_start) : ''}
        subtitle={period ? `${period.period_start} → ${period.period_end}` : ''}
        backTo="/periods"
        backLabel="All Periods"
        badge={period && <StatusBadge status={period.status} />}
        right={transaction_count > 0 && (
          <Link to={`/periods/${periodId}/journal`} className="btn btn-secondary btn-sm">
            Review Journal →
          </Link>
        )}
      />

      {error && <Banner variant="red" style={{ marginBottom: 16 }}>{error}</Banner>}

      {period && <PeriodStepper period={period} />}
      {period && <WorkflowHint period={period} page="detail" />}

      <div className="tabs" style={{ marginTop: 16 }}>
        {(['documents', 'balances', 'lifecycle'] as const).map((t) => (
          <button key={t} className={`tab-btn${activeTab === t ? ' tab-btn--active' : ''}`} onClick={() => setActiveTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* ── Documents tab ── */}
      {activeTab === 'documents' && (
        <>
          {canEdit && (
            <div className="card mb-16">
              <div className="card-hd">
                <div>
                  <div className="card-title">Upload Documents</div>
                  <div className="card-sub">Upload your paystubs and statements — the orchestrator will identify each document and its source account when you click Parse.</div>
                </div>
              </div>
              <div className="card-bd-sm">
                <div className="form-row" style={{ alignItems: 'flex-end' }}>
                  <label className={`file-input-label${pickedFiles.length > 0 ? ' file-input-label--has-file' : ''}`}>
                    <SvgIcon name="upload" size={14} />
                    <span>
                      {pickedFiles.length === 0
                        ? PICK_LABEL
                        : pickedFiles.length === 1
                          ? pickedFiles[0].name
                          : `${pickedFiles.length} files selected`}
                    </span>
                    <input
                      ref={fileRef}
                      type="file"
                      multiple
                      accept=".pdf,.csv,.xlsx"
                      onChange={(e) => setPickedFiles(Array.from(e.target.files ?? []))}
                    />
                  </label>
                  <button className="btn btn-primary" disabled={upload.isPending || pickedFiles.length === 0} onClick={handleUpload}>
                    {upload.isPending ? 'Uploading…' : pickedFiles.length > 1 ? `Upload ${pickedFiles.length}` : 'Upload'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">Documents</div>
                <div className="card-sub">{documents.length} uploaded</div>
              </div>
              <div className="card-hd-right">
                {canEdit && has_pending_documents && (
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={parseAll.isPending}
                    onClick={() => { setOrchestrationResult(null); parseAll.mutate() }}
                    title="Identify each document and extract its transactions in one pass"
                  >
                    {parseAll.isPending && <span className="spinner" style={{ marginRight: 6 }} />}
                    {parseAll.isPending ? 'Parsing…' : 'Parse'}
                  </button>
                )}
              </div>
            </div>
            {(parseDoc.isPending || parseAll.isPending) && (
              <div className="progress-bar">
                <div className="progress-bar-track" />
                <div className="progress-bar-fill" />
              </div>
            )}
            {documents.length === 0 ? (
              <EmptyState icon="file" message="No documents uploaded yet." hint={canEdit ? 'Upload PDFs, CSVs, or XLSX files using the form above.' : 'This period is no longer open for uploads.'} />
            ) : (
              <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>File</th><th>Type</th><th>Source Account</th><th>Status</th><th>Uploaded</th><th /></tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.document_id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <SvgIcon name="file" size={14} className="icon color-text3" />
                          <span style={{ fontSize: 13 }}>{doc.file_name}</span>
                        </div>
                      </td>
                      <td className="color-text2" style={{ fontSize: 13 }}>{doc.document_type.replace(/_/g, ' ')}</td>
                      <td style={{ fontSize: 12.5 }}>
                        {canEdit ? (
                          <select
                            className="inp inp--xs"
                            style={{ fontSize: 12, padding: '3px 6px', width: '100%' }}
                            value={doc.source_account_code ?? ''}
                            onChange={(e) => setDocSource.mutate({ docId: doc.document_id, code: e.target.value ? parseInt(e.target.value, 10) : null })}
                          >
                            <option value="">— none —</option>
                            {accounts.map((a) => <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>)}
                          </select>
                        ) : (
                          <span className="mono color-text3">{doc.source_account_code ?? '—'}</span>
                        )}
                      </td>
                      <td>
                        <StatusBadge status={doc.parse_status} />
                        {doc.parsed_at && (
                          <div className="color-text3" style={{ fontSize: 10.5, marginTop: 2 }}>
                            {doc.parsed_at.slice(0, 16)}{doc.llm_model ? ` · ${doc.llm_model}` : ''}
                          </div>
                        )}
                      </td>
                      <td className="color-text3" style={{ fontSize: 12 }}>{doc.created_at.slice(0, 16)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          {canEdit && doc.document_type !== 'manual' && (doc.parse_status === 'pending' || doc.parse_status === 'failed') && (
                            <button
                              className="btn btn-primary btn-sm"
                              disabled={parseDoc.isPending || parseAll.isPending}
                              onClick={() => {
                                if (doc.document_type === 'unknown') {
                                  setOrchestrationResult(null)
                                  parseAll.mutate()
                                } else {
                                  parseDoc.mutate(doc.document_id)
                                }
                              }}
                              style={{ display: 'flex', alignItems: 'center', gap: 5 }}
                            >
                              {((parseDoc.isPending && parseDoc.variables === doc.document_id) || (parseAll.isPending && doc.document_type === 'unknown')) && <span className="spinner" />}
                              Parse
                            </button>
                          )}
                          {canEdit && doc.document_type !== 'manual' && doc.parse_status === 'complete' && (
                            <button className="btn btn-secondary btn-sm" disabled={parseDoc.isPending || parseAll.isPending} onClick={() => { if (window.confirm('Reparse? Existing transactions from this document will be replaced.')) parseDoc.mutate(doc.document_id) }} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                              {parseDoc.isPending && parseDoc.variables === doc.document_id && <span className="spinner" />}
                              Reparse
                            </button>
                          )}
                          {period?.status === 'pending_close' && posted_doc_ids.includes(doc.document_id) && (
                            <button className="btn btn-secondary btn-sm" disabled={unpost.isPending} onClick={() => { if (window.confirm('Unpost all transactions from this document?')) unpost.mutate(doc.document_id) }}>Unpost</button>
                          )}
                          <button className="btn btn-danger btn-sm" disabled={deleteDoc.isPending} onClick={() => { if (window.confirm('Delete this document?')) deleteDoc.mutate(doc.document_id) }}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>

          {orchestrationResult && (
            <div className="card mt-16">
              <div className="card-hd">
                <div>
                  <div className="card-title">Orchestration Result</div>
                  <div className="card-sub">
                    {orchestrationResult.parsed} parsed · {orchestrationResult.failed} failed
                    {orchestrationResult.needs_review > 0 && ` · ${orchestrationResult.needs_review} need review`}
                    {orchestrationResult.classifier_ran && ` · classifier updated ${orchestrationResult.classifier_updated}`}
                  </div>
                </div>
                <div className="card-hd-right">
                  <button className="btn btn-ghost btn-sm" onClick={() => setOrchestrationResult(null)}>Dismiss</button>
                </div>
              </div>
              {orchestrationResult.needs_review > 0 && (
                <Banner variant="amber" style={{ margin: '0 16px 12px' }}>
                  Some documents couldn't be matched to a source account. Pick one from the dropdown in the documents table above, then click Parse on that row.
                </Banner>
              )}
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>File</th><th>Type</th><th>Source Account</th><th>Classifier</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    {orchestrationResult.steps.map((s) => (
                      <tr key={s.document_id}>
                        <td style={{ fontSize: 13 }}>{s.file_name}</td>
                        <td className="color-text2" style={{ fontSize: 12.5 }}>
                          <div>{s.resolved_type.replace(/_/g, ' ')}</div>
                          {s.type_reason && (
                            <div className="color-text3" style={{ fontSize: 11, marginTop: 2 }}>{s.type_reason}</div>
                          )}
                        </td>
                        <td className="color-text2" style={{ fontSize: 12.5 }}>
                          {s.resolved_account_name ? (
                            <div>{s.resolved_source_account_code} · {s.resolved_account_name}</div>
                          ) : (
                            <div className="color-text3">— unresolved —</div>
                          )}
                          {s.source_account_reason && (
                            <div className="color-text3" style={{ fontSize: 11, marginTop: 2 }}>{s.source_account_reason}</div>
                          )}
                        </td>
                        <td style={{ fontSize: 12.5 }}>{s.run_classifier ? 'yes' : '—'}</td>
                        <td>
                          <StatusBadge status={s.status} />
                          {s.error && s.error !== s.source_account_reason && (
                            <div className="color-text3" style={{ fontSize: 11, marginTop: 2 }}>{s.error}</div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {canEdit && (
            <div className="card mt-16">
              <div className="card-hd">
                <div>
                  <div className="card-title">Add Manual Transactions</div>
                  <div className="card-sub">Record transactions not captured in a statement</div>
                </div>
              </div>
              <div className="card-bd-sm">
                <div className="table-scroll">
                <table className="data-table" style={{ marginBottom: 8 }}>
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
                        <td>
                          <button className="btn btn-ghost btn-sm" style={{ padding: '3px 7px', color: 'var(--red)' }} onClick={() => setTxnRows((rs) => rs.filter((_, j) => j !== i))}>
                            <SvgIcon name="x" size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setTxnRows((rs) => [...rs, { date: '', desc: '', amount: '', acct: '' }])}>
                    <SvgIcon name="plus" size={12} /> Add Row
                  </button>
                </div>
                <button className="btn btn-primary btn-sm" disabled={addManual.isPending} onClick={() => addManual.mutate()}>
                  {addManual.isPending ? 'Adding…' : 'Add All'}
                </button>
                <p className="color-text3" style={{ fontSize: 11.5, marginTop: 10 }}>
                  <strong>Negative amount</strong>: outflow. <strong>Positive amount</strong>: inflow.
                </p>
              </div>
            </div>
          )}

          {transaction_count > 0 && (
            <Banner variant="accent" style={{ marginTop: 16 }}>
              {staged_count} staged · {approved_count} approved · {posted_count} posted ·{' '}
              <Link to={`/periods/${periodId}/journal`} className="fw-600" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>
                Review Journal →
              </Link>
            </Banner>
          )}
        </>
      )}

      {/* ── Balances tab ── */}
      {activeTab === 'balances' && (
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">Month-end Stated Balances</div>
              <div className="card-sub">Enter the closing balances from your statements to reconcile against the ledger</div>
            </div>
            {period?.status === 'open' && (
              <div className="card-hd-right">
                <button className="btn btn-primary btn-sm" disabled={saveBalance.isPending} onClick={() => saveBalance.mutate()}>
                  {saveBalance.isPending ? 'Saving…' : 'Save Balances'}
                </button>
              </div>
            )}
          </div>
          <div className="card-bd">
            {balance_accounts.length === 0 ? (
              <p className="color-text3">No balance-sheet accounts configured.</p>
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

      {/* ── Lifecycle tab ── */}
      {activeTab === 'lifecycle' && period && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <div className="card-hd">
              <div>
                <div className="card-title">Progress This Period</div>
                <div className="card-sub">Advance through the workflow when each phase is complete</div>
              </div>
            </div>
            <div className="card-bd">
              <div className="lc-panel">
                <div className="lc-eyebrow">Current phase</div>
                <div className="lc-phase-row">
                  <StatusBadge status={period.status} />
                  <span className="lc-phase-name">{fmtStatus(period.status)}</span>
                </div>
                <p className="lc-hint">{STATUS_HINTS[period.status] ?? ''}</p>

                {next_status && (
                  <button
                    className="btn btn-primary lc-advance-btn"
                    disabled={advanceStatus.isPending}
                    onClick={() => advanceStatus.mutate(next_status)}
                  >
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

                <p className="color-text3" style={{ fontSize: 11.5, marginTop: prev_status ? 10 : 16 }}>
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
                  <div className="summary-stat-sub">{documents.filter((d) => d.parse_status === 'parsed').length} parsed</div>
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
              <div className="card-hd"><div className="card-title">Danger Zone</div></div>
              <div className="card-bd" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {canEdit && (staged_count > 0 || approved_count > 0) && (
                  <div>
                    <button
                      className="btn btn-danger"
                      disabled={clearAll.isPending}
                      onClick={() => { if (window.confirm(`Delete all ${staged_count + approved_count} staged/approved transaction(s)?`)) clearAll.mutate() }}
                    >
                      Clear All Transactions
                    </button>
                    <p className="color-text3" style={{ fontSize: 12, marginTop: 8 }}>Deletes all staged and approved transactions. Posted transactions are not affected.</p>
                  </div>
                )}
                <div>
                  <button
                    className="btn btn-danger"
                    onClick={() => { setDeleteConfirmText(''); setShowDeleteModal(true) }}
                  >
                    Delete Period
                  </button>
                  <p className="color-text3" style={{ fontSize: 12, marginTop: 8 }}>Permanently deletes this period and all related data.</p>
                </div>
              </div>
            </div>
        </div>
      )}
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
                <p className="modal-confirm-label">
                  All documents, transactions, and journal entries for this period will be permanently deleted.
                  Type <strong>{expected}</strong> to confirm.
                </p>
                <input
                  className="inp"
                  placeholder={expected}
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && matches) { del.mutate() } }}
                  autoFocus
                />
              </div>
              <div className="modal-ft">
                <button className="btn btn-ghost btn-sm" onClick={() => setShowDeleteModal(false)}>Cancel</button>
                <button
                  className="btn btn-danger btn-sm"
                  disabled={!matches || del.isPending}
                  onClick={() => del.mutate()}
                >
                  {del.isPending ? 'Deleting…' : 'Delete this period'}
                </button>
              </div>
            </div>
          </div>
        )
      })()}
    </Layout>
  )
}
