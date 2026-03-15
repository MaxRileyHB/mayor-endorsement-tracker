import { useState, useEffect, useCallback } from 'react'
import { getDrafts, updateDraft, getBatchStatus, regenerateDraft, sendDrafts } from '../api'
import { TIER_COLORS } from '../constants'
import { SkeletonDraftCard } from './Skeleton'

const STATUS_FILTERS = ['all', 'pending_review', 'approved', 'edited', 'rejected']
const STATUS_LABELS = {
  all: 'All',
  pending_review: 'Pending',
  approved: 'Approved',
  edited: 'Edited',
  rejected: 'Rejected',
}
const STATUS_COLORS = {
  pending_review: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  edited: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-500',
  sent: 'bg-gray-100 text-gray-500',
}

export default function ReviewQueue({ batchId, expectedCount, onBack }) {
  const [drafts, setDrafts] = useState([])
  const [filter, setFilter] = useState('all')
  const [cardSearch, setCardSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [batchStatus, setBatchStatus] = useState(null)
  const [sending, setSending] = useState(false)
  const [selected, setSelected] = useState(new Set())

  // Always load all drafts; filter client-side so optimistic updates work instantly
  const load = useCallback(async () => {
    try {
      const params = {}
      if (batchId) params.batch_id = batchId
      const data = await getDrafts(params)
      setDrafts(data)
      return data
    } finally {
      setLoading(false)
    }
  }, [batchId])

  useEffect(() => {
    load()
    if (!batchId) return
    const poll = setInterval(() => {
      getBatchStatus(batchId).then(s => {
        setBatchStatus(s)
        load().then(() => {
          if (expectedCount > 0 && s.total >= expectedCount) clearInterval(poll)
        })
      }).catch(() => {})
    }, 3000)
    return () => clearInterval(poll)
  }, [batchId, expectedCount, load])

  // Optimistic patch: update UI immediately, sync to server in background
  const patch = (id, fields) => {
    setDrafts(prev => prev.map(d => d.id === id ? { ...d, ...fields } : d))
    setSelected(prev => { const next = new Set(prev); next.delete(id); return next })
    updateDraft(id, fields).then(updated => {
      setDrafts(prev => prev.map(d => d.id === id ? { ...d, ...updated } : d))
    })
  }

  const handleRegenerate = async (id) => {
    const { batch_id } = await regenerateDraft(id)
    setDrafts(prev => prev.map(d => d.id === id ? { ...d, status: 'rejected' } : d))
    setBatchStatus(s => s ? { ...s, total: (s.total || 0) + 1 } : { total: 1 })
    const poll = setInterval(() => {
      getBatchStatus(batch_id).then(s => {
        if (s.total > 0 && !s.by_status?.pending_review) clearInterval(poll)
        load()
      }).catch(() => {})
    }, 3000)
  }

  const approveAll = () => {
    const pending = drafts.filter(d => d.status === 'pending_review')
    setDrafts(prev => prev.map(d => d.status === 'pending_review' ? { ...d, status: 'approved' } : d))
    Promise.all(pending.map(d => updateDraft(d.id, { status: 'approved' })))
  }

  const batchApprove = () => {
    const ids = [...selected]
    setDrafts(prev => prev.map(d => ids.includes(d.id) ? { ...d, status: 'approved' } : d))
    setSelected(new Set())
    Promise.all(ids.map(id => updateDraft(id, { status: 'approved' })))
  }

  const batchReject = () => {
    const ids = [...selected]
    setDrafts(prev => prev.map(d => ids.includes(d.id) ? { ...d, status: 'rejected' } : d))
    setSelected(new Set())
    Promise.all(ids.map(id => updateDraft(id, { status: 'rejected' })))
  }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const counts = drafts.reduce((acc, d) => {
    acc[d.status] = (acc[d.status] || 0) + 1
    return acc
  }, {})
  const approvedCount = counts.approved || 0
  const pendingCount = counts.pending_review || 0

  const filtered = drafts
    .filter(d => filter === 'all' || d.status === filter)
    .filter(d => !cardSearch || d.city_name?.toLowerCase().includes(cardSearch.toLowerCase()))

  const allVisibleSelected = filtered.length > 0 && filtered.every(d => selected.has(d.id))

  const toggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelected(prev => {
        const next = new Set(prev)
        filtered.forEach(d => next.delete(d.id))
        return next
      })
    } else {
      setSelected(prev => {
        const next = new Set(prev)
        filtered.forEach(d => next.add(d.id))
        return next
      })
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-gray-400 hover:text-gray-700 text-sm flex items-center gap-1"
          >
            ← Back
          </button>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-gray-900">Review Drafts</h2>
            <p className="text-xs text-gray-400 flex items-center gap-2">
              {drafts.length} drafts · {approvedCount} approved · {pendingCount} pending
              {batchStatus && batchStatus.total > drafts.length && (
                <span className="flex items-center gap-1 text-amber-600 font-medium">
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                  </svg>
                  Generating {drafts.length}/{batchStatus.total}...
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            {pendingCount > 0 && (
              <button
                onClick={approveAll}
                className="bg-green-600 text-white text-sm px-3 py-1.5 rounded hover:bg-green-700"
              >
                Approve all pending ({pendingCount})
              </button>
            )}
          </div>
        </div>

        {/* Filter tabs + search */}
        <div className="flex items-center gap-2 mt-3">
          <div className="flex gap-1 flex-1">
            {STATUS_FILTERS.map(s => (
              <button
                key={s}
                onClick={() => { setFilter(s); setSelected(new Set()) }}
                className={`text-xs px-3 py-1 rounded-full transition-colors
                  ${filter === s
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-500 hover:bg-gray-100'}`}
              >
                {STATUS_LABELS[s]}
                {s !== 'all' && counts[s] ? ` (${counts[s]})` : ''}
              </button>
            ))}
          </div>
          <input
            type="text"
            value={cardSearch}
            onChange={e => setCardSearch(e.target.value)}
            placeholder="Filter by city..."
            className="text-xs border border-gray-200 rounded-lg px-2.5 py-1 w-36 focus:outline-none focus:ring-1 focus:ring-blue-300"
          />
        </div>

        {/* Batch action bar */}
        {selected.size > 0 && (
          <div className="flex items-center gap-3 mt-2 px-1">
            <span className="text-xs text-gray-500 font-medium">{selected.size} selected</span>
            <button
              onClick={batchApprove}
              className="bg-green-600 text-white text-xs px-3 py-1 rounded hover:bg-green-700"
            >
              Approve selected
            </button>
            <button
              onClick={batchReject}
              className="text-red-500 border border-red-200 text-xs px-3 py-1 rounded hover:bg-red-50"
            >
              Reject selected
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-gray-400 text-xs hover:text-gray-600"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Draft list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {loading ? (
          <div className="space-y-4">
            {[0, 1, 2].map(i => <SkeletonDraftCard key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center text-gray-400 py-12">No drafts in this category.</div>
        ) : (
          <>
            {/* Select all row */}
            <div className="flex items-center gap-2 px-1">
              <input
                type="checkbox"
                checked={allVisibleSelected}
                onChange={toggleSelectAll}
                className="rounded border-gray-300 text-blue-600 cursor-pointer"
              />
              <span className="text-xs text-gray-400">
                {allVisibleSelected ? 'Deselect' : 'Select'} all {filtered.length} visible
              </span>
            </div>
            {filtered.map(draft => (
              <DraftCard
                key={draft.id}
                draft={draft}
                selected={selected.has(draft.id)}
                onToggleSelect={() => toggleSelect(draft.id)}
                onPatch={patch}
                onRegenerate={handleRegenerate}
              />
            ))}
          </>
        )}
      </div>

      {/* Send bar */}
      {approvedCount > 0 && (
        <div className="bg-gray-900 text-white px-4 py-3 flex items-center gap-3 shrink-0">
          <span className="text-sm">Ready to send: {approvedCount} approved</span>
          <button
            disabled={sending}
            className="ml-auto bg-green-500 hover:bg-green-400 disabled:opacity-50 text-sm font-medium px-4 py-1.5 rounded"
            onClick={async () => {
              setSending(true)
              try {
                const ids = drafts.filter(d => d.status === 'approved' || d.status === 'edited').map(d => d.id)
                const result = await sendDrafts(ids)
                await load()
                if (result.failed?.length) {
                  alert(`Sent ${result.sent}. ${result.failed.length} failed — check that Gmail is connected.`)
                }
              } catch (e) {
                alert('Send failed — make sure Gmail is connected.')
              } finally {
                setSending(false)
              }
            }}
          >
            Send {approvedCount} approved
          </button>
        </div>
      )}
    </div>
  )
}

function DraftCard({ draft, selected, onToggleSelect, onPatch, onRegenerate }) {
  const [editMode, setEditMode] = useState(false)
  const [body, setBody] = useState(draft.body || '')
  const [subject, setSubject] = useState(draft.subject || '')
  const [saving, setSaving] = useState(false)
  const tier = draft.research_context?.tier || 3

  const save = async () => {
    setSaving(true)
    try {
      await onPatch(draft.id, { body, subject, status: 'edited' })
      setEditMode(false)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`bg-white border rounded-lg overflow-hidden
      ${draft.status === 'approved' || draft.status === 'edited' ? 'border-green-200' : ''}
      ${draft.status === 'rejected' ? 'border-red-200 opacity-60' : ''}
      ${draft.status === 'pending_review' ? 'border-gray-200' : ''}
      ${selected ? 'ring-2 ring-blue-300' : ''}`}
    >
      {/* Card header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={e => e.stopPropagation()}
          className="rounded border-gray-300 text-blue-600 cursor-pointer shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-gray-900">{draft.city_name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${TIER_COLORS[tier]}`}>
              T{tier}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLORS[draft.status] || 'bg-gray-100 text-gray-500'}`}>
              {draft.status.replace('_', ' ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5 truncate">
            To: {draft.to_address || '—'}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {draft.status !== 'approved' && draft.status !== 'edited' && draft.status !== 'rejected' && (
            <button
              onClick={() => onPatch(draft.id, { status: 'approved' })}
              className="bg-green-600 text-white text-xs px-3 py-1.5 rounded hover:bg-green-700"
            >
              Approve
            </button>
          )}
          {draft.status !== 'rejected' && (
            <button
              onClick={() => onPatch(draft.id, { status: 'rejected' })}
              className="text-red-500 border border-red-200 text-xs px-3 py-1.5 rounded hover:bg-red-50"
            >
              Reject
            </button>
          )}
          {draft.status === 'rejected' && (
            <button
              onClick={() => onPatch(draft.id, { status: 'pending_review' })}
              className="text-gray-500 border border-gray-200 text-xs px-3 py-1.5 rounded hover:bg-gray-50"
            >
              Restore
            </button>
          )}
          <button
            onClick={() => onRegenerate(draft.id)}
            className="text-purple-600 border border-purple-200 text-xs px-3 py-1.5 rounded hover:bg-purple-50 whitespace-nowrap"
          >
            Regenerate
          </button>
          <button
            onClick={() => { setEditMode(!editMode); setBody(draft.body || ''); setSubject(draft.subject || '') }}
            className="text-gray-600 border border-gray-200 text-xs px-3 py-1.5 rounded hover:bg-gray-50"
          >
            {editMode ? 'Cancel' : 'Edit'}
          </button>
        </div>
      </div>

      {/* Subject */}
      <div className="px-4 py-2 border-b border-gray-100 bg-gray-50">
        {editMode ? (
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        ) : (
          <p className="text-xs text-gray-600"><span className="text-gray-400">Subject:</span> {draft.subject}</p>
        )}
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {editMode ? (
          <div>
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              rows={10}
              className="w-full text-sm border border-gray-200 rounded px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-400 font-mono"
            />
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setEditMode(false)}
                className="text-gray-500 text-sm px-3 py-1.5 border border-gray-200 rounded hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={saving}
                className="bg-gray-900 text-white text-sm px-3 py-1.5 rounded hover:bg-gray-700 disabled:opacity-40"
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">
            {draft.body}
          </pre>
        )}
      </div>
    </div>
  )
}
