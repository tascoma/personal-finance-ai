import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPeriods, createPeriod } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import EmptyState from '../components/EmptyState'
import PeriodStepper from '../components/PeriodStepper'
import Banner from '../components/Banner'
import SvgIcon from '../components/SvgIcon'
import { fmtPeriod } from '../utils/format'

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

export default function PeriodsListPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [year, setYear] = useState<string>(String(new Date().getFullYear()))
  const [month, setMonth] = useState<string>(String(new Date().getMonth() + 1))
  const [error, setError] = useState<string | null>(null)

  const { data: periods = [], isLoading } = useQuery({
    queryKey: ['periods'],
    queryFn: fetchPeriods,
    staleTime: 30_000,
  })

  const create = useMutation({
    mutationFn: () => createPeriod({ year: parseInt(year, 10), month: parseInt(month, 10) }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['periods'] })
      setError(null)
      navigate(`/periods/${p.period_id}`)
    },
    onError: (e: Error) => setError(e.message),
  })

  const activePeriod = periods.find((p) => p.status !== 'closed')
  const closedCount = periods.filter((p) => p.status === 'closed').length

  return (
    <Layout>
      <div className="page">
        <PageHeader
          eyebrow="Workflow"
          title="Monthly close"
          subtitle="Each calendar month progresses through a four-stage close."
          actions={
            <div className="row gap-2">
              <div className="field-group">
                <label htmlFor="year" className="field-label">Year</label>
                <input
                  id="year"
                  type="number"
                  min={1900}
                  max={2100}
                  placeholder="2026"
                  className="inp"
                  style={{ width: 90 }}
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                />
              </div>
              <div className="field-group">
                <label htmlFor="month" className="field-label">Month</label>
                <select id="month" className="inp" style={{ width: 150 }} value={month} onChange={(e) => setMonth(e.target.value)}>
                  {MONTHS.map((name, i) => (
                    <option key={i + 1} value={i + 1}>{name}</option>
                  ))}
                </select>
              </div>
              <div className="field-group">
                <div style={{ height: 19 }} />
                <button className="btn btn-primary" disabled={create.isPending} onClick={() => create.mutate()}>
                  <SvgIcon name="plus" size={13} />
                  {create.isPending ? 'Creating…' : 'New period'}
                </button>
              </div>
            </div>
          }
        />

        {error && <Banner variant="red" style={{ marginBottom: 16 }}>{error}</Banner>}

        {/* Active period card */}
        {activePeriod && (
          <div className="grid grid-12 mb-6">
            <div className="card col-8">
              <div className="card-hd">
                <div>
                  <div className="card-title">Active period — {fmtPeriod(activePeriod.period_start)}</div>
                  <div className="card-sub">{activePeriod.period_start} → {activePeriod.period_end}</div>
                </div>
                <StatusBadge status={activePeriod.status} />
              </div>
              <div className="card-bd">
                <PeriodStepper period={activePeriod} />
                <div className="row gap-2 mt-4">
                  <Link to={`/periods/${activePeriod.period_id}`} className="btn btn-primary">
                    Continue <SvgIcon name="arrow" size={14} />
                  </Link>
                  <Link to={`/periods/${activePeriod.period_id}/close`} className="btn btn-secondary">
                    <SvgIcon name="zap" size={14} /> Guided close wizard
                  </Link>
                </div>
              </div>
            </div>

            <div className="card col-4">
              <div className="card-hd"><div className="card-title">Quick stats</div></div>
              <div className="card-bd stack gap-3">
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>Periods closed</span>
                  <span className="mono fw-600" style={{ fontSize: 14 }}>{closedCount}</span>
                </div>
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>Active period</span>
                  <span className="mono fw-600" style={{ fontSize: 14 }}>{fmtPeriod(activePeriod.period_start)}</span>
                </div>
                <div className="spread">
                  <span className="muted" style={{ fontSize: 12.5 }}>Current status</span>
                  <StatusBadge status={activePeriod.status} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* All periods table */}
        <div className="card">
          <div className="card-hd">
            <div>
              <div className="card-title">All periods</div>
              <div className="card-sub">{closedCount} closed · {periods.length - closedCount} open</div>
            </div>
          </div>

          {isLoading && <p className="muted" style={{ padding: '16px 20px' }}>Loading…</p>}

          {!isLoading && !periods.length && (
            <EmptyState icon="periods" message="No periods yet." hint="Create your first accounting period using the form above." />
          )}

          {periods.length > 0 && (
            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>Range</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Closed</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {[...periods].reverse().map((p) => (
                    <tr key={p.period_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/periods/${p.period_id}`)}>
                      <td>
                        <span className="fw-600">{fmtPeriod(p.period_start)}</span>
                        {p.status !== 'closed' && (
                          <span className="badge badge--accent" style={{ marginLeft: 8 }}>Active</span>
                        )}
                      </td>
                      <td className="mono muted" style={{ fontSize: 12 }}>{p.period_start} → {p.period_end}</td>
                      <td><StatusBadge status={p.status} /></td>
                      <td className="mono muted" style={{ fontSize: 12 }}>{p.created_at.slice(0, 10)}</td>
                      <td className="mono muted" style={{ fontSize: 12 }}>{p.closed_at ? p.closed_at.slice(0, 10) : '—'}</td>
                      <td>
                        <button className="btn btn-ghost btn-sm">
                          Open <SvgIcon name="arrow" size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  )
}
