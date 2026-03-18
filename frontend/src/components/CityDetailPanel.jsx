import { useState, useEffect } from 'react'
import { updateCity, getCity, getActivity, getCityDrafts, getCityEmails, getCityCalls, createCallLog, deleteCallLog, updateDraft, regenerateDraft, generateDrafts, sendDrafts } from '../api'
import { STATUSES, TIER_COLORS } from '../constants'
import { SkeletonSection } from './Skeleton'

const DRAFT_TYPE_LABEL = { info_request: 'Info Request', endorsement_outreach: 'Outreach' }
const DRAFT_TYPE_COLOR = { info_request: 'bg-amber-100 text-amber-700', endorsement_outreach: 'bg-blue-100 text-blue-700' }
const DRAFT_STATUS_COLOR = {
  pending_review: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  edited: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-500',
  sent: 'bg-gray-100 text-gray-500',
}
const DRAFT_BORDER = {
  pending_review: 'border-l-amber-400',
  approved: 'border-l-green-400',
  edited: 'border-l-green-400',
  rejected: 'border-l-red-300',
  sent: 'border-l-gray-300',
}

export default function CityDetailPanel({ city, onClose, onUpdate, onOptimisticUpdate }) {
  const [saving, setSaving] = useState(false)
  const [activity, setActivity] = useState([])
  const [note, setNote] = useState('')
  const [drafts, setDrafts] = useState([])
  const [emails, setEmails] = useState([])
  const [drafting, setDrafting] = useState(null)
  const [generatingBatchId, setGeneratingBatchId] = useState(null)
  const [loadingDrafts, setLoadingDrafts] = useState(false)
  const [loadingEmails, setLoadingEmails] = useState(false)
  const [calls, setCalls] = useState([])
  const [loggingCall, setLoggingCall] = useState(false)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (!city) return
    setNote('')
    setDrafting(null)
    setGeneratingBatchId(null)
    setDrafts([])
    setEmails([])
    setCalls([])
    setLoggingCall(false)
    setLoadingDrafts(true)
    setLoadingEmails(true)
    getActivity(city.id).then(setActivity).catch(() => {})
    getCityDrafts(city.id).then(setDrafts).catch(() => {}).finally(() => setLoadingDrafts(false))
    getCityEmails(city.id).then(setEmails).catch(() => {}).finally(() => setLoadingEmails(false))
    getCityCalls(city.id).then(setCalls).catch(() => {})
  }, [city?.id])

  // Poll for new draft after clicking generate
  useEffect(() => {
    if (!generatingBatchId || !city) return
    const interval = setInterval(() => {
      getCityDrafts(city.id).then(data => {
        setDrafts(data)
        if (data.some(d => d.batch_id === generatingBatchId)) {
          setGeneratingBatchId(null)
          setDrafting(null)
          clearInterval(interval)
        }
      }).catch(() => {})
    }, 2000)
    return () => clearInterval(interval)
  }, [generatingBatchId, city?.id])

  if (!city) return null

  const tier = city.outreach_tier || 3

  const save = async (fields) => {
    setSaving(true)
    onOptimisticUpdate?.(city.id, fields)
    try {
      const updated = await updateCity(city.id, fields)
      onUpdate(updated)
    } finally {
      setSaving(false)
    }
  }

  const saveNote = async () => {
    if (!note.trim()) return
    const updated = city.notes
      ? `${city.notes}\n\n${new Date().toLocaleDateString()}: ${note}`
      : `${new Date().toLocaleDateString()}: ${note}`
    await save({ notes: updated })
    setNote('')
  }

  const handleDraft = async (draftType) => {
    setDrafting(draftType)
    try {
      const result = await generateDrafts([city.id], draftType)
      setGeneratingBatchId(result.batch_id)
    } catch {
      setDrafting(null)
    }
  }

  const patchDraft = (id, fields) => {
    setDrafts(prev => prev.map(d => d.id === id ? { ...d, ...fields } : d))
    updateDraft(id, fields).then(updated =>
      setDrafts(prev => prev.map(d => d.id === id ? { ...d, ...updated } : d))
    )
  }

  const handleLogCall = async ({ notes, outcome, contact_type, called_at }) => {
    const optimistic = { id: `tmp-${Date.now()}`, city_id: city.id, notes, outcome, contact_type, called_at: called_at || new Date().toISOString() }
    setCalls(prev => [optimistic, ...prev])
    setLoggingCall(false)
    const saved = await createCallLog(city.id, { notes, outcome, contact_type, called_at: called_at || undefined })
    setCalls(prev => prev.map(c => c.id === optimistic.id ? saved : c))
  }

  const handleDeleteCall = (callId) => {
    setCalls(prev => prev.filter(c => c.id !== callId))
    deleteCallLog(city.id, callId).catch(() => {
      getCityCalls(city.id).then(setCalls)
    })
  }

  const handleRegenerate = async (id) => {
    const draft = drafts.find(d => d.id === id)
    setDrafts(prev => prev.map(d => d.id === id ? { ...d, status: 'rejected' } : d))
    const { batch_id } = await regenerateDraft(id)
    setGeneratingBatchId(batch_id)
    setDrafting(draft?.draft_type || 'endorsement_outreach')
  }

  const handleSend = async () => {
    const toSend = drafts.filter(d => d.status === 'approved' || d.status === 'edited')
    if (!toSend.length) return
    setSending(true)
    // Optimistic: mark them sent
    setDrafts(prev => prev.map(d => toSend.find(s => s.id === d.id) ? { ...d, status: 'sent' } : d))
    try {
      const result = await sendDrafts(toSend.map(d => d.id))
      // Reload drafts and city to reflect status advance
      getCityDrafts(city.id).then(setDrafts).catch(() => {})
      if (result.failed?.length) {
        alert(`Sent ${result.sent}. ${result.failed.length} failed — check Gmail is connected.`)
      }
      // Refresh city to reflect auto-advanced status
      getCity(city.id).then(onUpdate).catch(() => {})
    } catch {
      alert('Send failed — make sure Gmail is connected.')
      getCityDrafts(city.id).then(setDrafts).catch(() => {})
    } finally {
      setSending(false)
    }
  }

  const flags = [
    city.moratorium_active && { label: 'Active Moratorium', color: 'bg-orange-100 text-orange-700' },
    city.is_distressed_county && { label: 'Distressed County', color: 'bg-amber-100 text-amber-700' },
    city.has_undermarketed_zips && { label: 'Undermarketed ZIPs', color: 'bg-amber-100 text-amber-700' },
    city.mayor_needs_verification && { label: 'Mayor Unverified', color: 'bg-red-100 text-red-600' },
    city.wildfire_risk_tier === 'high' && { label: 'High Wildfire Risk', color: 'bg-red-100 text-red-600' },
  ].filter(Boolean)

  const activeDrafts = drafts.filter(d => d.status !== 'rejected' && d.status !== 'sent')
  const archivedDrafts = drafts.filter(d => d.status === 'rejected' || d.status === 'sent')

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
            <button
              disabled={!!drafting}
              onClick={() => handleDraft('endorsement_outreach')}
              className="bg-blue-600 text-white text-xs px-3 py-1.5 rounded hover:bg-blue-700 whitespace-nowrap disabled:opacity-50 flex items-center gap-1.5"
            >
              {drafting === 'endorsement_outreach' && <Spinner />}
              Draft outreach
            </button>
            <button
              disabled={!!drafting}
              onClick={() => handleDraft('info_request')}
              className="bg-amber-500 text-white text-xs px-3 py-1.5 rounded hover:bg-amber-600 whitespace-nowrap disabled:opacity-50 flex items-center gap-1.5"
            >
              {drafting === 'info_request' && <Spinner />}
              Info request
            </button>
          </div>
        </div>

        <div className="flex-1 px-5 py-4 space-y-5">

          {/* Drafts */}
          {(drafts.length > 0 || drafting || loadingDrafts) && (
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
                  Drafts
                  {activeDrafts.length > 0 && (
                    <span className="bg-amber-100 text-amber-700 text-xs px-1.5 py-0.5 rounded-full font-medium">
                      {activeDrafts.length}
                    </span>
                  )}
                </h3>
                {drafts.some(d => d.status === 'approved' || d.status === 'edited') && (
                  <button
                    onClick={handleSend}
                    disabled={sending}
                    className="bg-green-600 text-white text-xs px-2.5 py-1 rounded hover:bg-green-700 disabled:opacity-50 flex items-center gap-1"
                  >
                    {sending && <Spinner />}
                    Send {drafts.filter(d => d.status === 'approved' || d.status === 'edited').length} approved
                  </button>
                )}
              </div>

              <div className="space-y-2">
                {/* Initial load skeleton */}
                {loadingDrafts && !generatingBatchId && (
                  <SkeletonSection lines={2} />
                )}

                {/* Generating placeholder */}
                {generatingBatchId && (
                  <div className="border-l-2 border-l-gray-300 bg-gray-50 rounded-r px-3 py-2.5 flex items-center gap-2 text-xs text-gray-500">
                    <Spinner />
                    Generating {DRAFT_TYPE_LABEL[drafting] || 'draft'}...
                  </div>
                )}

                {activeDrafts.map(draft => (
                  <PanelDraftCard
                    key={draft.id}
                    draft={draft}
                    onPatch={patchDraft}
                    onRegenerate={handleRegenerate}
                  />
                ))}

                {archivedDrafts.length > 0 && (
                  <details className="group">
                    <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 select-none">
                      {archivedDrafts.length} archived (rejected/sent)
                    </summary>
                    <div className="space-y-2 mt-2">
                      {archivedDrafts.map(draft => (
                        <PanelDraftCard
                          key={draft.id}
                          draft={draft}
                          onPatch={patchDraft}
                          onRegenerate={handleRegenerate}
                        />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </section>
          )}

          {/* City background */}
          {city.city_blurb && (
            <section>
              <p className="text-xs text-gray-400 italic leading-relaxed">{city.city_blurb}</p>
            </section>
          )}

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
                  {city.fair_plan_exposure ? `$${(city.fair_plan_exposure / 1e6).toFixed(0)}M` : '—'}
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
                <p className="text-xs text-gray-500 mb-1 font-medium">Mayor</p>
                {(() => {
                  const wasSearched = !!city.contact_scrape_status && city.contact_scrape_status !== 'not_scraped'
                  const hasAny = city.mayor_work_email || city.mayor_work_phone || city.mayor_personal_email || city.mayor_personal_phone || city.mayor_instagram || city.mayor_facebook || city.mayor_other_social_handle
                  return (
                    <>
                      <ContactField label="Work Email" value={city.mayor_work_email} editable
                        onSave={v => save({ mayor_work_email: v })}
                        sourceUrl={city.mayor_work_email_source} wasSearched={wasSearched} />
                      <ContactField label="Work Phone" value={city.mayor_work_phone} editable
                        onSave={v => save({ mayor_work_phone: v })}
                        sourceUrl={city.mayor_work_phone_source} wasSearched={wasSearched} />
                      <ContactField label="Personal Email" value={city.mayor_personal_email} editable
                        onSave={v => save({ mayor_personal_email: v })}
                        sourceUrl={city.mayor_personal_email_source} wasSearched={wasSearched} />
                      <ContactField label="Personal Phone" value={city.mayor_personal_phone} editable
                        onSave={v => save({ mayor_personal_phone: v })}
                        sourceUrl={city.mayor_personal_phone_source} wasSearched={wasSearched} />
                      <ContactField label="Instagram" value={city.mayor_instagram} editable
                        onSave={v => save({ mayor_instagram: v })}
                        sourceUrl={city.mayor_instagram_source} wasSearched={wasSearched} />
                      <ContactField label="Facebook" value={city.mayor_facebook} editable
                        onSave={v => save({ mayor_facebook: v })}
                        sourceUrl={city.mayor_facebook_source} wasSearched={wasSearched} />
                      {city.mayor_other_social_handle && (
                        <ContactField
                          label={city.mayor_other_social_platform || 'Other'}
                          value={city.mayor_other_social_handle}
                          sourceUrl={city.mayor_other_social_source}
                        />
                      )}
                      {!hasAny && !wasSearched && (
                        <p className="text-xs text-gray-400 italic">Not yet collected</p>
                      )}
                      {city.contact_scrape_date && (
                        <p className="text-xs text-gray-300 mt-1.5">
                          Scraped {new Date(city.contact_scrape_date).toLocaleDateString()}
                          {city.contact_scrape_status === 'partial' && (
                            <span className="ml-1 text-yellow-500">· partial</span>
                          )}
                        </p>
                      )}
                    </>
                  )
                })()}
              </div>
            </div>
          </section>

          {/* Timeline: emails + calls */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
                Timeline
                {(emails.length + calls.length) > 0 && (
                  <span className="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded-full font-medium">
                    {emails.length + calls.length}
                  </span>
                )}
              </h3>
              <button
                onClick={() => setLoggingCall(l => !l)}
                className="text-xs text-gray-600 border border-gray-200 bg-white px-2.5 py-1 rounded hover:bg-gray-50"
              >
                Log call
              </button>
            </div>

            {loggingCall && (
              <LogCallForm
                city={city}
                onSave={handleLogCall}
                onCancel={() => setLoggingCall(false)}
              />
            )}

            {loadingEmails ? (
              <SkeletonSection lines={3} />
            ) : (emails.length + calls.length) === 0 ? (
              <div className="bg-gray-50 rounded p-4 text-center">
                <p className="text-xs text-gray-400">No emails or calls logged yet.</p>
                <p className="text-xs text-gray-400 mt-1">
                  Connect Gmail to sync emails, or log a call above.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {[
                  ...emails.map(e => ({ ...e, _type: 'email', _date: new Date(e.sent_at || e.created_at) })),
                  ...calls.map(c => ({ ...c, _type: 'call', _date: new Date(c.called_at || c.created_at) })),
                ]
                  .sort((a, b) => b._date - a._date)
                  .map(item =>
                    item._type === 'email'
                      ? <EmailRow key={`e-${item.id}`} email={item} />
                      : <CallRow key={`c-${item.id}`} call={item} onDelete={handleDeleteCall} />
                  )
                }
              </div>
            )}
          </section>

          {/* Officials */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Officials</h3>
            <div className="space-y-1 text-sm">
              <MayorField
                value={city.mayor}
                flagged={city.mayor_needs_verification}
                onSave={name => save({ mayor: name, mayor_needs_verification: false })}
              />
              <ContactField
                label="Last Name"
                value={city.mayor_last_name}
                editable
                onSave={v => save({ mayor_last_name: v || null })}
                wasSearched={false}
              />
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

function PanelDraftCard({ draft, onPatch, onRegenerate }) {
  const [expanded, setExpanded] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [body, setBody] = useState(draft.body || '')
  const [subject, setSubject] = useState(draft.subject || '')
  const [saving, setSaving] = useState(false)

  const borderColor = DRAFT_BORDER[draft.status] || 'border-l-gray-200'

  const save = async () => {
    setSaving(true)
    try {
      onPatch(draft.id, { body, subject, status: 'edited' })
      setEditMode(false)
      setExpanded(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`border-l-2 ${borderColor} bg-gray-50 rounded-r overflow-hidden`}>
      {/* Card header */}
      <div className="flex items-center gap-2 px-3 py-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${DRAFT_TYPE_COLOR[draft.draft_type] || 'bg-gray-100 text-gray-500'}`}>
          {DRAFT_TYPE_LABEL[draft.draft_type] || draft.draft_type}
        </span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${DRAFT_STATUS_COLOR[draft.status] || 'bg-gray-100 text-gray-500'}`}>
          {draft.status.replace('_', ' ')}
        </span>
        <span className="text-xs text-gray-400 ml-auto shrink-0">
          {draft.created_at ? new Date(draft.created_at).toLocaleDateString() : ''}
        </span>
      </div>

      {/* Subject */}
      <div className="px-3 pb-2">
        {editMode ? (
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400 mb-1"
          />
        ) : (
          <p className="text-xs text-gray-600 font-medium truncate">{draft.subject}</p>
        )}
        <p className="text-xs text-gray-400 truncate">To: {draft.to_address || '—'}</p>
      </div>

      {/* Body (collapsible) */}
      {editMode ? (
        <div className="px-3 pb-2">
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={8}
            className="w-full text-xs border border-gray-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400 font-mono"
          />
        </div>
      ) : (
        <div className="px-3 pb-2">
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-xs text-blue-500 hover:underline mb-1"
          >
            {expanded ? 'Hide body' : 'Show body'}
          </button>
          {expanded && (
            <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed bg-white border border-gray-100 rounded p-2 max-h-48 overflow-y-auto">
              {draft.body}
            </pre>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-1.5 flex-wrap px-3 pb-2.5">
        {draft.status !== 'approved' && draft.status !== 'edited' && draft.status !== 'rejected' && (
          <button
            onClick={() => onPatch(draft.id, { status: 'approved' })}
            className="bg-green-600 text-white text-xs px-2.5 py-1 rounded hover:bg-green-700"
          >
            Approve
          </button>
        )}
        {draft.status !== 'rejected' && (
          <button
            onClick={() => onPatch(draft.id, { status: 'rejected' })}
            className="text-red-500 border border-red-200 text-xs px-2.5 py-1 rounded hover:bg-red-50"
          >
            Reject
          </button>
        )}
        {draft.status === 'rejected' && (
          <button
            onClick={() => onPatch(draft.id, { status: 'pending_review' })}
            className="text-gray-500 border border-gray-200 text-xs px-2.5 py-1 rounded hover:bg-gray-100"
          >
            Restore
          </button>
        )}
        <button
          onClick={() => onRegenerate(draft.id)}
          className="text-purple-600 border border-purple-200 text-xs px-2.5 py-1 rounded hover:bg-purple-50"
        >
          Regenerate
        </button>
        {editMode ? (
          <>
            <button
              onClick={() => setEditMode(false)}
              className="text-gray-500 border border-gray-200 text-xs px-2.5 py-1 rounded hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="bg-gray-800 text-white text-xs px-2.5 py-1 rounded hover:bg-gray-700 disabled:opacity-40"
            >
              Save
            </button>
          </>
        ) : (
          <button
            onClick={() => { setEditMode(true); setExpanded(false); setBody(draft.body || ''); setSubject(draft.subject || '') }}
            className="text-gray-600 border border-gray-200 text-xs px-2.5 py-1 rounded hover:bg-gray-100"
          >
            Edit
          </button>
        )}
      </div>
    </div>
  )
}

function LogCallForm({ city, onSave, onCancel }) {
  const [notes, setNotes] = useState('')
  const [outcome, setOutcome] = useState('reached')
  const [contactType, setContactType] = useState('mayor_work')
  const [calledAt, setCalledAt] = useState(() => {
    const now = new Date()
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
    return now.toISOString().slice(0, 16)
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave({ notes: notes.trim() || null, outcome, contact_type: contactType, called_at: new Date(calledAt).toISOString() })
  }

  const mayorWorkPhone = city.mayor_work_phone
  const mayorPersonalPhone = city.mayor_personal_phone
  const cityPhone = city.city_phone

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-lg p-3 mb-3 space-y-2">
      <div className="flex gap-2 flex-wrap">
        <select
          value={contactType}
          onChange={e => setContactType(e.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white"
        >
          <option value="mayor_work">Mayor work{mayorWorkPhone ? ` · ${mayorWorkPhone}` : ''}</option>
          <option value="mayor_personal">Mayor personal{mayorPersonalPhone ? ` · ${mayorPersonalPhone}` : ''}</option>
          <option value="city">City line{cityPhone ? ` · ${cityPhone}` : ''}</option>
        </select>
        <select
          value={outcome}
          onChange={e => setOutcome(e.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white"
        >
          <option value="reached">Reached</option>
          <option value="voicemail">Voicemail</option>
          <option value="no_answer">No answer</option>
        </select>
        <input
          type="datetime-local"
          value={calledAt}
          onChange={e => setCalledAt(e.target.value)}
          className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white flex-1 min-w-0"
        />
      </div>
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="Notes from the call..."
        rows={3}
        className="w-full text-sm border border-gray-200 rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-300 resize-none"
      />
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel}
          className="text-xs text-gray-500 border border-gray-200 rounded px-3 py-1.5 hover:bg-gray-50">
          Cancel
        </button>
        <button type="submit"
          className="text-xs bg-gray-900 text-white rounded px-3 py-1.5 hover:bg-gray-700">
          Save call
        </button>
      </div>
    </form>
  )
}

const OUTCOME_LABEL = { reached: 'Reached', voicemail: 'Voicemail', no_answer: 'No answer' }
const OUTCOME_COLOR = {
  reached: 'bg-blue-50 text-blue-700',
  voicemail: 'bg-amber-50 text-amber-700',
  no_answer: 'bg-gray-100 text-gray-500',
}
const CONTACT_LABEL = { mayor_work: 'Mayor work', mayor_personal: 'Mayor personal', city: 'City line' }

function CallRow({ call, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const outcomeLabel = OUTCOME_LABEL[call.outcome] || call.outcome || 'Call'
  const outcomeColor = OUTCOME_COLOR[call.outcome] || 'bg-gray-100 text-gray-500'
  const contactLabel = call.contact_type ? CONTACT_LABEL[call.contact_type] : null

  return (
    <div className="rounded border border-gray-200 bg-white text-xs">
      <div className="px-3 py-2 flex items-start gap-2">
        <button
          onClick={() => call.notes && setExpanded(e => !e)}
          className={`flex-1 min-w-0 text-left flex items-start gap-2 ${call.notes ? 'cursor-pointer' : 'cursor-default'}`}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-gray-500 font-medium">Call</span>
              <span className={`px-1.5 py-0.5 rounded ${outcomeColor}`}>{outcomeLabel}</span>
              {contactLabel && <span className="text-gray-400">{contactLabel}</span>}
              {call.notes && !expanded && (
                <span className="text-gray-400 truncate max-w-[160px]">{call.notes}</span>
              )}
            </div>
          </div>
          <span className="text-gray-400 shrink-0 ml-2">
            {call.called_at ? new Date(call.called_at).toLocaleDateString() : ''}
          </span>
        </button>
        <button
          onClick={() => onDelete(call.id)}
          className="text-gray-300 hover:text-red-400 shrink-0 ml-1 leading-none"
          title="Remove"
        >
          &times;
        </button>
      </div>
      {expanded && call.notes && (
        <div className="px-3 pb-3 border-t border-gray-100 pt-2 text-gray-700 whitespace-pre-wrap">
          {call.notes}
        </div>
      )}
    </div>
  )
}

function EmailRow({ email }) {
  const [expanded, setExpanded] = useState(false)
  const isInbound = email.direction === 'inbound'

  return (
    <div className={`rounded border text-xs ${isInbound ? 'border-green-200 bg-green-50' : 'border-blue-100 bg-blue-50'}`}>
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full text-left px-3 py-2 flex items-start gap-2"
      >
        <span className={`shrink-0 mt-0.5 font-bold ${isInbound ? 'text-green-600' : 'text-blue-500'}`}>
          {isInbound ? '←' : '→'}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-800 truncate">{email.subject || '(no subject)'}</p>
          <p className="text-gray-500 truncate">
            {isInbound ? email.from_address : `To: ${email.to_address}`}
          </p>
        </div>
        <span className="text-gray-400 shrink-0 ml-2">
          {email.sent_at ? new Date(email.sent_at).toLocaleDateString() : ''}
        </span>
      </button>
      {expanded && email.body_preview && (
        <div className="px-3 pb-3 border-t border-gray-200 mt-1 pt-2 text-gray-700 whitespace-pre-wrap">
          {email.body_preview}
        </div>
      )}
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
    </svg>
  )
}

function MayorField({ value, flagged, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(value || '')

  const commit = () => {
    const trimmed = val.trim()
    if (trimmed && trimmed !== value) onSave(trimmed)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="flex justify-between items-center">
        <span className="text-gray-500">Mayor</span>
        <input
          autoFocus
          type="text"
          value={val}
          onChange={e => setVal(e.target.value)}
          onBlur={commit}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
          className="text-sm border border-blue-300 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400 w-48"
        />
      </div>
    )
  }

  return (
    <div className="flex justify-between items-center group">
      <span className="text-gray-500">Mayor</span>
      <div className="flex items-center gap-1.5">
        <span className="text-gray-900 font-medium">{value || '—'}</span>
        <button
          onClick={() => { setVal(value || ''); setEditing(true) }}
          className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-blue-500 transition-opacity"
          title="Edit mayor"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 012.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z" />
          </svg>
        </button>
      </div>
    </div>
  )
}

function ContactField({ label, value, link, editable, onSave, sourceUrl, wasSearched }) {
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
      <span className="text-gray-400 w-20 shrink-0">{label}</span>
      {value ? (
        <span className="flex items-center gap-1 min-w-0">
          {link ? (
            <a href={value.startsWith('http') ? value : `https://${value}`}
              target="_blank" rel="noreferrer"
              className="text-blue-600 hover:underline truncate">{value}</a>
          ) : (
            <span
              className={`text-gray-700 truncate ${editable ? 'cursor-pointer hover:text-blue-600' : ''}`}
              onClick={() => editable && setEditing(true)}
            >{value}</span>
          )}
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noreferrer"
              title={`Source: ${sourceUrl}`}
              className="text-gray-300 hover:text-blue-400 shrink-0"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          )}
        </span>
      ) : editable ? (
        wasSearched
          ? <span className="text-gray-300 italic">Not found</span>
          : <button onClick={() => setEditing(true)} className="text-blue-500 hover:underline italic">Add...</button>
      ) : null}
    </div>
  )
}
