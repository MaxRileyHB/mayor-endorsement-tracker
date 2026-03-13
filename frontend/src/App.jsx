import { useState, useEffect, useCallback } from 'react'
import { getCities, getStats, batchUpdate } from './api'
import KanbanBoard from './components/KanbanBoard'
import TableView from './components/TableView'
import CityDetailPanel from './components/CityDetailPanel'
import { STATUSES } from './constants'

export default function App() {
  const [cities, setCities] = useState([])
  const [stats, setStats] = useState(null)
  const [view, setView] = useState('kanban')
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterTier, setFilterTier] = useState('')
  const [sortBy, setSortBy] = useState('city_name')
  const [sortOrder, setSortOrder] = useState('asc')
  const [selected, setSelected] = useState(new Set())
  const [activeCity, setActiveCity] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadCities = useCallback(async () => {
    try {
      const params = { per_page: 500 }
      if (search) params.search = search
      if (filterStatus) params.status = filterStatus
      if (filterTier) params.tier = filterTier
      if (sortBy) { params.sort_by = sortBy; params.sort_order = sortOrder }
      const data = await getCities(params)
      setCities(data)
    } finally {
      setLoading(false)
    }
  }, [search, filterStatus, filterTier, sortBy, sortOrder])

  const loadStats = useCallback(() => {
    getStats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    loadCities()
    loadStats()
  }, [loadCities, loadStats])

  const handleSelect = (id, checked) => {
    setSelected(prev => {
      const next = new Set(prev)
      checked ? next.add(id) : next.delete(id)
      return next
    })
  }

  const handleCityUpdate = (updated) => {
    setCities(prev => prev.map(c => c.id === updated.id ? updated : c))
    if (activeCity?.id === updated.id) setActiveCity(updated)
    loadStats()
  }

  const handleBatchStatus = async (status) => {
    await batchUpdate([...selected], { outreach_status: status })
    setSelected(new Set())
    loadCities()
    loadStats()
  }

  const handleSort = (col) => {
    if (sortBy === col) setSortOrder(o => o === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortOrder('asc') }
  }

  const endorsed = stats?.by_status?.endorsed || 0
  const contacted = Object.entries(stats?.by_status || {})
    .filter(([k]) => !['no_contact_info', 'city_contact_only', 'not_pursuing'].includes(k))
    .reduce((s, [, v]) => s + v, 0)

  return (
    <div className="h-screen flex flex-col bg-gray-50 font-sans">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-4 shrink-0">
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-900">Mayor Endorsement Tracker</h1>
          <p className="text-xs text-gray-400">
            {stats?.total || '—'} cities · {contacted} contacted · {endorsed} endorsed
          </p>
        </div>

        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search cities, mayors, counties..."
          className="w-64 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
        />

        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700"
        >
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>

        <select
          value={filterTier}
          onChange={e => setFilterTier(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700"
        >
          <option value="">All tiers</option>
          <option value="1">Tier 1</option>
          <option value="2">Tier 2</option>
          <option value="3">Tier 3</option>
        </select>

        <div className="flex border border-gray-200 rounded-lg overflow-hidden text-sm">
          <button
            className={`px-3 py-1.5 ${view === 'kanban' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => setView('kanban')}
          >
            Board
          </button>
          <button
            className={`px-3 py-1.5 ${view === 'table' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            onClick={() => setView('table')}
          >
            Table
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden px-4 py-3">
        {loading ? (
          <div className="flex items-center justify-center h-full text-gray-400">Loading cities...</div>
        ) : view === 'kanban' ? (
          <KanbanBoard
            cities={cities}
            onCityClick={setActiveCity}
            selected={selected}
            onSelect={handleSelect}
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
          <div className="flex gap-2 ml-auto">
            <button className="bg-amber-500 hover:bg-amber-400 text-sm px-3 py-1.5 rounded">
              Info request emails
            </button>
            <button className="bg-blue-500 hover:bg-blue-400 text-sm px-3 py-1.5 rounded">
              Outreach emails
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
              onClick={() => setSelected(new Set())}
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
      />
    </div>
  )
}
