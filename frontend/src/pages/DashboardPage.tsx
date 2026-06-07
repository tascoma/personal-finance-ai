import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { fetchDashboard } from '../api/dashboard'
import { fetchPeriods } from '../api/periods'
import Layout from '../components/Layout'
import PageHeader from '../components/PageHeader'
import EmptyState from '../components/EmptyState'
import SvgIcon from '../components/SvgIcon'
import OverviewTab from './dashboard/OverviewTab'
import ExpensesTab from './dashboard/ExpensesTab'
import AssetsTab from './dashboard/AssetsTab'
import ForecastTab from './dashboard/ForecastTab'

type DashboardTab = 'overview' | 'expenses' | 'assets' | 'forecast'

// `null` selected year means "All Years".
const ALL_YEARS = null

export default function DashboardPage() {
  const [selectedYear, setSelectedYear] = useState<number | null>(ALL_YEARS)
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview')

  const initialised = useRef(false)
  const queryClient = useQueryClient()
  const { data: allPeriods } = useQuery({ queryKey: ['periods'], queryFn: fetchPeriods, staleTime: 60_000 })
  const closedPeriods = useMemo(() => (allPeriods ?? []).filter((p) => p.status === 'closed'), [allPeriods])

  // Years with at least one closed period, newest first.
  const availableYears = useMemo(
    () => [...new Set(closedPeriods.map((p) => Number(p.period_start.slice(0, 4))))].sort((a, b) => b - a),
    [closedPeriods],
  )

  // Default to the current year if it has data, else the most recent year, else All Years.
  useEffect(() => {
    if (initialised.current || availableYears.length === 0) return
    initialised.current = true
    const currentYear = new Date().getFullYear()
    setSelectedYear(availableYears.includes(currentYear) ? currentYear : availableYears[0])
  }, [availableYears])

  const scopeLabel = selectedYear == null ? 'All Years' : String(selectedYear)

  const DASHBOARD_STALE_TIME = 5 * 60_000

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['dashboard', selectedYear],
    queryFn: () => fetchDashboard(selectedYear ?? undefined),
    staleTime: DASHBOARD_STALE_TIME,
    placeholderData: keepPreviousData,
  })

  // Warm the cache for every other filter option in the background so switching
  // years is instant (mirrors the iOS dashboard's prefetchOthers()).
  useEffect(() => {
    if (availableYears.length === 0) return
    const options: (number | null)[] = [...availableYears, ALL_YEARS]
    for (const year of options) {
      if (year === selectedYear) continue
      queryClient.prefetchQuery({
        queryKey: ['dashboard', year],
        queryFn: () => fetchDashboard(year ?? undefined),
        staleTime: DASHBOARD_STALE_TIME,
      })
    }
  }, [availableYears, selectedYear, queryClient])

  if (isLoading && !data) return <Layout><p className="muted">Loading…</p></Layout>
  if (error || !data) return <Layout><p className="color-red">Failed to load dashboard.</p></Layout>

  return (
    <Layout activePeriod={data.active_period}>
      <div className="page">
        <PageHeader
          eyebrow="Overview"
          title="Welcome back"
          subtitle={`Financial snapshot · ${data.period_count} period${data.period_count !== 1 ? 's' : ''} tracked`}
          actions={
            <div className="row gap-2 wrap">
              <div className="seg">
                <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>Overview</button>
                <button className={activeTab === 'expenses' ? 'active' : ''} onClick={() => setActiveTab('expenses')}>Expenses</button>
                <button className={activeTab === 'assets' ? 'active' : ''} onClick={() => setActiveTab('assets')}>Assets</button>
                <button className={activeTab === 'forecast' ? 'active' : ''} onClick={() => setActiveTab('forecast')}>Forecast</button>
              </div>
              {availableYears.length > 0 && (
                <div className="row gap-2">
                  <SvgIcon name="periods" size={14} />
                  <select
                    className="inp inp-fit"
                    style={{ minWidth: 120 }}
                    value={selectedYear == null ? 'all' : String(selectedYear)}
                    onChange={(e) => setSelectedYear(e.target.value === 'all' ? null : Number(e.target.value))}
                  >
                    {availableYears.map((y) => <option key={y} value={y}>{y}</option>)}
                    <option value="all">All Years</option>
                  </select>
                  {isFetching && <span className="muted" style={{ fontSize: 12 }}>Updating…</span>}
                </div>
              )}
            </div>
          }
        />

        {!data.has_data && !data.active_period ? (
          <div className="card">
            <EmptyState icon="periods" message="No open period yet." hint="Create a period to start tracking your finances.">
              <Link to="/periods" className="btn btn-primary" style={{ marginTop: 8 }}>Go to Workflow</Link>
            </EmptyState>
          </div>
        ) : (
          <>
            {activeTab === 'overview' && <OverviewTab data={data} scopeLabel={scopeLabel} />}
            {activeTab === 'expenses' && <ExpensesTab data={data} scopeLabel={scopeLabel} />}
            {activeTab === 'assets' && <AssetsTab data={data} scopeLabel={scopeLabel} />}
            {activeTab === 'forecast' && <ForecastTab data={data} scopeLabel={scopeLabel} />}
          </>
        )}
      </div>
    </Layout>
  )
}
