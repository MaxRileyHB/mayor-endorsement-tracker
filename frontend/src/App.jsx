import { useState, useEffect, useCallback } from 'react'
import { getCities, getStats, batchUpdate, generateDrafts, getFilterOptions, getAuthStatus, syncEmails, getUnreadCities } from './api'
import KanbanBoard from './components/KanbanBoard'
import TableView from './components/TableView'
import CityDetailPanel from './components/CityDetailPanel'
import ReviewQueue from './components/ReviewQueue'
import MailMerge from './components/MailMerge'
import MultiSelectDropdown from './components/MultiSelectDropdown'
import { SkeletonKanban, SkeletonTableRows } from './components/Skeleton'
import { STATUSES } from './constants'

const EMPTY_FILTERS = {
  status: [],
  tier: [],
  county: [],
  state_senate_district: [],
  state_assembly_district: [],
  congressional_district: [],
  wildfire_risk_tier: [],
  moratorium_active: '',
  is_distressed_county: '',
  has_undermarketed_zips: '',
  needs_verification: '',
}

const PIPELINE_SEGMENTS = [
  { key: 'no_contact_info',    color: 'bg-gray-300',   label: 'No contact info' },
  { key: 'city_contact_only',  color: 'bg-gray-400',   label: 'City contact only' },
  { key: 'info_requested',     color: 'bg-amber-300',  label: 'Info requested' },
  { key: 'ready_for_outreach', color: 'bg-blue-300',   label: 'Ready for outreach' },
  { key: 'outreach_sent',      color: 'bg-blue-500',   label: 'Outreach sent' },
  { key: 'in_conversation',    color: 'bg-violet-400', label: 'In conversation' },
  { key: 'call_scheduled',     color: 'bg-violet-600', label: 'Call scheduled' },
  { key: 'endorsed',           color: 'bg-green-500',  label: 'Endorsed' },
  { key: 'declined',           color: 'bg-red-400',    label: 'Declined' },
  { key: 'follow_up',          color: 'bg-amber-400',  label: 'Follow-up needed' },
  { key: 'not_pursuing',       color: 'bg-gray-200',   label: 'Not pursuing' },
]

function PipelineBar({ stats }) {
  if (!stats) return null
  const total = stats.total || 1
  const byStatus = stats.by_status || {}

  const endorsed   = byStatus.endorsed || 0
  const active     = (byStatus.outreach_sent || 0) + (byStatus.in_conversation || 0) + (byStatus.call_scheduled || 0)
  const noContact  = (byStatus.no_contact_info || 0) + (byStatus.city_contact_only || 0)
  const declined   = byStatus.declined || 0

  return (
    <div className="bg-white border-b border-gray-100 px-4 py-2 shrink-0">
      <div className="flex items-center gap-5 mb-1.5 text-xs">
        <span className="text-gray-400">{total} cities total</span>
        <span className="font-medium text-green-700">{endorsed} endorsed</span>
        <span className="text-violet-700">{active} active in pipeline</span>
        <span className="text-gray-400">{noContact} not yet contacted</span>
        {declined > 0 && <span className="text-red-500">{declined} declined</span>}
      </div>
      <div className="flex h-2 rounded-full overflow-hidden gap-[1px] bg-gray-100">
        {PIPELINE_SEGMENTS.map(seg => {
          const count = byStatus[seg.key] || 0
          if (!count) return null
          return (
            <div
              key={seg.key}
              className={`${seg.color} h-full transition-all`}
              style={{ width: `${(count / total) * 100}%` }}
              title={`${seg.label}: ${count}`}
            />
          )
        })}
      </div>
    </div>
  )
}

const Spinner = () => (
  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
  </svg>
)

function BoolPill({ active, onToggle, label, activeClass }) {
  return (
    <button
      onClick={onToggle}
      className={`text-xs px-2.5 py-1 rounded-full border transition-colors whitespace-nowrap ${
        active ? activeClass : 'border-gray-200 text-gray-600 hover:border-gray-300 bg-white'
      }`}
    >
      {label}
    </button>
  )
}

export default function App() {
  const [cities, setCities] = useState([])
  const [stats, setStats] = useState(null)
  const [filterOptions, setFilterOptions] = useState({
    counties: [], senate_districts: [], assembly_districts: [], congressional_districts: [],
  })
  const [view, setView] = useState('kanban')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [showFilters, setShowFilters] = useState(false)
  const [sortBy, setSortBy] = useState('city_name')
  const [sortOrder, setSortOrder] = useState('asc')
  const [selected, setSelected] = useState(new Set())
  const [activeCity, setActiveCity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [fetching, setFetching] = useState(false)
  const [reviewBatchId, setReviewBatchId] = useState(null)
  const [reviewCityCount, setReviewCityCount] = useState(0)
  const [mailMergeInitialCityIds, setMailMergeInitialCityIds] = useState([])
  const [generating, setGenerating] = useState(false)
  const [gmailStatus, setGmailStatus] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [unreadCityIds, setUnreadCityIds] = useState(new Set())

  const loadCities = useCallback(async () => {
    setFetching(true)
    try {
      const params = { per_page: 500 }
      if (search) params.search = search
      if (sortBy) { params.sort_by = sortBy; params.sort_order = sortOrder }
      Object.entries(filters).forEach(([k, v]) => {
        if (Array.isArray(v) ? v.length > 0 : v !== '') params[k] = v
      })
      const data = await getCities(params)
      setCities(data)
    } finally {
      setLoading(false)
      setFetching(false)
    }
  }, [search, filters, sortBy, sortOrder])

  const loadStats = useCallback(() => {
    getStats().then(setStats).catch(() => {})
  }, [])

  const loadUnread = useCallback(() => {
    getUnreadCities().then(d => setUnreadCityIds(new Set(d.city_ids))).catch(() => {})
  }, [])

  useEffect(() => {
    getFilterOptions().then(setFilterOptions).catch(() => {})
    getAuthStatus().then(setGmailStatus).catch(() => {})
    loadUnread()
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      await syncEmails()
      await loadCities()
      getAuthStatus().then(setGmailStatus)
      loadUnread()
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 350)
    return () => clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    loadCities()
    loadStats()
  }, [loadCities, loadStats])

  const setFilter = (key, value) => setFilters(prev => ({ ...prev, [key]: value }))
  const toggleBool = (key) => setFilters(prev => ({ ...prev, [key]: prev[key] === 'true' ? '' : 'true' }))
  const clearFilters = () => setFilters(EMPTY_FILTERS)

  const activeFilterCount = Object.values(filters).filter(v => Array.isArray(v) ? v.length > 0 : Boolean(v)).length

  const handleSelect = (id, checked) => {
    setSelected(prev => {
      const next = new Set(prev)
      checked ? next.add(id) : next.delete(id)
      return next
    })
  }

  const handleSelectAll = () => setSelected(new Set(cities.map(c => c.id)))
  const handleDeselectAll = () => setSelected(new Set())

  const handleOptimisticCityUpdate = (id, fields) => {
    setCities(prev => prev.map(c => c.id === id ? { ...c, ...fields } : c))
    setActiveCity(prev => prev?.id === id ? { ...prev, ...fields } : prev)
  }

  const handleCityUpdate = (updated) => {
    setCities(prev => prev.map(c => c.id === updated.id ? updated : c))
    setActiveCity(prev => prev?.id === updated.id ? updated : prev)
    loadStats()
    loadUnread()
  }

  const handleBatchStatus = (status) => {
    const ids = [...selected]
    setCities(prev => prev.map(c => ids.includes(c.id) ? { ...c, outreach_status: status } : c))
    setSelected(new Set())
    batchUpdate(ids, { outreach_status: status }).then(loadStats)
  }

  const handleGenerateDrafts = async (draft_type) => {
    if (selected.size === 0) return
    setGenerating(true)
    try {
      const result = await generateDrafts([...selected], draft_type)
      setSelected(new Set())
      setView('review')
      setReviewBatchId(result.batch_id)
      setReviewCityCount(result.city_count)
    } finally {
      setGenerating(false)
    }
  }

  const handleSort = (col) => {
    if (sortBy === col) setSortOrder(o => o === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortOrder('asc') }
  }

  const endorsed = stats?.by_status?.endorsed || 0
  const contacted = Object.entries(stats?.by_status || {})
    .filter(([k]) => !['no_contact_info', 'city_contact_only', 'not_pursuing'].includes(k))
    .reduce((s, [, v]) => s + v, 0)

  const allVisibleSelected = cities.length > 0 && cities.every(c => selected.has(c.id))

  return (
    <div className="h-screen flex flex-col bg-gray-50 font-sans">

      {/* Top loading bar */}
      {(loading || fetching) && (
        <div className="fixed top-0 left-0 right-0 h-0.5 z-[100] overflow-hidden bg-blue-100">
          <div className="loading-bar h-full w-full bg-gradient-to-r from-transparent via-blue-500 to-transparent" />
        </div>
      )}

      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 shrink-0">
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-900">Mayor Endorsement Tracker</h1>
          <p className="text-xs text-gray-400">Ben Allen for Insurance Commissioner</p>
        </div>

        <input
          type="text"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="Search cities, mayors, counties..."
          className="w-56 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
        />

        {/* Filters toggle */}
        <button
          onClick={() => setShowFilters(f => !f)}
          className={`relative text-sm px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
            showFilters || activeFilterCount > 0
              ? 'bg-blue-600 text-white border-blue-600'
              : 'border-gray-200 text-gray-600 bg-white hover:border-gray-300'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18M7 12h10M11 20h2" />
          </svg>
          Filters
          {activeFilterCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 bg-amber-400 text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center leading-none">
              {activeFilterCount}
            </span>
          )}
        </button>

        {/* Gmail status */}
        {gmailStatus?.connected ? (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 flex items-center gap-1.5 disabled:opacity-50"
          >
            {syncing ? <Spinner /> : <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />}
            {syncing ? 'Syncing...' : 'Sync Gmail'}
          </button>
        ) : (
          <a
            href={`${import.meta.env.VITE_API_BASE_URL || ''}/api/auth/gmail`}
            className="text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50"
          >
            Connect Gmail
          </a>
        )}

        <div className="flex border border-gray-200 rounded-lg overflow-hidden text-sm">
          <button
            className={`px-3 py-1.5 ${view === 'kanban' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => setView('kanban')}
          >Board</button>
          <button
            className={`px-3 py-1.5 ${view === 'table' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => setView('table')}
          >Table</button>
          <button
            className={`px-3 py-1.5 ${view === 'review' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => { setView('review'); setReviewBatchId(null) }}
          >Drafts</button>
          <button
            className={`px-3 py-1.5 ${view === 'mail-merge' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => { setView('mail-merge'); setMailMergeInitialCityIds([]) }}
          >Mail Merge</button>
        </div>
      </header>

      <PipelineBar stats={stats} />

      {/* Filter panel */}
      {showFilters && (
        <div className="bg-white border-b border-gray-200 px-4 pt-3 pb-4 shrink-0">
          <div className="flex flex-wrap gap-x-4 gap-y-3 items-end">

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Status</label>
              <MultiSelectDropdown
                label="statuses"
                options={STATUSES.map(s => s.key)}
                selected={filters.status}
                onChange={v => setFilter('status', v)}
                formatOption={key => STATUSES.find(s => s.key === key)?.label ?? key}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Tier</label>
              <MultiSelectDropdown
                label="tiers"
                options={['1', '2', '3']}
                selected={filters.tier.map(String)}
                onChange={v => setFilter('tier', v)}
                formatOption={v => `Tier ${v}`}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">County</label>
              <MultiSelectDropdown
                label="counties"
                options={filterOptions.counties}
                selected={filters.county}
                onChange={v => setFilter('county', v)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Senate District</label>
              <MultiSelectDropdown
                label="SDs"
                options={filterOptions.senate_districts}
                selected={filters.state_senate_district}
                onChange={v => setFilter('state_senate_district', v)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Assembly District</label>
              <MultiSelectDropdown
                label="ADs"
                options={filterOptions.assembly_districts}
                selected={filters.state_assembly_district}
                onChange={v => setFilter('state_assembly_district', v)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Congressional</label>
              <MultiSelectDropdown
                label="CDs"
                options={filterOptions.congressional_districts}
                selected={filters.congressional_district}
                onChange={v => setFilter('congressional_district', v)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Wildfire Risk</label>
              <MultiSelectDropdown
                label="risk levels"
                options={['high', 'medium', 'low']}
                selected={filters.wildfire_risk_tier}
                onChange={v => setFilter('wildfire_risk_tier', v)}
                formatOption={v => v.charAt(0).toUpperCase() + v.slice(1)}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400 font-medium">Flags</label>
              <div className="flex gap-1.5 flex-wrap">
                <BoolPill active={filters.moratorium_active === 'true'} onToggle={() => toggleBool('moratorium_active')}
                  label="🔥 Moratorium" activeClass="bg-orange-500 text-white border-orange-500" />
                <BoolPill active={filters.is_distressed_county === 'true'} onToggle={() => toggleBool('is_distressed_county')}
                  label="Distressed" activeClass="bg-amber-500 text-white border-amber-500" />
                <BoolPill active={filters.has_undermarketed_zips === 'true'} onToggle={() => toggleBool('has_undermarketed_zips')}
                  label="Undermarketed" activeClass="bg-amber-500 text-white border-amber-500" />
                <BoolPill active={filters.needs_verification === 'true'} onToggle={() => toggleBool('needs_verification')}
                  label="Mayor Unverified" activeClass="bg-red-500 text-white border-red-500" />
              </div>
            </div>

            {/* Right side: count + actions */}
            <div className="flex flex-col gap-1.5 ml-auto items-end">
              <span className="text-xs text-gray-500 font-medium">{cities.length} cities match</span>
              <div className="flex gap-2 items-center">
                {activeFilterCount > 0 && (
                  <button onClick={clearFilters}
                    className="text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white">
                    Clear filters
                  </button>
                )}
                <button
                  onClick={allVisibleSelected ? handleDeselectAll : handleSelectAll}
                  className="text-xs bg-gray-900 text-white rounded-lg px-3 py-1.5 hover:bg-gray-700"
                >
                  {allVisibleSelected ? `Deselect all ${cities.length}` : `Select all ${cities.length}`}
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

      <main className={`flex-1 overflow-hidden transition-opacity duration-150 ${view !== 'mail-merge' ? 'px-4 py-3' : ''} ${fetching && !loading ? 'opacity-60 pointer-events-none' : ''}`}>
        {view === 'mail-merge' ? (
          <MailMerge
            initialCityIds={mailMergeInitialCityIds}
            onBack={() => setView('kanban')}
          />
        ) : view === 'review' ? (
          <ReviewQueue
            batchId={reviewBatchId}
            expectedCount={reviewCityCount}
            onBack={() => setView('kanban')}
            onSend={() => { loadCities(); loadUnread() }}
          />
        ) : loading ? (
          view === 'table' ? (
            <div className="overflow-auto h-full">
              <table className="w-full text-sm border-collapse">
                <thead className="sticky top-0 bg-gray-50 z-10">
                  <tr>
                    {['', 'City', 'Mayor', 'County', 'Pop.', 'Tier', 'Status', 'FAIR Plan', 'Last Contact'].map(h => (
                      <th key={h} className="p-2 text-left text-xs font-semibold text-gray-600">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody><SkeletonTableRows /></tbody>
              </table>
            </div>
          ) : (
            <SkeletonKanban />
          )
        ) : view === 'kanban' ? (
          <KanbanBoard
            cities={cities}
            onCityClick={setActiveCity}
            selected={selected}
            onSelect={handleSelect}
            unreadCityIds={unreadCityIds}
          />
        ) : (
          <TableView
            cities={cities}
            onCityClick={setActiveCity}
            selected={selected}
            onSelect={handleSelect}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSort={handleSort}
          />
        )}
      </main>

      {/* Batch action bar */}
      {selected.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 bg-gray-900 text-white px-4 py-3 flex items-center gap-3 z-40">
          <span className="text-sm font-medium">{selected.size} cities selected</span>
          {!allVisibleSelected && cities.length > selected.size && (
            <button onClick={handleSelectAll}
              className="text-xs text-gray-400 hover:text-white underline underline-offset-2">
              Select all {cities.length} visible
            </button>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={() => {
                setMailMergeInitialCityIds([...selected])
                setSelected(new Set())
                setView('mail-merge')
              }}
              className="bg-violet-600 hover:bg-violet-500 text-sm px-3 py-1.5 rounded"
            >
              Mail Merge
            </button>
            <button
              disabled={generating}
              onClick={() => handleGenerateDrafts('info_request')}
              className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-sm px-3 py-1.5 rounded flex items-center gap-2"
            >
              {generating && <Spinner />}
              {generating ? 'Starting...' : 'Info request emails'}
            </button>
            <button
              disabled={generating}
              onClick={() => handleGenerateDrafts('endorsement_outreach')}
              className="bg-blue-500 hover:bg-blue-400 disabled:opacity-50 text-sm px-3 py-1.5 rounded flex items-center gap-2"
            >
              {generating && <Spinner />}
              {generating ? 'Starting...' : 'Outreach emails'}
            </button>
            <select
              className="text-sm bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white"
              onChange={e => { if (e.target.value) handleBatchStatus(e.target.value) }}
              defaultValue=""
            >
              <option value="">Move to stage...</option>
              {STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            <button
              className="text-gray-400 hover:text-white text-sm px-3 py-1.5"
              onClick={handleDeselectAll}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      <CityDetailPanel
        city={activeCity}
        onClose={() => setActiveCity(null)}
        onUpdate={handleCityUpdate}
        onOptimisticUpdate={handleOptimisticCityUpdate}
      />
    </div>
  )
}
