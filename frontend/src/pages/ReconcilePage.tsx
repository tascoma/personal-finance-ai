import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchReconcilePage, runReconciliation, analyzeReconciliation, postUnrealizedGl, postClosingEntries, postEquityRollup } from '../api/reconciliation'
import { updatePeriodStatus } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import PeriodStepper from '../components/PeriodStepper'
import WorkflowHint from '../components/WorkflowHint'
import Banner from '../components/Banner'
import SvgIcon from '../components/SvgIcon'
import { fmtPeriod } from '../utils/format'

function fmtGap(gap: string) {
  const n = parseFloat(gap)
  if (n === 0) return <span className="color-green">$0.00</span>
  if (Math.abs(n) > 5) return <span className="color-red fw-600">{n.toFixed(2)}</span>
  return <span className="color-amber">{n.toFixed(2)}</span>
}

function fmtSigned(val: string) {
  const n = parseFloat(val)
  if (n < 0) return <span className="color-red">({Math.abs(n).toFixed(2)})</span>
  return <>{n.toFixed(2)}</>
}

interface Props {
  embedded?: boolean
  periodId?: string
}

export default function ReconcilePage({ embedded, periodId: propPeriodId }: Props) {
  const params = useParams<{ periodId: string }>()
  const periodId = propPeriodId ?? params.periodId
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['reconcile', periodId] })

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ['reconcile', periodId],
    queryFn: () => fetchReconcilePage(periodId!),
    staleTime: 30_000,
    enabled: !!periodId,
  })

  const run = useMutation({ mutationFn: () => runReconciliation(periodId!), onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d), onError: (e: Error) => setError(e.message) })
  const analyze = useMutation({ mutationFn: () => analyzeReconciliation(periodId!), onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d), onError: (e: Error) => setError(e.message) })
  const postUnrealized = useMutation({ mutationFn: (code: number) => postUnrealizedGl(periodId!, code), onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d), onError: (e: Error) => setError(e.message) })
  const postClosing = useMutation({ mutationFn: () => postClosingEntries(periodId!), onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d), onError: (e: Error) => setError(e.message) })
  const postEquity = useMutation({ mutationFn: () => postEquityRollup(periodId!), onSuccess: (d) => qc.setQueryData(['reconcile', periodId], d), onError: (e: Error) => setError(e.message) })
  const advanceStatus = useMutation({ mutationFn: (s: string) => updatePeriodStatus(periodId!, s), onSuccess: () => invalidate(), onError: (e: Error) => setError(e.message) })

  if (isLoading || !data) {
    if (embedded) return <p className="muted">Loading…</p>
    return <Layout><p className="muted">Loading…</p></Layout>
  }

  const { period, details, ran, has_gaps, has_non_investment_gaps, analysis, temp_preview, equity_preview } = data
  const canEdit = period.status === 'pending_close' || period.status === 'closed'
  const canClose = period.status === 'pending_close'

  const content = (
    <>
      {loadError && <Banner variant="red" style={{ marginBottom: 12 }}>Failed to load reconciliation data.</Banner>}
      {error && <Banner variant="red" style={{ marginBottom: 12 }}>{error}</Banner>}

      <div className="kpi-grid kpi-4 mb-4">
        <div className="kpi"><div className="kpi-label">Accounts</div><div className="kpi-value">{details.length}</div><div className="kpi-sub">being reconciled</div></div>
        <div className="kpi"><div className="kpi-label">Reconciled</div><div className="kpi-value color-green">{details.filter(d => d.status === 'reconciled').length}</div><div className="kpi-sub">exact match</div></div>
        <div className="kpi"><div className="kpi-label">With gaps</div><div className="kpi-value color-amber">{details.filter(d => d.status !== 'reconciled').length}</div><div className="kpi-sub">needs attention</div></div>
        <div className="kpi"><div className="kpi-label">Total gap</div><div className="kpi-value">${details.filter(d => d.status !== 'reconciled').reduce((s, d) => s + Math.abs(parseFloat(d.gap)), 0).toFixed(2)}</div><div className="kpi-sub">absolute sum</div></div>
      </div>

      {!ran ? (
        <div className="card">
          <div className="card-bd text-center" style={{ padding: '36px 24px' }}>
            <p className="muted-2 mb-4">Click <strong>Run Reconciliation</strong> to compare your journal balances against your stated month-end balances.</p>
            {canEdit ? (
              <button className="btn btn-primary" disabled={run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? 'Running…' : 'Run Reconciliation'}
              </button>
            ) : (
              <p className="muted" style={{ fontSize: 12 }}>Advance the period to Pending Close to run reconciliation.</p>
            )}
          </div>
        </div>
      ) : (
        <>
          {has_non_investment_gaps && !analysis && canEdit && (
            <Banner variant="accent" style={{ marginBottom: 12 }}>
              Some accounts have unexplained gaps.
              <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto' }} disabled={analyze.isPending} onClick={() => analyze.mutate()}>
                <SvgIcon name="sparkles" size={13} />{analyze.isPending ? 'Analyzing…' : 'AI Analyze gaps'}
              </button>
            </Banner>
          )}

          {analysis && (
            <div className="card mb-4" style={{ background: 'linear-gradient(135deg, var(--accent-tint), transparent 60%)' }}>
              <div className="card-hd">
                <div className="row gap-3">
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: 'linear-gradient(135deg, var(--accent), var(--purple))', display: 'grid', placeItems: 'center', color: 'var(--on-accent)' }}>
                    <SvgIcon name="sparkles" size={14} />
                  </div>
                  <div>
                    <div className="card-title">AI Reconciliation Analysis</div>
                    <div className="card-sub">Claude Sonnet 4.6</div>
                  </div>
                </div>
              </div>
              <div className="card-bd stack gap-3">
                <p className="muted-2" style={{ lineHeight: 1.55 }}>{analysis.overall_summary}</p>
                {analysis.accounts.map((acctAnalysis) => {
                  const detail = details.find((d) => d.account_code === acctAnalysis.account_code)
                  const sevColor = acctAnalysis.severity === 'high' ? 'var(--red)' : acctAnalysis.severity === 'medium' ? 'var(--amber)' : 'var(--green)'
                  return (
                    <div key={acctAnalysis.account_code} className="analysis-row" style={{ borderLeft: `3px solid ${sevColor}` }}>
                      <div className="spread mb-2">
                        <div className="fw-600" style={{ fontSize: 13 }}>{detail?.account_code ?? acctAnalysis.account_code} · {detail?.account_name ?? acctAnalysis.account_code}</div>
                        <span className="badge" style={{ background: sevColor + '20', color: sevColor, border: 'none' }}>{acctAnalysis.severity.toUpperCase()}</span>
                      </div>
                      {acctAnalysis.likely_causes.length > 0 && (
                        <div className="cause"><span className="muted fw-600">Causes: </span>{acctAnalysis.likely_causes.join('; ')}</div>
                      )}
                      {acctAnalysis.suggested_actions.length > 0 && (
                        <div className="fix"><span className="muted fw-600">Actions: </span>{acctAnalysis.suggested_actions.join('; ')}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="card mb-4">
            <div className="card-hd">
              <div>
                <div className="card-title">Account Balances</div>
                <div className="card-sub">{details.filter(d => d.status === 'reconciled').length} reconciled · {details.filter(d => d.status !== 'reconciled').length} with gaps</div>
              </div>
              {canEdit && <button className="btn btn-secondary btn-sm" disabled={run.isPending} onClick={() => run.mutate()}><SvgIcon name="refresh" size={13} /> Re-run</button>}
            </div>
            {details.map((d) => {
              const gap = parseFloat(d.gap)
              return (
                <div key={d.recon_id} className="recon-row">
                  <div className="spread mb-3">
                    <div>
                      <div className="fw-600" style={{ fontSize: 13.5 }}>{d.account_code} · {d.account_name}</div>
                      {d.is_investment && <div className="muted" style={{ fontSize: 11 }}>includes unrealized gains/losses</div>}
                    </div>
                    <div className="row gap-4">
                      <div className="text-right">
                        <div className="muted" style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Gap</div>
                        <div className="mono fw-600" style={{ fontSize: 16 }}>{fmtGap(d.gap)}</div>
                      </div>
                      {d.status === 'reconciled'
                        ? <StatusBadge status="reconciled" />
                        : <div className="row gap-2">
                            {d.is_investment && canEdit && (
                              <button className="btn btn-secondary btn-sm" disabled={postUnrealized.isPending} onClick={() => postUnrealized.mutate(d.account_code)}>Post G/L</button>
                            )}
                            <button className="btn btn-secondary btn-sm">Post adjustment</button>
                          </div>
                      }
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 120px', gap: 12, alignItems: 'center', marginBottom: 4 }}>
                    <span className="muted" style={{ fontSize: 11.5 }}>Computed</span>
                    <div className="gap-bar-wrap"><div style={{ height: '100%', width: `${Math.min(100, (parseFloat(d.computed_balance) / Math.max(parseFloat(d.computed_balance), parseFloat(d.stated_balance))) * 100)}%`, background: 'var(--accent)', borderRadius: 4 }} /></div>
                    <span className="mono text-right" style={{ fontSize: 12.5 }}>{parseFloat(d.computed_balance).toFixed(2)}</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 120px', gap: 12, alignItems: 'center' }}>
                    <span className="muted" style={{ fontSize: 11.5 }}>Stated</span>
                    <div className="gap-bar-wrap"><div style={{ height: '100%', width: `${Math.min(100, (parseFloat(d.stated_balance) / Math.max(parseFloat(d.computed_balance), parseFloat(d.stated_balance))) * 100)}%`, background: gap === 0 ? 'var(--green)' : 'var(--amber)', borderRadius: 4 }} /></div>
                    <span className="mono text-right" style={{ fontSize: 12.5 }}>{parseFloat(d.stated_balance).toFixed(2)}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {has_gaps && (
            <Banner variant="amber" style={{ marginBottom: 12 }}>
              <strong>{details.filter(d => d.status !== 'reconciled').length} account(s) have unresolved gaps.</strong>{' '}
              Post Unrealized G/L for investment accounts, or add adjusting journal entries for others, then re-run.
            </Banner>
          )}
        </>
      )}

      {/* Temporary Accounts / Closing Entries */}
      {temp_preview && (
        <div className="card mb-4">
          <div className="card-hd">
            <div>
              <div className="card-title">Closing Entry Preview</div>
              <div className="card-sub">Zero out income/expense and roll into Retained Earnings</div>
            </div>
            {!temp_preview.closing_posted && canEdit && (temp_preview.income_accounts.length > 0 || temp_preview.expense_accounts.length > 0) && (
              <button className="btn btn-primary btn-sm" disabled={postClosing.isPending} onClick={() => postClosing.mutate()}>
                {postClosing.isPending ? 'Posting…' : 'Post Closing Entries'}
              </button>
            )}
          </div>
          {temp_preview.closing_posted && <Banner variant="green" style={{ margin: '0 16px 12px' }}>Closing entries posted</Banner>}
          <div className="card-bd stack gap-3">
            <div className="spread"><span className="muted">Total income</span><span className="mono color-green fw-600">${fmtSigned(temp_preview.net_income)}</span></div>
            <div className="divider" style={{ margin: 0 }} />
            <div className="spread"><span className="fw-600">Net income → Retained Earnings</span><span className="mono color-accent fw-600">{fmtSigned(temp_preview.net_income)}</span></div>
          </div>
        </div>
      )}

      {/* Equity Rollup */}
      {equity_preview && (
        <div className="card mb-4">
          <div className="card-hd">
            <div>
              <div className="card-title">Owner's Equity Rollup</div>
              <div className="card-sub">Transfer net income to Prior Period Net Worth (300102)</div>
            </div>
            {!equity_preview.rollup_posted && parseFloat(equity_preview.net_income_balance) !== 0 && canEdit && (
              <button className="btn btn-primary btn-sm" disabled={postEquity.isPending} onClick={() => postEquity.mutate()}>
                {postEquity.isPending ? 'Posting…' : 'Post Equity Rollup'}
              </button>
            )}
          </div>
          {equity_preview.rollup_posted && <Banner variant="green" style={{ margin: '0 16px 12px' }}>Equity rollup posted</Banner>}
          <div className="card-bd stack gap-3">
            <div className="spread"><span className="muted">300103 · Current Period Net Income</span><span className="mono fw-600">{fmtSigned(equity_preview.net_income_balance)}</span></div>
            <div className="spread"><span className="muted">300102 · Prior Period Net Worth</span><span className="mono muted">receives transfer</span></div>
          </div>
        </div>
      )}

      {/* Close Period */}
      {canClose && (
        <div className="card">
          <div className="card-hd">
            <div><div className="card-title">Close Period</div><div className="card-sub">Lock the period once all gaps are resolved</div></div>
          </div>
          <div className="card-bd">
            <button
              className={`btn ${has_gaps ? 'btn-secondary' : 'btn-primary'}`}
              disabled={advanceStatus.isPending}
              onClick={() => { if (window.confirm('Close this period? This locks all journal entries.')) advanceStatus.mutate('closed') }}
            >
              {advanceStatus.isPending ? 'Closing…' : 'Post & close period'}
              <SvgIcon name="check" size={14} />
            </button>
            {has_gaps && <p className="muted mt-2" style={{ fontSize: 12 }}>You may close with gaps — they will remain in the ledger.</p>}
          </div>
        </div>
      )}
    </>
  )

  if (embedded) {
    return (
      <div className="stack gap-4">
        <div className="spread mb-2">
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em' }}>Account reconciliation</div>
            <div className="muted" style={{ fontSize: 12.5 }}>Compare computed book balances against your stated bank balances</div>
          </div>
          <div className="row gap-2">
            {canEdit && <button className="btn btn-secondary btn-sm" disabled={run.isPending} onClick={() => run.mutate()}><SvgIcon name="refresh" size={13} /> Re-run</button>}
            {has_non_investment_gaps && !analysis && canEdit && (
              <button className="btn btn-primary btn-sm" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
                {analyze.isPending ? <><span className="parsing-dots"><span/><span/><span/></span> Analyzing…</> : <><SvgIcon name="sparkles" size={13} /> AI Analyze</>}
              </button>
            )}
          </div>
        </div>
        {content}
      </div>
    )
  }

  return (
    <Layout activePeriod={period}>
      <div className="page">
        <PageHeader
          eyebrow={fmtPeriod(period.period_start)}
          title="Reconciliation"
          subtitle="Verify book balances match stated account balances"
          backTo={`/periods/${periodId}`}
          backLabel={fmtPeriod(period.period_start)}
          badge={<StatusBadge status={period.status} />}
          actions={
            canEdit ? (
              <button className="btn btn-primary btn-sm" disabled={run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? 'Running…' : 'Run Reconciliation'}
              </button>
            ) : undefined
          }
        />
        <PeriodStepper period={period} />
        <WorkflowHint period={period} page="reconcile" />
        <div className="mt-4">{content}</div>
      </div>
    </Layout>
  )
}
