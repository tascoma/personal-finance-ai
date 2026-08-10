import { useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPeriodDetail, updatePeriodStatus, saveBalances } from '../api/periods'
import { orchestrateParseStream } from '../api/periods'
import { fetchJournalPage, classifyTransactions, postTransactions, createManualJournalEntry } from '../api/journal'
import type { OrchestrationEvent, ManualJournalEntryCreate } from '../types'
import { approveAllStaged, approveTransaction, updateTransactionAccount, rejectTransaction } from '../api/transactions'
import { fetchReconcilePage, runReconciliation, postUnrealizedGl, postClosingEntries, postEquityRollup } from '../api/reconciliation'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import SvgIcon from '../components/SvgIcon'
import { useConfirm } from '../hooks/useConfirm'
import { useToast } from '../contexts/ToastContext'
import ConfidencePill from '../components/ConfidencePill'
import { fmtPeriod, fmtDebitCredit } from '../utils/format'

const WIZARD_STEPS = [
  { key: 'docs',      name: 'Documents parsed',      hint: 'All statements uploaded' },
  { key: 'classify',  name: 'Approve transactions',  hint: 'Review extracted data' },
  { key: 'journal',   name: 'Review journal entries', hint: 'Inspect posted entries' },
  { key: 'balances',  name: 'Stated balances',       hint: 'Enter month-end amounts' },
  { key: 'reconcile', name: 'Reconcile',             hint: 'Verify account gaps' },
  { key: 'post',      name: 'Post & close',          hint: 'Final review' },
]

type ParseLogEntry = { label: string; detail?: string; status: 'running' | 'done' | 'error' | 'warn' }
type LineDraft = { account_code: string; debit: string; credit: string; memo: string }
const blankLine = (): LineDraft => ({ account_code: '', debit: '', credit: '', memo: '' })

function handleEvent(
  ev: OrchestrationEvent,
  append: (e: ParseLogEntry) => void,
  updateLast: (patch: Partial<ParseLogEntry>) => void,
) {
  switch (ev.event) {
    case 'planning':
      append({ label: 'Planning documents…', status: 'running' })
      break
    case 'planned':
      updateLast({ label: `Routing ${ev.doc_count} document${ev.doc_count === 1 ? '' : 's'}`, status: 'done' })
      break
    case 'parsing':
      append({ label: `${ev.file_name}`, detail: `${ev.index} of ${ev.total}`, status: 'running' })
      break
    case 'parsed':
      if (ev.status === 'complete') {
        updateLast({
          status: 'done',
          detail: ev.txn_count != null ? `${ev.txn_count} transaction${ev.txn_count === 1 ? '' : 's'}` : undefined,
        })
      } else if (ev.status === 'needs_review') {
        updateLast({ status: 'warn', detail: 'needs review — no source account matched' })
      } else {
        updateLast({ status: 'error', detail: 'failed' })
      }
      break
    case 'classifying':
      append({ label: 'Classifying transactions…', status: 'running' })
      break
    case 'complete':
      if (ev.classifier_ran) {
        updateLast({ status: 'done', detail: `${ev.classifier_updated} transaction${ev.classifier_updated === 1 ? '' : 's'} classified` })
      }
      break
    case 'error':
      updateLast({ status: 'error' })
      append({ label: ev.message ?? 'An error occurred', status: 'error' })
      break
  }
}

export default function CloseWizardPage() {
  const { periodId } = useParams<{ periodId: string }>()
  const qc = useQueryClient()
  const { ask, confirmDialog } = useConfirm()
  const toast = useToast()
  const [step, setStep] = useState(0)
  const [completed, setCompleted] = useState<Record<number, boolean>>({})
  const [balanceValues, setBalanceValues] = useState<Record<number, string>>({})
  const [reconError, setReconError] = useState<string | null>(null)
  const [showEntryForm, setShowEntryForm] = useState(false)
  const [entryDate, setEntryDate] = useState('')
  const [entryDesc, setEntryDesc] = useState('')
  const [entryLines, setEntryLines] = useState<LineDraft[]>([blankLine(), blankLine()])
  const [entryError, setEntryError] = useState<string | null>(null)

  const invalidatePeriod = () => qc.invalidateQueries({ queryKey: ['period', periodId] })

  const { data: periodData, isLoading: periodLoading } = useQuery({
    queryKey: ['period', periodId],
    queryFn: () => fetchPeriodDetail(periodId!),
    staleTime: 30_000,
    enabled: !!periodId,
  })
  const { data: journalData } = useQuery({
    queryKey: ['journal', periodId],
    queryFn: () => fetchJournalPage(periodId!),
    staleTime: 30_000,
    enabled: !!periodId && step >= 1,
  })
  const { data: reconData } = useQuery({
    queryKey: ['reconcile', periodId],
    queryFn: () => fetchReconcilePage(periodId!),
    staleTime: 30_000,
    enabled: !!periodId && step >= 4,
  })

  const [parseLog, setParseLog] = useState<ParseLogEntry[]>([])
  const [isParsing, setIsParsing] = useState(false)

  const handleParse = useCallback(async () => {
    setIsParsing(true)
    setParseLog([])
    const append = (entry: ParseLogEntry) => setParseLog(prev => [...prev, entry])
    const updateLast = (patch: Partial<ParseLogEntry>) =>
      setParseLog(prev => prev.length === 0 ? prev : [...prev.slice(0, -1), { ...prev[prev.length - 1], ...patch }])

    try {
      for await (const ev of orchestrateParseStream(periodId!)) {
        handleEvent(ev, append, updateLast)
      }
      qc.invalidateQueries({ queryKey: ['period', periodId] })
    } catch (e) {
      updateLast({ status: 'error' })
      append({ label: e instanceof Error ? e.message : 'Unexpected error', status: 'error' })
    } finally {
      setIsParsing(false)
    }
  }, [periodId, qc])
  const classify = useMutation({
    mutationFn: () => classifyTransactions(periodId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['journal', periodId] }) },
    onError: (e: Error) => toast.error(`Classification failed: ${e.message}`),
  })
  const approveAll = useMutation({
    mutationFn: () => approveAllStaged(periodId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['journal', periodId] }) },
    onError: (e: Error) => toast.error(`Could not approve transactions: ${e.message}`),
  })
  const postTxns = useMutation({
    mutationFn: async () => {
      const status = periodData?.period.status
      if (status === 'open') {
        await updatePeriodStatus(periodId!, 'pending_review')
        await updatePeriodStatus(periodId!, 'pending_close')
      } else if (status === 'pending_review') {
        await updatePeriodStatus(periodId!, 'pending_close')
      }
      return postTransactions(periodId!)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['journal', periodId] })
      qc.invalidateQueries({ queryKey: ['period', periodId] })
      toast.success('Transactions posted')
    },
    onError: (e: Error) => toast.error(`Could not post transactions: ${e.message}`),
  })
  const updateAccount = useMutation({
    mutationFn: ({ txnId, accountCode }: { txnId: string; accountCode: number }) =>
      updateTransactionAccount(periodId!, txnId, accountCode),
    onMutate: async ({ txnId, accountCode }) => {
      await qc.cancelQueries({ queryKey: ['journal', periodId] })
      const prev = qc.getQueryData(['journal', periodId])
      qc.setQueryData(['journal', periodId], (old: typeof journalData) => {
        if (!old) return old
        const patch = (list: typeof old.staged) =>
          list.map(t => t.raw_txn_id === txnId ? { ...t, suggested_account_code: accountCode } : t)
        return { ...old, staged: patch(old.staged), approved: patch(old.approved) }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['journal', periodId], ctx.prev)
    },
    onSettled: () => { qc.invalidateQueries({ queryKey: ['journal', periodId] }) },
  })
  const removeTransaction = useMutation({
    mutationFn: (txnId: string) => rejectTransaction(periodId!, txnId),
    onMutate: async (txnId) => {
      await qc.cancelQueries({ queryKey: ['journal', periodId] })
      const prev = qc.getQueryData(['journal', periodId])
      qc.setQueryData(['journal', periodId], (old: typeof journalData) => {
        if (!old) return old
        return {
          ...old,
          staged: old.staged.filter(t => t.raw_txn_id !== txnId),
          approved: old.approved.filter(t => t.raw_txn_id !== txnId),
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['journal', periodId], ctx.prev)
    },
  })
  const approveSingle = useMutation({
    mutationFn: (txnId: string) => approveTransaction(periodId!, txnId),
    onMutate: async (txnId) => {
      await qc.cancelQueries({ queryKey: ['journal', periodId] })
      const prev = qc.getQueryData(['journal', periodId])
      qc.setQueryData(['journal', periodId], (old: typeof journalData) => {
        if (!old) return old
        const txn = old.staged.find(t => t.raw_txn_id === txnId)
        if (!txn) return old
        return {
          ...old,
          staged: old.staged.filter(t => t.raw_txn_id !== txnId),
          approved: [...old.approved, { ...txn, status: 'approved' }],
        }
      })
      return { prev }
    },
    onSuccess: (updated, txnId) => {
      qc.setQueryData(['journal', periodId], (old: typeof journalData) => {
        if (!old) return old
        return {
          ...old,
          approved: old.approved.map(t => t.raw_txn_id === txnId ? updated : t),
        }
      })
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['journal', periodId], ctx.prev)
    },
  })
  const saveBalancesMut = useMutation({
    mutationFn: () => saveBalances(
      periodId!,
      (periodData?.balance_accounts ?? []).map(a => ({
        account_code: a.account_code,
        stated_balance: balanceValues[a.account_code] ?? (periodData?.stated_balances[a.account_code] ?? '0'),
      })),
    ),
    onSuccess: () => toast.success('Stated balances saved'),
    onError: (e: Error) => toast.error(`Could not save balances: ${e.message}`),
  })
  const runRecon = useMutation({
    mutationFn: () => runReconciliation(periodId!),
    onSuccess: (d) => { setReconError(null); qc.setQueryData(['reconcile', periodId], d) },
    onError: (e: Error) => setReconError(e.message),
  })
  const postUnrealized = useMutation({
    mutationFn: (code: number) => postUnrealizedGl(periodId!, code),
    onSuccess: (d) => { setReconError(null); qc.setQueryData(['reconcile', periodId], d) },
    onError: (e: Error) => setReconError(e.message),
  })
  const postClosing = useMutation({
    mutationFn: async () => {
      await postClosingEntries(periodId!)
      return postEquityRollup(periodId!)
    },
    onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d),
    onError: (e: Error) => toast.error(`Could not post closing entries: ${e.message}`),
  })
  const closePeriod = useMutation({
    mutationFn: () => updatePeriodStatus(periodId!, 'closed'),
    onSuccess: () => { invalidatePeriod(); setCompleted((c) => ({ ...c, 5: true })); toast.success('Period closed') },
    onError: (e: Error) => toast.error(`Could not close the period: ${e.message}`),
  })

  const addEntry = useMutation({
    mutationFn: (body: ManualJournalEntryCreate) => createManualJournalEntry(periodId!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['journal', periodId] })
      setShowEntryForm(false)
      setEntryDate('')
      setEntryDesc('')
      setEntryLines([blankLine(), blankLine()])
      setEntryError(null)
    },
    onError: (e: Error) => setEntryError(e.message),
  })

  function handleSubmitEntry() {
    if (!entryDate || !entryDesc.trim()) {
      setEntryError('Date and description are required')
      return
    }
    if (entryLines.some(l => !l.account_code)) {
      setEntryError('All lines must have an account selected')
      return
    }
    const totalDebit = entryLines.reduce((s, l) => s + parseFloat(l.debit || '0'), 0)
    const totalCredit = entryLines.reduce((s, l) => s + parseFloat(l.credit || '0'), 0)
    if (Math.abs(totalDebit - totalCredit) > 0.005) {
      setEntryError(`Not balanced: debits $${totalDebit.toFixed(2)} ≠ credits $${totalCredit.toFixed(2)}`)
      return
    }
    setEntryError(null)
    addEntry.mutate({
      entry_date: entryDate,
      description: entryDesc.trim(),
      source_type: 'manual',
      lines: entryLines.map(l => ({
        account_code: parseInt(l.account_code),
        debit: l.debit || '0',
        credit: l.credit || '0',
        memo: l.memo.trim() || undefined,
      })),
    })
  }

  function advance() {
    setCompleted((c) => ({ ...c, [step]: true }))
    if (step < WIZARD_STEPS.length - 1) setStep(step + 1)
  }

  if (periodLoading || !periodData) {
    return <Layout><p className="muted">Loading…</p></Layout>
  }

  const period = periodData.period
  const docs = periodData.documents
  const parsedCount = docs.filter(d => d.parse_status === 'parsed' || d.parse_status === 'complete').length

  return (
    <Layout activePeriod={period}>
      <div className="page">
        <Link to={`/periods/${period.period_id}`} className="btn btn-ghost btn-sm" style={{ marginBottom: 12, marginLeft: -8 }}>
          <SvgIcon name="arrowLeft" size={14} /> Period detail
        </Link>

        <PageHeader
          eyebrow="Guided close"
          title={`Close ${fmtPeriod(period.period_start)}`}
          subtitle="Step through the close in order. You can re-visit any completed step."
          badge={<StatusBadge status={period.status} />}
        />

        <div className="wizard-shell">
          {/* Sidebar nav */}
          <div className="wizard-side">
            {WIZARD_STEPS.map((s, i) => {
              const cls = completed[i] ? 'done' : i === step ? 'active' : ''
              return (
                <div key={s.key} className={`wizard-step ${cls}`} onClick={() => setStep(i)}>
                  <div className="wizard-step-num">
                    {completed[i] ? <SvgIcon name="check" size={12} strokeWidth={2.5} /> : i + 1}
                  </div>
                  <div>
                    <div className="wizard-step-name">{s.name}</div>
                    <div className="wizard-step-hint">{s.hint}</div>
                  </div>
                  <div className="wizard-step-connector" />
                </div>
              )
            })}
          </div>

          {/* Body */}
          <div className="wizard-body">
            {/* Step 0: Docs */}
            {step === 0 && (
              <>
                <div className="wizard-body-hd">
                  <div className="wizard-body-title">All documents parsed?</div>
                  <div className="wizard-body-sub">Confirm every statement is parsed before approving transactions.</div>
                </div>
                <div className="wizard-body-bd">
                  <div className="grid grid-3 mb-4">
                    <CountTile label="Parsed" count={parsedCount} color="var(--green)" />
                    <CountTile label="Pending" count={docs.filter(d => d.parse_status === 'pending').length} color="var(--amber)" />
                    <CountTile label="Failed" count={docs.filter(d => d.parse_status === 'failed').length} color="var(--red)" />
                  </div>
                  <div className="card">
                    <div className="card-bd-flush">
                      {docs.slice(0, 6).map((d) => (
                        <div className="doc-row" key={d.document_id}>
                          <div className="doc-icon"><SvgIcon name="pdf" size={16} /></div>
                          <div>
                            <div className="doc-name">{d.file_name}</div>
                            <div className="doc-meta">{d.document_type.replace(/_/g, ' ')}</div>
                          </div>
                          <StatusBadge status={d.parse_status} />
                        </div>
                      ))}
                    </div>
                  </div>
                  {parseLog.length > 0 && (
                    <div className="parse-log mt-4">
                      {parseLog.map((entry, i) => (
                        <div key={i} className={`parse-log-item parse-log-item--${entry.status}`}>
                          <div className="parse-log-icon">
                            {entry.status === 'running'
                              ? <span className="spinner" style={{ width: 13, height: 13 }} />
                              : entry.status === 'done'
                              ? <SvgIcon name="check" size={13} strokeWidth={2.5} />
                              : entry.status === 'warn'
                              ? <span style={{ fontSize: 12 }}>!</span>
                              : <span style={{ fontSize: 12 }}>✕</span>}
                          </div>
                          <div className="parse-log-text">
                            <div className="parse-log-label">{entry.label}</div>
                            {entry.detail && <div className="parse-log-detail">{entry.detail}</div>}
                          </div>
                        </div>
                      ))}
                      {isParsing && <div className="progress-bar mt-2"><div className="progress-bar-fill" /></div>}
                    </div>
                  )}
                  {periodData.has_pending_documents && !isParsing && (
                    <button className="btn btn-secondary btn-sm mt-4" disabled={isParsing} onClick={handleParse}>
                      <SvgIcon name="sparkles" size={13} />Parse all pending
                    </button>
                  )}
                </div>
                <div className="wizard-body-ft">
                  <span className="muted" style={{ fontSize: 12 }}>{parsedCount} of {docs.length} documents parsed.</span>
                  <button className="btn btn-primary" onClick={advance}>Continue <SvgIcon name="arrow" size={14} /></button>
                </div>
              </>
            )}

            {/* Step 1: Classify */}
            {step === 1 && (
              <>
                <div className="wizard-body-hd spread">
                  <div>
                    <div className="wizard-body-title">Approve extracted transactions</div>
                    <div className="wizard-body-sub">
                      {journalData ? `${journalData.approved.length} of ${journalData.staged.length + journalData.approved.length} approved` : 'Loading…'}
                    </div>
                  </div>
                  <div className="row gap-2">
                    <button className="btn btn-secondary btn-sm" disabled={classify.isPending} onClick={() => classify.mutate()}>
                      <SvgIcon name="sparkles" size={13} />{classify.isPending ? 'Classifying…' : 'Classify with AI'}
                    </button>
                    <button className="btn btn-secondary btn-sm" disabled={approveAll.isPending} onClick={() => approveAll.mutate()}>
                      Approve all
                    </button>
                  </div>
                </div>
                <div className="wizard-body-bd" style={{ padding: 0 }}>
                  {journalData ? (
                    <div className="tbl-scroll">
                      <table className="tbl">
                        <thead>
                          <tr><th>Date</th><th>Description</th><th>Source</th><th>Suggested category</th><th>Confidence</th><th className="text-right">Amount</th><th className="text-right">Status</th><th /></tr>
                        </thead>
                        <tbody>
                          {(() => {
                            const docsByID = Object.fromEntries(journalData.documents.map(d => [d.document_id, d]))
                            return [...journalData.staged, ...journalData.approved].map((t) => {
                            const n = parseFloat(t.amount)
                            const doc = docsByID[t.document_id]
                            return (
                              <tr key={t.raw_txn_id}>
                                <td className="mono muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{t.txn_date.slice(5)}</td>
                                <td>{t.description}</td>
                                <td>
                                  {doc
                                    ? <span className="badge badge--ghost" style={{ whiteSpace: 'nowrap' }}>{doc.document_type.replace(/_/g, ' ')}</span>
                                    : <span className="muted" style={{ fontSize: 12 }}>—</span>}
                                </td>
                                <td>
                                  <select
                                    className="inp inp--sm"
                                    value={t.suggested_account_code ?? ''}
                                    onChange={(e) => updateAccount.mutate({ txnId: t.raw_txn_id, accountCode: Number(e.target.value) })}
                                    style={{ minWidth: 180 }}
                                  >
                                    {t.suggested_account_code == null && <option value="">— pick account —</option>}
                                    {journalData.accounts.map((a) => (
                                      <option key={a.account_code} value={a.account_code}>{a.account_name}</option>
                                    ))}
                                  </select>
                                </td>
                                <td><ConfidencePill confidence={t.classifier_confidence} /></td>
                                <td className="mono text-right" style={{ color: n < 0 ? 'var(--red)' : 'var(--green)', whiteSpace: 'nowrap' }}>{n < 0 ? `−$${Math.abs(n).toFixed(2)}` : `$${n.toFixed(2)}`}</td>
                                <td className="text-right"><StatusBadge status={t.status} /></td>
                                <td className="text-right">
                                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                  {t.status !== 'approved' && (
                                    <button
                                      className="icon-btn"
                                      title="Approve transaction"
                                      disabled={approveSingle.isPending}
                                      onClick={() => approveSingle.mutate(t.raw_txn_id)}
                                      style={{ color: 'var(--text-3)' }}
                                      onMouseEnter={e => (e.currentTarget.style.color = 'var(--green)')}
                                      onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                                    >
                                      <SvgIcon name="check" size={14} />
                                    </button>
                                  )}
                                  <button
                                    className="icon-btn"
                                    title="Remove transaction"
                                    disabled={removeTransaction.isPending}
                                    onClick={() => removeTransaction.mutate(t.raw_txn_id)}
                                    style={{ color: 'var(--text-3)' }}
                                    onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
                                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                                  >
                                    <SvgIcon name="trash" size={14} />
                                  </button>
                                  </div>
                                </td>
                              </tr>
                            )
                          })
                          })()}
                        </tbody>
                      </table>
                    </div>
                  ) : <p className="muted" style={{ padding: 16 }}>Loading transactions…</p>}
                </div>
                <div className="wizard-body-ft">
                  <span className="muted" style={{ fontSize: 12 }}>Low-confidence items may need manual review.</span>
                  <button className="btn btn-primary" onClick={advance}>Continue <SvgIcon name="arrow" size={14} /></button>
                </div>
              </>
            )}

            {/* Step 2: Journal entries */}
            {step === 2 && (
              <>
                <div className="wizard-body-hd spread">
                  <div>
                    <div className="wizard-body-title">Review journal entries</div>
                    <div className="wizard-body-sub">
                      {journalData
                        ? journalData.entries.length > 0
                          ? `${journalData.entries.length} entr${journalData.entries.length === 1 ? 'y' : 'ies'} from ${journalData.approved.length} approved transaction${journalData.approved.length === 1 ? '' : 's'}.`
                          : journalData.approved.length > 0
                            ? `${journalData.approved.length} approved transaction${journalData.approved.length === 1 ? '' : 's'} — post them to generate entries.`
                            : 'No approved transactions yet.'
                        : 'Loading…'}
                    </div>
                  </div>
                  <div className="row gap-2">
                    {journalData && journalData.approved.length > 0 && (
                      <button className="btn btn-secondary btn-sm" disabled={postTxns.isPending} onClick={() => postTxns.mutate()}>
                        <SvgIcon name="sparkles" size={13} />{postTxns.isPending ? 'Posting…' : 'Post transactions'}
                      </button>
                    )}
                    {journalData && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setShowEntryForm(true)
                          if (!entryDate) setEntryDate(period.period_end)
                          setEntryError(null)
                        }}
                      >
                        <SvgIcon name="plus" size={13} />Add entry
                      </button>
                    )}
                  </div>
                </div>
                <div className="wizard-body-bd">
                  {showEntryForm && journalData && (
                    <div className="card mb-4">
                      <div className="card-hd spread">
                        <div className="card-title">New manual entry</div>
                        <button
                          className="icon-btn"
                          style={{ color: 'var(--text-3)' }}
                          onClick={() => { setShowEntryForm(false); setEntryError(null) }}
                          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text)')}
                          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                        >
                          <SvgIcon name="x" size={15} />
                        </button>
                      </div>
                      <div className="card-bd stack gap-4">
                        <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 12 }}>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-3)', marginBottom: 4 }}>Date</div>
                            <input className="inp" type="date" value={entryDate} onChange={e => setEntryDate(e.target.value)} />
                          </div>
                          <div>
                            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-3)', marginBottom: 4 }}>Description</div>
                            <input className="inp" type="text" value={entryDesc} onChange={e => setEntryDesc(e.target.value)} placeholder="e.g. Cash purchase — office supplies" />
                          </div>
                        </div>
                        <div className="tbl-scroll">
                          <table className="tbl">
                            <thead>
                              <tr>
                                <th>Account</th>
                                <th className="text-right" style={{ width: 110 }}>Debit</th>
                                <th className="text-right" style={{ width: 110 }}>Credit</th>
                                <th style={{ width: 160 }}>Memo</th>
                                <th style={{ width: 32 }} />
                              </tr>
                            </thead>
                            <tbody>
                              {entryLines.map((line, i) => (
                                <tr key={i}>
                                  <td>
                                    <select
                                      className="inp inp--sm"
                                      style={{ minWidth: 200 }}
                                      value={line.account_code}
                                      onChange={e => setEntryLines(prev => prev.map((l, j) => j === i ? { ...l, account_code: e.target.value } : l))}
                                    >
                                      <option value="">— pick account —</option>
                                      {journalData.accounts.map(a => (
                                        <option key={a.account_code} value={a.account_code}>{a.account_code} · {a.account_name}</option>
                                      ))}
                                    </select>
                                  </td>
                                  <td>
                                    <input
                                      className="inp inp--sm mono"
                                      style={{ width: '100%', textAlign: 'right' }}
                                      type="number"
                                      min="0"
                                      step="0.01"
                                      placeholder="0.00"
                                      value={line.debit}
                                      onChange={e => setEntryLines(prev => prev.map((l, j) => j === i ? { ...l, debit: e.target.value } : l))}
                                    />
                                  </td>
                                  <td>
                                    <input
                                      className="inp inp--sm mono"
                                      style={{ width: '100%', textAlign: 'right' }}
                                      type="number"
                                      min="0"
                                      step="0.01"
                                      placeholder="0.00"
                                      value={line.credit}
                                      onChange={e => setEntryLines(prev => prev.map((l, j) => j === i ? { ...l, credit: e.target.value } : l))}
                                    />
                                  </td>
                                  <td>
                                    <input
                                      className="inp inp--sm"
                                      style={{ width: '100%' }}
                                      type="text"
                                      placeholder="Optional"
                                      value={line.memo}
                                      onChange={e => setEntryLines(prev => prev.map((l, j) => j === i ? { ...l, memo: e.target.value } : l))}
                                    />
                                  </td>
                                  <td>
                                    {entryLines.length > 2 && (
                                      <button
                                        className="icon-btn"
                                        style={{ color: 'var(--text-3)' }}
                                        onClick={() => setEntryLines(prev => prev.filter((_, j) => j !== i))}
                                        onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
                                        onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-3)')}
                                      >
                                        <SvgIcon name="trash" size={13} />
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr>
                                <td>
                                  <button className="btn btn-ghost btn-sm" onClick={() => setEntryLines(prev => [...prev, blankLine()])}>
                                    <SvgIcon name="plus" size={12} /> Add line
                                  </button>
                                </td>
                                <td className="mono text-right fw-600" style={{ fontSize: 13, color: 'var(--text)' }}>
                                  {entryLines.reduce((s, l) => s + parseFloat(l.debit || '0'), 0).toFixed(2)}
                                </td>
                                <td className="mono text-right fw-600" style={{ fontSize: 13, color: 'var(--text)' }}>
                                  {entryLines.reduce((s, l) => s + parseFloat(l.credit || '0'), 0).toFixed(2)}
                                </td>
                                <td colSpan={2} />
                              </tr>
                            </tfoot>
                          </table>
                        </div>
                        {entryError && <p style={{ color: 'var(--red)', fontSize: 13, margin: 0 }}>{entryError}</p>}
                        <div className="row gap-2" style={{ justifyContent: 'flex-end' }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => { setShowEntryForm(false); setEntryError(null) }}>Cancel</button>
                          <button className="btn btn-primary btn-sm" disabled={addEntry.isPending} onClick={handleSubmitEntry}>
                            {addEntry.isPending ? 'Saving…' : 'Save entry'}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                  {journalData ? (
                    journalData.entries.length === 0 ? (
                      <p className="muted" style={{ padding: '16px 0' }}>No journal entries yet. Approve transactions and post them first.</p>
                    ) : (
                      <div className="stack gap-4">
                        {(() => {
                          const accountsByCode = Object.fromEntries(journalData.accounts.map(a => [a.account_code, a]))
                          return journalData.entries.map((entry) => {
                          const totalDebit = entry.lines.reduce((s, l) => s + parseFloat(l.debit_amount), 0)
                          return (
                            <div key={entry.entry_id} className="card">
                              <div className="card-hd">
                                <div>
                                  <div className="card-title">{entry.description}</div>
                                  <div className="card-sub mono">{entry.entry_date} · {entry.source_type.replace(/_/g, ' ')}</div>
                                </div>
                                <span className="mono fw-600">${totalDebit.toFixed(2)}</span>
                              </div>
                              <div className="tbl-scroll">
                                <table className="tbl">
                                  <thead>
                                    <tr><th>Account</th><th>Memo</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr>
                                  </thead>
                                  <tbody>
                                    {[...entry.lines]
                                      .sort((a, b) => {
                                        const aD = parseFloat(a.debit_amount) > 0
                                        const bD = parseFloat(b.debit_amount) > 0
                                        if (aD !== bD) return aD ? -1 : 1
                                        return a.account_code - b.account_code
                                      })
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
                                </table>
                              </div>
                            </div>
                          )
                        })
                        })()}
                      </div>
                    )
                  ) : <p className="muted">Loading entries…</p>}
                </div>
                <div className="wizard-body-ft">
                  <span className="muted" style={{ fontSize: 12 }}>Each approved transaction produces one journal entry.</span>
                  <button className="btn btn-primary" onClick={advance}>Continue <SvgIcon name="arrow" size={14} /></button>
                </div>
              </>
            )}

            {/* Step 3: Balances */}
            {step === 3 && (
              <>
                <div className="wizard-body-hd">
                  <div className="wizard-body-title">Stated ending balances</div>
                  <div className="wizard-body-sub">Type the ending balance shown on each statement.</div>
                </div>
                <div className="wizard-body-bd">
                  <div className="stack gap-4">
                    {periodData.balance_accounts.map((a) => (
                      <div className="spread" key={a.account_code} style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 500 }}>{a.account_name}</div>
                          <div className="muted mono" style={{ fontSize: 11.5 }}>{a.account_code} · {a.sub_category}</div>
                        </div>
                        <input
                          className="inp mono"
                          style={{ width: 150, textAlign: 'right' }}
                          type="number"
                          step="0.01"
                          value={balanceValues[a.account_code] ?? (periodData.stated_balances[a.account_code] ?? '')}
                          placeholder="0.00"
                          onChange={(e) => setBalanceValues(prev => ({ ...prev, [a.account_code]: e.target.value }))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
                <div className="wizard-body-ft">
                  <span className="muted" style={{ fontSize: 12 }}>Balances used in reconciliation.</span>
                  <button
                    className="btn btn-primary"
                    disabled={saveBalancesMut.isPending}
                    onClick={async () => { await saveBalancesMut.mutateAsync(); advance() }}
                  >
                    {saveBalancesMut.isPending ? 'Saving…' : <>Save & continue <SvgIcon name="arrow" size={14} /></>}
                  </button>
                </div>
              </>
            )}

            {/* Step 4: Reconcile */}
            {step === 4 && (
              <>
                <div className="wizard-body-hd spread">
                  <div>
                    <div className="wizard-body-title">Reconciliation</div>
                    <div className="wizard-body-sub">
                      {reconData?.ran ? `${reconData.details.filter(d => d.status !== 'reconciled').length} accounts have gaps.` : 'Run reconciliation to compare balances.'}
                    </div>
                  </div>
                  <button className="btn btn-secondary btn-sm" disabled={runRecon.isPending} onClick={() => runRecon.mutate()}>
                    <SvgIcon name="refresh" size={13} />{runRecon.isPending ? 'Running…' : 'Run reconciliation'}
                  </button>
                </div>
                <div className="wizard-body-bd" style={{ padding: 0 }}>
                  {reconError && (
                    <p style={{ padding: '12px 16px', color: 'var(--red)', fontSize: 13 }}>{reconError}</p>
                  )}
                  {reconData?.ran ? reconData.details.map((r) => (
                    <div key={r.recon_id} style={{ padding: '12px 16px', borderBottom: '1px solid var(--line)', display: 'grid', gridTemplateColumns: '1.6fr 1fr 1fr 120px 100px', gap: 16, alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500 }}>{r.account_name}</div>
                        <div className="muted mono" style={{ fontSize: 11.5 }}>{r.account_code}</div>
                      </div>
                      <div><div className="muted" style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Computed</div><div className="mono">{parseFloat(r.computed_balance).toFixed(2)}</div></div>
                      <div><div className="muted" style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Stated</div><div className="mono">{parseFloat(r.stated_balance).toFixed(2)}</div></div>
                      <div><div className="muted" style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Gap</div><div className="mono fw-600" style={{ color: parseFloat(r.gap) === 0 ? 'var(--green)' : 'var(--amber)' }}>{parseFloat(r.gap) === 0 ? '$0.00' : `$${parseFloat(r.gap).toFixed(2)}`}</div></div>
                      <div className="text-right">
                        {parseFloat(r.gap) === 0
                          ? <StatusBadge status="reconciled" />
                          : r.is_investment
                            ? <button className="btn btn-secondary btn-sm" disabled={postUnrealized.isPending} onClick={() => postUnrealized.mutate(r.account_code)}>Post G/L</button>
                            : <button className="btn btn-secondary btn-sm" disabled>Fix</button>
                        }
                      </div>
                    </div>
                  )) : !reconError && <p className="muted" style={{ padding: 16 }}>Click "Run reconciliation" to compare balances.</p>}
                </div>
                <div className="wizard-body-ft">
                  <span className="muted" style={{ fontSize: 12 }}>You can post adjusting entries from the Reconcile tab.</span>
                  <button className="btn btn-primary" onClick={advance}>Continue to post <SvgIcon name="arrow" size={14} /></button>
                </div>
              </>
            )}

            {/* Step 5: Post & Close */}
            {step === 5 && (
              <>
                {completed[5] ? (
                  <>
                    <div className="wizard-body-hd">
                      <div className="wizard-body-title">Period closed</div>
                      <div className="wizard-body-sub">{fmtPeriod(period.period_start)} is locked and posted to the ledger.</div>
                    </div>
                    <div className="wizard-body-bd" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 12 }}>
                      <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--green-bg)', color: 'var(--green)', display: 'grid', placeItems: 'center' }}>
                        <SvgIcon name="check" size={32} strokeWidth={2.2} />
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em' }}>All set</div>
                      <p className="muted text-center">Period closed and locked. All journal entries have been posted.</p>
                    </div>
                    <div className="wizard-body-ft">
                      <span className="muted" style={{ fontSize: 12 }}>Period is now read-only.</span>
                      <Link to="/" className="btn btn-primary">Back to dashboard <SvgIcon name="arrow" size={14} /></Link>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="wizard-body-hd">
                      <div className="wizard-body-title">Post & close period</div>
                      <div className="wizard-body-sub">Post journal entries and close the period. This locks the period.</div>
                    </div>
                    <div className="wizard-body-bd">
                      <div className="grid grid-3 mb-4">
                        <CountTile label="Approved txns" count={journalData?.approved.length ?? 0} color="var(--accent)" />
                        <CountTile label="Journal entries" count={journalData?.entries.length ?? 0} color="var(--accent)" />
                        <CountTile label="Closing entries" count={reconData?.temp_preview?.closing_posted ? 2 : 0} color="var(--accent)" />
                      </div>
                      <div className="row gap-3 mb-4">
                        {reconData?.temp_preview && !reconData.temp_preview.closing_posted && (
                          <button className="btn btn-secondary btn-sm" disabled={postClosing.isPending} onClick={() => postClosing.mutate()}>
                            {postClosing.isPending ? 'Posting…' : 'Post closing entries'}
                          </button>
                        )}
                      </div>
                      {reconData?.temp_preview && (
                        <div className="stack gap-4">
                          {/* Entry 1: close revenue accounts */}
                          <ClosingEntryCard
                            title="Close revenue accounts"
                            posted={reconData.temp_preview.closing_posted}
                            rows={[
                              ...reconData.temp_preview.income_accounts.map(a => ({
                                code: a.account_code,
                                name: a.account_name,
                                debit: a.period_balance,
                                credit: '0',
                              })),
                              {
                                code: null,
                                name: 'Income Summary',
                                debit: '0',
                                credit: reconData.temp_preview.total_income,
                              },
                            ]}
                          />
                          {/* Entry 2: close expense accounts */}
                          <ClosingEntryCard
                            title="Close expense accounts"
                            posted={reconData.temp_preview.closing_posted}
                            rows={[
                              {
                                code: null,
                                name: 'Income Summary',
                                debit: reconData.temp_preview.total_expenses,
                                credit: '0',
                              },
                              ...reconData.temp_preview.expense_accounts.map(a => ({
                                code: a.account_code,
                                name: a.account_name,
                                debit: '0',
                                credit: a.period_balance,
                              })),
                            ]}
                          />
                          {/* Entry 3: equity rollup */}
                          {reconData.equity_preview && (
                            <ClosingEntryCard
                              title="Equity rollup — net income to retained earnings"
                              posted={reconData.equity_preview.rollup_posted}
                              rows={[
                                { code: null, name: 'Income Summary', debit: reconData.equity_preview.net_income_balance, credit: '0' },
                                { code: null, name: 'Retained Earnings', debit: '0', credit: reconData.equity_preview.net_income_balance },
                              ]}
                            />
                          )}
                        </div>
                      )}
                    </div>
                    <div className="wizard-body-ft">
                      <span className="muted" style={{ fontSize: 12 }}>Closing is reversible — periods can be reopened.</span>
                      <button
                        className="btn btn-primary"
                        disabled={closePeriod.isPending}
                        onClick={() => ask({ title: 'Close this period?', message: 'This locks all journal entries for the period.', confirmLabel: 'Post & close', onConfirm: () => closePeriod.mutate() })}
                      >
                        {closePeriod.isPending ? <><span className="parsing-dots"><span/><span/><span/></span> Closing…</> : <>Post & close <SvgIcon name="check" size={14} /></>}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      {confirmDialog}
    </Layout>
  )
}

function CountTile({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className="count-tile" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="count-tile-label">{label}</div>
      <div className="count-tile-value" style={{ color }}>{count}</div>
    </div>
  )
}

type ClosingRow = { code: number | null; name: string; debit: string; credit: string }

function ClosingEntryCard({ title, posted, rows }: { title: string; posted: boolean; rows: ClosingRow[] }) {
  const total = rows.reduce((s, r) => s + parseFloat(r.debit || '0'), 0)
  return (
    <div className="card">
      <div className="card-hd">
        <div>
          <div className="card-title">{title}</div>
          <div className="card-sub mono">closing entry</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="mono fw-600">${total.toFixed(2)}</span>
          {posted
            ? <span className="badge badge--green">posted</span>
            : <span className="badge badge--ghost">preview</span>}
        </div>
      </div>
      <div className="tbl-scroll">
        <table className="tbl">
          <thead>
            <tr><th>Account</th><th className="text-right">Debit</th><th className="text-right">Credit</th></tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td className="mono" style={{ fontSize: 13 }}>
                  {row.code != null && <span className="muted">{row.code} · </span>}{row.name}
                </td>
                <td className="mono text-right" style={{ color: parseFloat(row.debit) > 0 ? 'var(--text)' : 'var(--text-3)' }}>
                  {fmtDebitCredit(row.debit)}
                </td>
                <td className="mono text-right" style={{ color: parseFloat(row.credit) > 0 ? 'var(--text)' : 'var(--text-3)' }}>
                  {fmtDebitCredit(row.credit)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
