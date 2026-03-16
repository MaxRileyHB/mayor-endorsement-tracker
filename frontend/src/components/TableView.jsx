import { STATUS_MAP, TIER_COLORS } from '../constants'
import * as XLSX from 'xlsx'

const COLUMNS = [
  { key: 'city_name', label: 'City', sort: true },
  { key: 'mayor', label: 'Mayor', sort: true },
  { key: 'county', label: 'County', sort: true },
  { key: 'population', label: 'Pop.', sort: true },
  { key: 'outreach_tier', label: 'Tier', sort: true },
  { key: 'outreach_status', label: 'Status', sort: true },
  { key: 'fair_plan_policies', label: 'FAIR Plan', sort: true },
  { key: 'last_contacted', label: 'Last Contact', sort: true },
]

function exportToExcel(cities) {
  const rows = cities.map(c => ({
    'City': c.city_name || '',
    'Mayor': c.mayor || '',
    'County': c.county || '',
    'Population': c.population || '',
    'Tier': c.outreach_tier || '',
    'Status': STATUS_MAP[c.outreach_status]?.label || c.outreach_status || '',
    'City Email': c.city_email || '',
    'Mayor Email': c.mayor_email || '',
    'City Phone': c.city_phone || '',
    'Mayor Phone': c.mayor_phone || '',
    'FAIR Plan Policies': c.fair_plan_policies || '',
    'FAIR Plan Exposure': c.fair_plan_exposure || '',
    'Wildfire Risk': c.wildfire_risk_tier || '',
    'Moratorium Active': c.moratorium_active ? 'Yes' : '',
    'Distressed County': c.is_distressed_county ? 'Yes' : '',
    'Congressional District': c.congressional_district || '',
    'Senate District': c.state_senate_district || '',
    'Assembly District': c.state_assembly_district || '',
    'Last Contacted': c.last_contacted ? new Date(c.last_contacted).toLocaleDateString() : '',
    'Next Action': c.next_action || '',
    'Next Action Date': c.next_action_date || '',
    'Notes': c.notes || '',
  }))

  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Cities')

  const date = new Date().toISOString().slice(0, 10)
  XLSX.writeFile(wb, `mayor-endorsements-${date}.xlsx`)
}

export default function TableView({ cities, onCityClick, selected, onSelect, sortBy, sortOrder, onSort }) {
  const allSelected = cities.length > 0 && cities.every(c => selected.has(c.id))

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-1 pb-2 shrink-0">
        <span className="text-xs text-gray-400">{cities.length} cities</span>
        <button
          onClick={() => exportToExcel(cities)}
          className="text-xs border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-600 hover:bg-gray-50 flex items-center gap-1.5"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Export to Excel
        </button>
      </div>
    <div className="overflow-auto flex-1">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          <tr>
            <th className="p-2 w-8">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={(e) => cities.forEach(c => onSelect(c.id, e.target.checked))}
              />
            </th>
            {COLUMNS.map(col => (
              <th
                key={col.key}
                className={`p-2 text-left text-xs font-semibold text-gray-600 whitespace-nowrap
                  ${col.sort ? 'cursor-pointer hover:text-gray-900' : ''}`}
                onClick={() => col.sort && onSort(col.key)}
              >
                {col.label}
                {sortBy === col.key && (
                  <span className="ml-1 text-gray-400">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cities.map((city, i) => {
            const statusMeta = STATUS_MAP[city.outreach_status] || STATUS_MAP['no_contact_info']
            const tier = city.outreach_tier || 3
            return (
              <tr
                key={city.id}
                className={`border-t border-gray-100 cursor-pointer hover:bg-blue-50 transition-colors
                  ${selected.has(city.id) ? 'bg-blue-50' : i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}
                onClick={() => onCityClick(city)}
              >
                <td className="p-2" onClick={e => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(city.id)}
                    onChange={(e) => onSelect(city.id, e.target.checked)}
                  />
                </td>
                <td className="p-2 font-medium text-gray-900 whitespace-nowrap">{city.city_name}</td>
                <td className="p-2 text-gray-600">{city.mayor || <span className="text-gray-300 italic">—</span>}</td>
                <td className="p-2 text-gray-500">{city.county}</td>
                <td className="p-2 text-gray-500 text-right">
                  {city.population ? (city.population >= 1000
                    ? `${(city.population / 1000).toFixed(0)}k`
                    : city.population) : '—'}
                </td>
                <td className="p-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${TIER_COLORS[tier]}`}>
                    T{tier}
                  </span>
                </td>
                <td className="p-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${statusMeta.color}`}>
                    {statusMeta.label}
                  </span>
                </td>
                <td className="p-2 text-gray-500 text-right">
                  {city.fair_plan_policies > 0 ? city.fair_plan_policies.toLocaleString() : '—'}
                </td>
                <td className="p-2 text-gray-400 text-xs">
                  {city.last_contacted
                    ? new Date(city.last_contacted).toLocaleDateString()
                    : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
    </div>
  )
}
