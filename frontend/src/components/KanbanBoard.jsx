import { STATUSES } from '../constants'
import CityCard from './CityCard'

export default function KanbanBoard({ cities, onCityClick, selected, onSelect, unreadCityIds = new Set() }) {
  const byStatus = {}
  for (const s of STATUSES) byStatus[s.key] = []
  for (const city of cities) {
    const key = city.outreach_status || 'no_contact_info'
    if (byStatus[key]) byStatus[key].push(city)
    else byStatus['no_contact_info'].push(city)
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-4 h-full">
      {STATUSES.map((status) => {
        const cols = byStatus[status.key] || []
        // Sort: unread cities float to top
        const sorted = [...cols].sort((a, b) => {
          const aUnread = unreadCityIds.has(a.id) ? 0 : 1
          const bUnread = unreadCityIds.has(b.id) ? 0 : 1
          return aUnread - bUnread
        })
        const unreadCount = cols.filter(c => unreadCityIds.has(c.id)).length
        return (
          <div key={status.key} className="flex-none w-56">
            <div className="flex items-center gap-2 mb-2 px-1">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${status.color}`}>
                {status.label}
              </span>
              <span className="text-xs text-gray-400">{cols.length}</span>
              {unreadCount > 0 && (
                <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">
                  {unreadCount} response{unreadCount > 1 ? 's' : ''}
                </span>
              )}
            </div>
            <div className="flex flex-col gap-2">
              {sorted.map((city) => (
                <CityCard
                  key={city.id}
                  city={city}
                  onClick={onCityClick}
                  selected={selected.has(city.id)}
                  onSelect={onSelect}
                  hasUnread={unreadCityIds.has(city.id)}
                />
              ))}
              {cols.length === 0 && (
                <div className="text-xs text-gray-300 text-center py-4">—</div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
