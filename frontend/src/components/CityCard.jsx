import { TIER_COLORS, STATUS_MAP } from '../constants'

function contactCompleteness(city) {
  const hasEmail = city.mayor_work_email || city.mayor_personal_email
  const hasPhone = city.mayor_work_phone || city.mayor_personal_phone
  const hasSocial = city.mayor_instagram || city.mayor_facebook || city.mayor_other_social_handle
  if (hasEmail && (hasPhone || hasSocial)) return 'strong'
  if (hasEmail || hasPhone || hasSocial) return 'partial'
  if (city.city_email || city.city_phone) return 'minimal'
  return 'none'
}

const COMPLETENESS_DOT = {
  strong:  { color: 'bg-green-400',  title: 'Mayor contact: email + phone/social' },
  partial: { color: 'bg-yellow-400', title: 'Mayor contact: partial (email or phone/social)' },
  minimal: { color: 'bg-red-400',    title: 'City contact only — no mayor direct info' },
  none:    { color: 'bg-gray-300',   title: 'No contact info at all' },
}

export default function CityCard({ city, onClick, selected, onSelect, hasUnread = false }) {
  const tier = city.outreach_tier || 3
  const completeness = contactCompleteness(city)
  const dot = COMPLETENESS_DOT[completeness]

  return (
    <div
      className={`bg-white border rounded-lg p-3 cursor-pointer hover:shadow-md transition-shadow text-sm
        ${selected ? 'ring-2 ring-blue-500 border-blue-300' : 'border-gray-200'}`}
      onClick={() => onClick(city)}
    >
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => { e.stopPropagation(); onSelect(city.id, e.target.checked) }}
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5 shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-semibold text-gray-900 truncate">{city.city_name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded border font-medium shrink-0 ${TIER_COLORS[tier]}`}>
              T{tier}
            </span>
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${dot.color}`}
              title={dot.title}
            />
            {hasUnread && (
              <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium shrink-0">
                Response
              </span>
            )}
          </div>

          <div className="text-gray-500 text-xs mt-0.5 truncate">
            {city.mayor || <span className="italic text-gray-400">Mayor unknown</span>}
          </div>

          <div className="text-gray-400 text-xs mt-0.5">
            {city.county} · {city.population ? `${(city.population / 1000).toFixed(0)}k` : '—'}
          </div>

          <div className="flex flex-wrap gap-1 mt-1.5">
            {city.moratorium_active && (
              <span className="bg-orange-100 text-orange-700 text-xs px-1.5 py-0.5 rounded">
                Moratorium
              </span>
            )}
            {city.is_distressed_county && (
              <span className="bg-amber-100 text-amber-700 text-xs px-1.5 py-0.5 rounded">
                Distressed
              </span>
            )}
            {city.fair_plan_policies > 500 && (
              <span className="bg-amber-100 text-amber-700 text-xs px-1.5 py-0.5 rounded">
                FAIR {city.fair_plan_policies?.toLocaleString()}
              </span>
            )}
            {city.mayor_needs_verification && (
              <span className="bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded">
                Verify mayor
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
