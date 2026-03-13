import { STATUS_MAP, TIER_COLORS } from '../constants'

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

export default function TableView({ cities, onCityClick, selected, onSelect, sortBy, sortOrder, onSort }) {
  const allSelected = cities.length > 0 && cities.every(c => selected.has(c.id))

  return (
    <div className="overflow-auto h-full">
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
  )
}
