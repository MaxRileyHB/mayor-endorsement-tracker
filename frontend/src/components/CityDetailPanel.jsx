import { useState, useEffect } from 'react'
import { updateCity, getActivity } from '../api'
import { STATUSES, TIER_COLORS } from '../constants'

export default function CityDetailPanel({ city, onClose, onUpdate }) {
  const [editing, setEditing] = useState({})
  const [saving, setSaving] = useState(false)
  const [activity, setActivity] = useState([])
  const [note, setNote] = useState('')

  useEffect(() => {
    if (city) {
      setEditing({})
      getActivity(city.id).then(setActivity).catch(() => {})
    }
  }, [city?.id])

  if (!city) return null

  const tier = city.outreach_tier || 3

  const save = async (fields) => {
    setSaving(true)
    try {
      const updated = await updateCity(city.id, fields)
      onUpdate(updated)
    } finally {
      setSaving(false)
    }
  }

  const saveNote = async () => {
    if (!note.trim()) return
    await save({ notes: city.notes ? `${city.notes}\n\n${new Date().toLocaleDateString()}: ${note}` : `${new Date().toLocaleDateString()}: ${note}` })
    setNote('')
  }

  const flags = [
    city.moratorium_active && { label: 'Active Moratorium', color: 'bg-orange-100 text-orange-700' },
    city.is_distressed_county && { label: 'Distressed County', color: 'bg-amber-100 text-amber-700' },
    city.has_undermarketed_zips && { label: 'Undermarketed ZIPs', color: 'bg-amber-100 text-amber-700' },
    city.mayor_needs_verification && { label: 'Mayor Unverified', color: 'bg-red-100 text-red-600' },
    city.wildfire_risk_tier === 'high' && { label: 'High Wildfire Risk', color: 'bg-red-100 text-red-600' },
  ].filter(Boolean)

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div
        className="bg-white w-full max-w-xl h-full shadow-2xl overflow-y-auto flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-5 py-4 z-10">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">{city.city_name}</h2>
              <p className="text-sm text-gray-500">
                {city.mayor || 'Mayor unknown'} · {city.county} · {city.population?.toLocaleString() || '—'}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-xs px-2 py-1 rounded border font-medium ${TIER_COLORS[tier]}`}>T{tier}</span>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
            </div>
          </div>

          {/* Insurance flags */}
          {flags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {flags.map(f => (
                <span key={f.label} className={`text-xs px-2 py-0.5 rounded ${f.color}`}>{f.label}</span>
              ))}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 mt-3">
            <select
              value={city.outreach_status}
              onChange={e => save({ outreach_status: e.target.value })}
              className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white text-gray-700 flex-1"
            >
              {STATUSES.map(s => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
            <button className="bg-blue-600 text-white text-xs px-3 py-1.5 rounded hover:bg-blue-700 whitespace-nowrap">
              Draft outreach
            </button>
            <button className="bg-amber-500 text-white text-xs px-3 py-1.5 rounded hover:bg-amber-600 whitespace-nowrap">
              Info request
            </button>
          </div>
        </div>

        <div className="flex-1 px-5 py-4 space-y-5">
          {/* Insurance data */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Insurance Data</h3>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-gray-50 rounded p-2.5">
                <div className="text-lg font-semibold text-gray-900">
                  {city.fair_plan_policies?.toLocaleString() || '—'}
                </div>
                <div className="text-xs text-gray-500">FAIR Plan Policies</div>
              </div>
              <div className="bg-gray-50 rounded p-2.5">
                <div className="text-lg font-semibold text-gray-900">
                  {city.fair_plan_exposure
                    ? `$${(city.fair_plan_exposure / 1e6).toFixed(0)}M`
                    : '—'}
                </div>
                <div className="text-xs text-gray-500">Exposure</div>
              </div>
              <div className="bg-gray-50 rounded p-2.5">
                <div className="text-lg font-semibold text-gray-900 capitalize">
                  {city.wildfire_risk_tier || '—'}
                </div>
                <div className="text-xs text-gray-500">Wildfire Risk</div>
              </div>
            </div>
            {city.moratorium_fires?.length > 0 && (
              <p className="text-xs text-orange-700 mt-2">
                Moratorium fires: {Array.isArray(city.moratorium_fires)
                  ? city.moratorium_fires.join(', ')
                  : city.moratorium_fires}
              </p>
            )}
          </section>

          {/* Contact */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Contact</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-gray-500 mb-1 font-medium">City</p>
                <ContactField label="Email" value={city.city_email} />
                <ContactField label="Phone" value={city.city_phone} />
                <ContactField label="Website" value={city.city_website} link />
                <ContactField label="Clerk" value={city.city_clerk} />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1 font-medium">Mayor Direct</p>
                <ContactField label="Email" value={city.mayor_email} editable
                  onSave={v => save({ mayor_email: v })} />
                <ContactField label="Phone" value={city.mayor_phone} editable
                  onSave={v => save({ mayor_phone: v })} />
                {!city.mayor_email && !city.mayor_phone && (
                  <p className="text-xs text-gray-400 italic">Not yet collected</p>
                )}
              </div>
            </div>
          </section>

          {/* Officials */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Officials</h3>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Mayor</span>
                <span className="text-gray-900 font-medium">{city.mayor || '—'}</span>
              </div>
              {city.mayor_pro_tem && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Mayor Pro Tem</span>
                  <span className="text-gray-700">{city.mayor_pro_tem}</span>
                </div>
              )}
              {city.city_manager && (
                <div className="flex justify-between">
                  <span className="text-gray-500">City Manager</span>
                  <span className="text-gray-700">{city.city_manager}</span>
                </div>
              )}
            </div>
          </section>

          {/* Districts */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Districts</h3>
            <div className="flex gap-4 text-sm">
              {city.congressional_district && (
                <div><span className="text-gray-500">CD</span> <span className="font-medium">{city.congressional_district}</span></div>
              )}
              {city.state_senate_district && (
                <div><span className="text-gray-500">SD</span> <span className="font-medium">{city.state_senate_district}</span></div>
              )}
              {city.state_assembly_district && (
                <div><span className="text-gray-500">AD</span> <span className="font-medium">{city.state_assembly_district}</span></div>
              )}
            </div>
          </section>

          {/* Notes */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Notes</h3>
            {city.notes && (
              <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded p-3 mb-2">
                {city.notes}
              </div>
            )}
            <div className="flex gap-2">
              <input
                type="text"
                value={note}
                onChange={e => setNote(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && saveNote()}
                placeholder="Add a note..."
                className="flex-1 text-sm border border-gray-200 rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
              <button
                onClick={saveNote}
                disabled={!note.trim() || saving}
                className="bg-gray-800 text-white text-sm px-3 py-1.5 rounded hover:bg-gray-700 disabled:opacity-40"
              >
                Add
              </button>
            </div>
          </section>

          {/* Next action */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Next Action</h3>
            <div className="flex gap-2">
              <input
                type="text"
                defaultValue={city.next_action || ''}
                onBlur={e => save({ next_action: e.target.value })}
                placeholder="e.g. Follow up after call Thursday"
                className="flex-1 text-sm border border-gray-200 rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
              <input
                type="date"
                defaultValue={city.next_action_date || ''}
                onBlur={e => save({ next_action_date: e.target.value || null })}
                className="text-sm border border-gray-200 rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
          </section>

          {/* Activity log */}
          {activity.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Activity</h3>
              <div className="space-y-1">
                {activity.slice(0, 10).map(log => (
                  <div key={log.id} className="flex gap-2 text-xs text-gray-500">
                    <span className="text-gray-400 shrink-0">
                      {new Date(log.created_at).toLocaleDateString()}
                    </span>
                    <span>{log.action}: {log.details}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

function ContactField({ label, value, link, editable, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(value || '')

  if (!value && !editable) return null

  if (editable && editing) {
    return (
      <div className="flex gap-1 mb-1">
        <input
          autoFocus
          type="text"
          value={val}
          onChange={e => setVal(e.target.value)}
          onBlur={() => { onSave(val); setEditing(false) }}
          onKeyDown={e => { if (e.key === 'Enter') { onSave(val); setEditing(false) } }}
          className="text-xs border rounded px-1.5 py-0.5 flex-1"
        />
      </div>
    )
  }

  return (
    <div className="flex items-baseline gap-1 mb-1 text-xs">
      <span className="text-gray-400 w-12 shrink-0">{label}</span>
      {value ? (
        link ? (
          <a href={value.startsWith('http') ? value : `https://${value}`}
            target="_blank" rel="noreferrer"
            className="text-blue-600 hover:underline truncate">{value}</a>
        ) : (
          <span
            className={`text-gray-700 truncate ${editable ? 'cursor-pointer hover:text-blue-600' : ''}`}
            onClick={() => editable && setEditing(true)}
          >{value}</span>
        )
      ) : editable ? (
        <button onClick={() => setEditing(true)} className="text-blue-500 hover:underline italic">
          Add...
        </button>
      ) : null}
    </div>
  )
}
