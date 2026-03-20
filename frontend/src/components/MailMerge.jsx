import { useState, useEffect, useRef, useCallback } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Link from '@tiptap/extension-link'
import Underline from '@tiptap/extension-underline'
import { STATUSES, STATUS_MAP } from '../constants'
import {
  mmListTemplates, mmCreateTemplate, mmUpdateTemplate, mmDeleteTemplate,
  mmCount, mmPreview, mmTest, mmSend,
  mmJobStatus, mmJobPause, mmJobResume, mmJobCancel,
  getFilterOptions,
} from '../api'

const AVAILABLE_TAGS = [
  { key: 'mayor_first_name', label: 'Mayor first name',  example: 'John' },
  { key: 'mayor_last_name',  label: 'Mayor last name',   example: 'Smith' },
  { key: 'mayor_full_name',  label: 'Mayor full name',   example: 'John Smith' },
  { key: 'city_name',        label: 'City name',         example: 'Rancho Palos Verdes' },
  { key: 'county',           label: 'County',            example: 'Los Angeles' },
  { key: 'population',       label: 'Population',        example: '41,643' },
  { key: 'mayor_title',      label: 'Mayor title',       example: 'Mayor' },
  { key: 'city_website',     label: 'City website',      example: 'https://rpvca.gov' },
]

const EMAIL_PRIORITY_LABELS = {
  mayor_work:     'Mayor work email',
  mayor_personal: 'Mayor personal email',
  city:           'City general email',
}

const STAGGER_OPTIONS = [
  { value: 'fast',   label: 'Fast (1 per 10s, ~360/hr)',   sub: 'Higher spam risk' },
  { value: 'normal', label: 'Normal (1 per 30s, ~120/hr)', sub: 'Recommended' },
  { value: 'slow',   label: 'Slow (1 per 60s, ~60/hr)',    sub: 'Safest for large batches' },
]

const DEFAULT_FILTERS = {
  city_ids: [],
  statuses: [],
  tiers: [],
  counties: [],
  wildfire_risk: [],
  contact_filter: '',
  last_contacted_filter: '',
  last_contacted_days: 14,
  exclude_endorsed: true,
  exclude_declined: true,
  exclude_not_pursuing: true,
}

// ── Utility components ────────────────────────────────────────────────────────

function StepDot({ n, current }) {
  const done = n < current
  const active = n === current
  return (
    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors ${
      done   ? 'bg-blue-600 border-blue-600 text-white' :
      active ? 'bg-white border-blue-600 text-blue-600' :
               'bg-white border-gray-200 text-gray-400'
    }`}>
      {done ? '✓' : n}
    </div>
  )
}

function StepHeader({ step }) {
  const steps = ['Template', 'Recipients', 'Preview', 'Send']
  return (
    <div className="flex items-center gap-0 mb-6 shrink-0">
      {steps.map((label, i) => (
        <div key={i} className="flex items-center">
          <div className="flex items-center gap-1.5">
            <StepDot n={i + 1} current={step} />
            <span className={`text-xs font-medium ${i + 1 === step ? 'text-gray-900' : 'text-gray-400'}`}>
              {label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-8 h-px mx-2 ${i + 1 < step ? 'bg-blue-600' : 'bg-gray-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

function TagPill({ tag }) {
  return (
    <code className="bg-blue-50 text-blue-700 border border-blue-200 text-xs px-1.5 py-0.5 rounded font-mono">
      {'{' + tag + '}'}
    </code>
  )
}

// ── TipTap toolbar button ─────────────────────────────────────────────────────

function ToolbarBtn({ onClick, active, title, children }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => { e.preventDefault(); onClick() }}
      title={title}
      className={`px-2 py-1 rounded text-sm font-medium transition-colors ${
        active ? 'bg-gray-200 text-gray-900' : 'text-gray-600 hover:bg-gray-100'
      }`}
    >
      {children}
    </button>
  )
}

// ── TipTap editor wrapper ─────────────────────────────────────────────────────

function RichEditor({ content, onChange, placeholder = 'Write your email body here…' }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading:          false,
        blockquote:       false,
        code:             false,
        codeBlock:        false,
        horizontalRule:   false,
        bulletList:       false,
        orderedList:      false,
        listItem:         false,
      }),
      Underline,
      Link.configure({ openOnClick: false, HTMLAttributes: { rel: 'noopener noreferrer' } }),
    ],
    content,
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
    editorProps: {
      attributes: { class: 'focus:outline-none' },
    },
  })

  // Sync content when a saved template is loaded
  useEffect(() => {
    if (editor && content !== editor.getHTML()) {
      editor.commands.setContent(content || '')
    }
  }, [content]) // eslint-disable-line react-hooks/exhaustive-deps

  const insertTag = (tag) => {
    editor?.chain().focus().insertContent(`{${tag}}`).run()
  }

  const addLink = () => {
    const url = window.prompt('URL:')
    if (!url) return
    editor?.chain().focus().setLink({ href: url }).run()
  }

  if (!editor) return null

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-gray-100 bg-gray-50 flex-wrap">
        <ToolbarBtn onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold">
          <strong>B</strong>
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic">
          <em>I</em>
        </ToolbarBtn>
        <ToolbarBtn onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive('underline')} title="Underline">
          <span className="underline">U</span>
        </ToolbarBtn>
        <ToolbarBtn onClick={addLink} active={editor.isActive('link')} title="Insert link">
          🔗
        </ToolbarBtn>
        {editor.isActive('link') && (
          <ToolbarBtn onClick={() => editor.chain().focus().unsetLink().run()} title="Remove link">
            ✕ link
          </ToolbarBtn>
        )}

        <div className="w-px h-4 bg-gray-200 mx-1" />

        <div className="relative group">
          <button
            type="button"
            className="text-xs px-2 py-1 rounded text-blue-600 hover:bg-blue-50 font-medium flex items-center gap-1"
          >
            {'{ }'} Insert field ▾
          </button>
          <div className="absolute left-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 min-w-[220px] py-1 hidden group-hover:block">
            {AVAILABLE_TAGS.map(t => (
              <button
                key={t.key}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); insertTag(t.key) }}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 flex items-center justify-between gap-4"
              >
                <span className="font-mono text-xs text-blue-700">{'{' + t.key + '}'}</span>
                <span className="text-gray-400 text-xs">{t.example}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Editor area */}
      <div className="tiptap-body px-3 py-2.5 text-sm text-gray-800">
        {!editor.getText() && !content && (
          <p className="text-gray-400 pointer-events-none absolute">{placeholder}</p>
        )}
        <EditorContent editor={editor} />
      </div>
    </div>
  )
}

// ── Step 1: Template ──────────────────────────────────────────────────────────

function Step1Template({ state, setState, onNext }) {
  const [templates, setTemplates] = useState([])
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showTagRef, setShowTagRef] = useState(false)

  useEffect(() => {
    mmListTemplates().then(setTemplates).catch(() => {})
  }, [])

  const handleLoad = (t) => {
    setState(s => ({
      ...s,
      selectedTemplateId: t.id,
      templateName: t.name,
      subject: t.subject_template,
      bodyHtml: t.body_template,
    }))
  }

  const handleSave = async () => {
    if (!state.templateName.trim()) {
      alert('Give this template a name before saving.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        name: state.templateName.trim(),
        subject_template: state.subject,
        body_template: state.bodyHtml,
      }
      let saved
      if (state.selectedTemplateId) {
        saved = await mmUpdateTemplate(state.selectedTemplateId, payload)
      } else {
        saved = await mmCreateTemplate(payload)
        setState(s => ({ ...s, selectedTemplateId: saved.id }))
      }
      const updated = await mmListTemplates()
      setTemplates(updated)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!state.selectedTemplateId) return
    if (!window.confirm('Delete this template?')) return
    setDeleting(true)
    try {
      await mmDeleteTemplate(state.selectedTemplateId)
      setState(s => ({ ...s, selectedTemplateId: null, templateName: '', subject: '', bodyHtml: '' }))
      setTemplates(await mmListTemplates())
    } finally {
      setDeleting(false)
    }
  }

  const canNext = state.selectedTemplateId && state.subject.trim() && state.bodyHtml && state.bodyHtml !== '<p></p>'

  // Subject tag insertion helper
  const subjectRef = useRef(null)
  const insertSubjectTag = (tag) => {
    const input = subjectRef.current
    if (!input) return
    const start = input.selectionStart
    const end = input.selectionEnd
    const newVal = state.subject.slice(0, start) + `{${tag}}` + state.subject.slice(end)
    setState(s => ({ ...s, subject: newVal }))
    setTimeout(() => {
      input.focus()
      const pos = start + tag.length + 2
      input.setSelectionRange(pos, pos)
    }, 0)
  }

  return (
    <div className="space-y-5">
      {/* Saved templates row */}
      {templates.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 shrink-0">Saved templates:</span>
          {templates.map(t => (
            <button
              key={t.id}
              onClick={() => handleLoad(t)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                state.selectedTemplateId === t.id
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'border-gray-200 text-gray-700 hover:border-blue-300 bg-white'
              }`}
            >
              {t.name}
            </button>
          ))}
        </div>
      )}

      {/* Template name */}
      <div className="flex gap-2 items-center">
        <input
          type="text"
          value={state.templateName}
          onChange={e => setState(s => ({ ...s, templateName: e.target.value, selectedTemplateId: state.selectedTemplateId }))}
          placeholder="Template name (e.g. Initial outreach v2)…"
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
        <button
          onClick={handleSave}
          disabled={saving}
          className="text-sm px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 whitespace-nowrap"
        >
          {saving ? 'Saving…' : state.selectedTemplateId ? 'Update template' : 'Save template'}
        </button>
        {state.selectedTemplateId && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-sm px-3 py-1.5 text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-50"
          >
            Delete
          </button>
        )}
      </div>

      {/* Subject */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-gray-600">Subject line</label>
          <div className="relative group">
            <button type="button" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
              {'{ }'} Insert field ▾
            </button>
            <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 min-w-[220px] py-1 hidden group-hover:block">
              {AVAILABLE_TAGS.map(t => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => insertSubjectTag(t.key)}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 flex items-center justify-between gap-4"
                >
                  <span className="font-mono text-xs text-blue-700">{'{' + t.key + '}'}</span>
                  <span className="text-gray-400 text-xs">{t.example}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <input
          ref={subjectRef}
          type="text"
          value={state.subject}
          onChange={e => setState(s => ({ ...s, subject: e.target.value }))}
          placeholder={`Insurance in {city_name} — Sen. Ben Allen`}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
        />
      </div>

      {/* Body */}
      <div>
        <label className="text-xs font-medium text-gray-600 block mb-1.5">Email body</label>
        <RichEditor
          content={state.bodyHtml}
          onChange={html => setState(s => ({ ...s, bodyHtml: html }))}
        />
      </div>

      {/* Tag reference */}
      <div>
        <button
          onClick={() => setShowTagRef(v => !v)}
          className="text-xs text-gray-400 hover:text-gray-600"
        >
          {showTagRef ? '▾' : '▸'} Field tag reference
        </button>
        {showTagRef && (
          <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
            {AVAILABLE_TAGS.map(t => (
              <div key={t.key} className="flex items-center gap-2">
                <TagPill tag={t.key} />
                <span className="text-gray-500">{t.label} — <em>{t.example}</em></span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-3 pt-2">
        {state.subject.trim() && state.bodyHtml && state.bodyHtml !== '<p></p>' && !state.selectedTemplateId && (
          <span className="text-xs text-amber-600">Save the template first to continue</span>
        )}
        <button
          onClick={onNext}
          disabled={!canNext}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-40"
        >
          Next: Recipients →
        </button>
      </div>
    </div>
  )
}

// ── Step 2: Recipients ────────────────────────────────────────────────────────

function PriorityList({ priority, onChange }) {
  const [dragging, setDragging] = useState(null)

  const handleDragStart = (e, key) => {
    setDragging(key)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e, key) => {
    e.preventDefault()
    if (key === dragging) return
    const next = [...priority]
    const from = next.indexOf(dragging)
    const to = next.indexOf(key)
    next.splice(from, 1)
    next.splice(to, 0, dragging)
    onChange(next)
  }

  return (
    <div className="space-y-1.5">
      {priority.map((key, idx) => (
        <div
          key={key}
          draggable
          onDragStart={e => handleDragStart(e, key)}
          onDragOver={e => handleDragOver(e, key)}
          onDragEnd={() => setDragging(null)}
          className={`flex items-center gap-2 bg-white border rounded-lg px-3 py-2 cursor-grab active:cursor-grabbing select-none transition-colors ${
            dragging === key ? 'border-blue-400 bg-blue-50' : 'border-gray-200'
          }`}
        >
          <span className="text-gray-300 text-base">⠿</span>
          <span className="text-xs text-gray-400 w-3">{idx + 1}.</span>
          <span className="text-sm text-gray-800">{EMAIL_PRIORITY_LABELS[key]}</span>
        </div>
      ))}
    </div>
  )
}

function Step2Recipients({ state, setState, onBack, onNext }) {
  const [filterOptions, setFilterOptions] = useState({ counties: [] })
  const [countData, setCountData] = useState(null)
  const [showCityList, setShowCityList] = useState(false)
  const [counting, setCounting] = useState(false)
  const countTimer = useRef(null)

  useEffect(() => {
    getFilterOptions().then(setFilterOptions).catch(() => {})
  }, [])

  const refreshCount = useCallback((filters, priority) => {
    clearTimeout(countTimer.current)
    countTimer.current = setTimeout(async () => {
      setCounting(true)
      try {
        const data = await mmCount(filters, priority)
        setCountData(data)
      } finally {
        setCounting(false)
      }
    }, 400)
  }, [])

  useEffect(() => {
    refreshCount(state.filters, state.emailPriority)
  }, [state.filters, state.emailPriority, refreshCount])

  const setFilter = (key, value) =>
    setState(s => ({ ...s, filters: { ...s.filters, [key]: value } }))

  const toggleStatus = (key) => {
    setFilter('status', undefined) // unused
    setFilter('statuses',
      state.filters.statuses.includes(key)
        ? state.filters.statuses.filter(s => s !== key)
        : [...state.filters.statuses, key]
    )
  }

  const applyPreset = (preset) => {
    if (preset === 'not_contacted') {
      setFilter('statuses', ['no_contact_info', 'city_contact_only', 'ready_for_outreach'])
    } else if (preset === 'needs_followup') {
      setFilter('statuses', ['follow_up', 'outreach_sent'])
    } else if (preset === 'all_active') {
      setFilter('statuses', STATUSES.filter(s =>
        !['endorsed', 'declined', 'not_pursuing'].includes(s.key)
      ).map(s => s.key))
    }
  }

  const hasInitialCities = state.filters.city_ids.length > 0

  return (
    <div className="space-y-5">
      {hasInitialCities ? (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800 flex items-center justify-between">
          <span>Using <strong>{state.filters.city_ids.length} selected cities</strong> from the pipeline view</span>
          <button
            onClick={() => setFilter('city_ids', [])}
            className="text-xs text-blue-600 hover:underline"
          >
            Clear — use filters instead
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Presets */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">Quick presets</label>
            <div className="flex gap-2 flex-wrap">
              {[
                { key: 'not_contacted', label: 'Not yet contacted' },
                { key: 'needs_followup', label: 'Needs follow-up' },
                { key: 'all_active',    label: 'All active' },
              ].map(p => (
                <button key={p.key} onClick={() => applyPreset(p.key)}
                  className="text-xs px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded-full text-gray-700">
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Status */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">Pipeline status</label>
            <div className="flex flex-wrap gap-1.5">
              {STATUSES.map(s => (
                <button
                  key={s.key}
                  onClick={() => toggleStatus(s.key)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    state.filters.statuses.includes(s.key)
                      ? 'bg-gray-800 text-white border-gray-800'
                      : 'border-gray-200 text-gray-600 hover:border-gray-400 bg-white'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {/* Row: Tier + Wildfire risk */}
          <div className="flex gap-6">
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Tier</label>
              <div className="flex gap-2">
                {[1, 2, 3].map(t => (
                  <button key={t} onClick={() => setFilter('tiers',
                    state.filters.tiers.includes(t)
                      ? state.filters.tiers.filter(x => x !== t)
                      : [...state.filters.tiers, t]
                  )}
                    className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                      state.filters.tiers.includes(t)
                        ? 'bg-gray-800 text-white border-gray-800'
                        : 'border-gray-200 text-gray-600 hover:border-gray-400 bg-white'
                    }`}>
                    T{t}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1.5">Wildfire risk</label>
              <div className="flex gap-2">
                {['high', 'medium', 'low'].map(r => (
                  <button key={r} onClick={() => setFilter('wildfire_risk',
                    state.filters.wildfire_risk.includes(r)
                      ? state.filters.wildfire_risk.filter(x => x !== r)
                      : [...state.filters.wildfire_risk, r]
                  )}
                    className={`text-xs px-2.5 py-1 rounded-full border transition-colors capitalize ${
                      state.filters.wildfire_risk.includes(r)
                        ? 'bg-orange-500 text-white border-orange-500'
                        : 'border-gray-200 text-gray-600 hover:border-orange-300 bg-white'
                    }`}>
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* County */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">County</label>
            <select
              multiple
              value={state.filters.counties}
              onChange={e => setFilter('counties', [...e.target.selectedOptions].map(o => o.value))}
              className="w-full max-w-xs text-sm border border-gray-200 rounded-lg px-2 py-1.5 h-24 focus:outline-none focus:ring-2 focus:ring-blue-300"
            >
              {filterOptions.counties.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            {state.filters.counties.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {state.filters.counties.map(c => (
                  <span key={c} className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                    {c}
                    <button onClick={() => setFilter('counties', state.filters.counties.filter(x => x !== c))}>×</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Contact availability */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">Contact availability</label>
            <div className="flex gap-2 flex-wrap">
              {[
                { value: 'has_mayor_email', label: 'Has mayor email' },
                { value: 'has_any_email',   label: 'Has any email' },
                { value: 'no_email',        label: 'No email at all' },
              ].map(opt => (
                <button key={opt.value}
                  onClick={() => setFilter('contact_filter', state.filters.contact_filter === opt.value ? '' : opt.value)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    state.filters.contact_filter === opt.value
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'border-gray-200 text-gray-600 hover:border-gray-400 bg-white'
                  }`}>
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Last contacted */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">Last contacted</label>
            <div className="flex gap-2 flex-wrap items-center">
              {[
                { value: 'never',         label: 'Never contacted' },
                { value: 'not_in_X_days', label: 'Not in last' },
                { value: 'in_X_days',     label: 'In last' },
              ].map(opt => (
                <button key={opt.value}
                  onClick={() => setFilter('last_contacted_filter',
                    state.filters.last_contacted_filter === opt.value ? '' : opt.value
                  )}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    state.filters.last_contacted_filter === opt.value
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'border-gray-200 text-gray-600 hover:border-gray-400 bg-white'
                  }`}>
                  {opt.label}
                </button>
              ))}
              {['not_in_X_days', 'in_X_days'].includes(state.filters.last_contacted_filter) && (
                <input
                  type="number"
                  value={state.filters.last_contacted_days}
                  onChange={e => setFilter('last_contacted_days', parseInt(e.target.value) || 14)}
                  min={1}
                  className="w-16 text-sm border border-gray-200 rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
              )}
              {['not_in_X_days', 'in_X_days'].includes(state.filters.last_contacted_filter) && (
                <span className="text-xs text-gray-500">days</span>
              )}
            </div>
          </div>

          {/* Exclude */}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1.5">Exclude</label>
            <div className="flex gap-3">
              {[
                { key: 'exclude_endorsed',     label: 'Endorsed' },
                { key: 'exclude_declined',     label: 'Declined' },
                { key: 'exclude_not_pursuing', label: 'Not pursuing' },
              ].map(opt => (
                <label key={opt.key} className="flex items-center gap-1.5 text-xs text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={state.filters[opt.key]}
                    onChange={e => setFilter(opt.key, e.target.checked)}
                    className="rounded"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Email priority */}
      <div className="pt-2 border-t border-gray-100">
        <label className="text-xs font-medium text-gray-500 block mb-2">
          Email address priority — drag to reorder
        </label>
        <div className="max-w-xs">
          <PriorityList
            priority={state.emailPriority}
            onChange={p => setState(s => ({ ...s, emailPriority: p }))}
          />
        </div>
      </div>

      {/* Live count */}
      <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
        {counting ? (
          <p className="text-sm text-gray-400">Calculating…</p>
        ) : countData ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-800">
              Will send to <strong>{countData.will_send}</strong> cities
              {countData.skipped > 0 && (
                <span className="text-gray-400 font-normal"> ({countData.skipped} will be skipped)</span>
              )}
            </p>
            <div className="text-xs text-gray-500 space-y-0.5">
              {countData.breakdown.mayor_work > 0 && (
                <div>→ Mayor work email: <strong>{countData.breakdown.mayor_work}</strong> cities</div>
              )}
              {countData.breakdown.mayor_personal > 0 && (
                <div>→ Mayor personal email: <strong>{countData.breakdown.mayor_personal}</strong> cities (no work email)</div>
              )}
              {countData.breakdown.city > 0 && (
                <div>→ City general email: <strong>{countData.breakdown.city}</strong> cities (no mayor email)</div>
              )}
              {countData.breakdown.no_email > 0 && (
                <div className="text-amber-600">→ No email available: <strong>{countData.breakdown.no_email}</strong> cities (will be skipped)</div>
              )}
              {countData.no_mayor_name > 0 && (
                <div className="text-amber-600">→ No mayor name: <strong>{countData.no_mayor_name}</strong> cities (will be skipped)</div>
              )}
            </div>

            {/* View list toggle */}
            {countData.city_names?.length > 0 && (
              <button
                onClick={() => setShowCityList(v => !v)}
                className="text-xs text-blue-600 hover:underline mt-1"
              >
                {showCityList ? 'Hide city list ▴' : `View ${countData.city_names.length} cities ▾`}
              </button>
            )}
            {showCityList && (
              <div className="max-h-40 overflow-y-auto bg-white border border-gray-100 rounded p-2 text-xs text-gray-600 columns-2 gap-2">
                {countData.city_names.map(n => <div key={n}>{n}</div>)}
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-400">Set filters to see recipient count</p>
        )}
      </div>

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800">← Back</button>
        <button
          onClick={onNext}
          disabled={!countData || countData.will_send === 0}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-40"
        >
          Next: Preview →
        </button>
      </div>
    </div>
  )
}

// ── Step 3: Preview ───────────────────────────────────────────────────────────

const STATUS_COLORS = {
  endorsed:           'bg-green-100 text-green-700',
  declined:           'bg-red-100 text-red-600',
  outreach_sent:      'bg-blue-100 text-blue-700',
  in_conversation:    'bg-purple-100 text-purple-700',
  call_scheduled:     'bg-purple-100 text-purple-800',
  follow_up:          'bg-amber-100 text-amber-700',
  no_contact_info:    'bg-gray-100 text-gray-500',
}

function PreviewCard({ preview }) {
  const [expanded, setExpanded] = useState(true)
  const statusInfo = STATUS_MAP[preview.status]

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between px-4 py-2.5 bg-gray-50 cursor-pointer"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium text-sm text-gray-900 truncate">{preview.city_name}</span>
          {statusInfo && (
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${statusInfo.color}`}>
              {statusInfo.label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400 shrink-0">
          <span>To: {preview.to_email}</span>
          <span>{expanded ? '▴' : '▾'}</span>
        </div>
      </div>

      {preview.empty_tags.length > 0 && (
        <div className="bg-amber-50 border-b border-amber-100 px-4 py-2 text-xs text-amber-700 flex items-center gap-1">
          ⚠️ Empty tags in this email:
          {preview.empty_tags.map(t => <TagPill key={t} tag={t} />)}
        </div>
      )}

      {expanded && (
        <div className="px-4 py-3 space-y-2">
          <div className="text-xs text-gray-500 font-medium">Subject: <span className="text-gray-800 font-normal">{preview.subject}</span></div>
          <div
            className="text-sm text-gray-800 border-t border-gray-100 pt-3 prose prose-sm max-w-none"
            dangerouslySetInnerHTML={{ __html: preview.body }}
          />
        </div>
      )}
    </div>
  )
}

function Step3Preview({ state, setState, onBack, onNext }) {
  const [loading, setLoading] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [error, setError] = useState(null)
  const [testCity, setTestCity] = useState(null)
  const [testEmail, setTestEmail] = useState('')
  const [testSending, setTestSending] = useState(false)
  const [testSent, setTestSent] = useState(false)

  const loadPreviews = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await mmPreview(state.selectedTemplateId, state.filters, state.emailPriority)
      setPreviewData(data)
      if (data.previews.length > 0) {
        setTestCity(data.previews[0].city_id)
      }
    } catch (e) {
      const detail = e.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to generate preview')
    } finally {
      setLoading(false)
    }
  }, [state.selectedTemplateId, state.filters, state.emailPriority])

  useEffect(() => { loadPreviews() }, [loadPreviews])

  const handleSendTest = async () => {
    if (!testCity || !testEmail) return
    setTestSending(true)
    setTestSent(false)
    try {
      await mmTest(state.selectedTemplateId, testCity, testEmail)
      setTestSent(true)
    } catch (e) {
      alert(e.response?.data?.detail || 'Test send failed')
    } finally {
      setTestSending(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Preview — 5 random cities from your filtered list</h3>
        <button onClick={loadPreviews} className="text-xs text-blue-600 hover:underline">Refresh ↺</button>
      </div>

      {loading && (
        <div className="text-center py-12 text-gray-400 text-sm">Generating previews…</div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {previewData && !loading && (
        <>
          {/* Tag warnings */}
          {Object.entries(previewData.tag_missing_counts).map(([tag, count]) => (
            <div key={tag} className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 text-xs text-amber-700">
              ⚠️ <TagPill tag={tag} /> will be blank in <strong>{count}</strong> of your sampled cities
            </div>
          ))}

          {/* Skipped summary */}
          {previewData.total_skipped > 0 && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-2 text-xs text-gray-600">
              <strong>{previewData.total_skipped} cities will be skipped</strong>
              {previewData.skipped_cities.slice(0, 5).map(s => (
                <span key={s.city_id} className="ml-2 text-gray-400">{s.city_name} ({s.reason})</span>
              ))}
              {previewData.total_skipped > 5 && <span className="text-gray-400"> +{previewData.total_skipped - 5} more</span>}
            </div>
          )}

          {/* Preview cards */}
          <div className="space-y-3">
            {previewData.previews.map(p => <PreviewCard key={p.city_id} preview={p} />)}
          </div>

          {/* Send test */}
          <div className="border border-gray-200 rounded-lg p-4 space-y-3">
            <h4 className="text-sm font-medium text-gray-800">Send a test to yourself</h4>
            <div className="flex gap-2 items-center flex-wrap">
              <select
                value={testCity || ''}
                onChange={e => setTestCity(parseInt(e.target.value))}
                className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
              >
                {previewData.previews.map(p => (
                  <option key={p.city_id} value={p.city_id}>Use data from: {p.city_name}</option>
                ))}
              </select>
              <input
                type="email"
                value={testEmail}
                onChange={e => setTestEmail(e.target.value)}
                placeholder="your@email.com"
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 w-52 focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
              <button
                onClick={handleSendTest}
                disabled={!testEmail || testSending}
                className="text-sm px-4 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50"
              >
                {testSending ? 'Sending…' : 'Send test'}
              </button>
              {testSent && <span className="text-xs text-green-600">✓ Test sent!</span>}
            </div>
          </div>
        </>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800">← Back</button>
        <button
          onClick={onNext}
          disabled={!previewData || previewData.total_will_send === 0}
          className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-500 disabled:opacity-40"
        >
          Next: Send →
        </button>
      </div>
    </div>
  )
}

// ── Step 4: Send ──────────────────────────────────────────────────────────────

function Step4Send({ state, setState, onBack }) {
  const [staggerRate, setStaggerRate] = useState('normal')
  const [jobId, setJobId] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const startPolling = useCallback((id) => {
    pollRef.current = setInterval(async () => {
      try {
        const status = await mmJobStatus(id)
        setJobStatus(status)
        if (['completed', 'cancelled'].includes(status.status)) {
          clearInterval(pollRef.current)
        }
      } catch {
        clearInterval(pollRef.current)
      }
    }, 2000)
  }, [])

  useEffect(() => () => clearInterval(pollRef.current), [])

  const handleSend = async () => {
    setStarting(true)
    setError(null)
    try {
      const result = await mmSend(
        state.selectedTemplateId,
        state.filters,
        state.emailPriority,
        staggerRate,
      )
      setJobId(result.job_id)
      setJobStatus({
        status: 'running',
        total: result.total_count,
        sent: 0,
        skipped: result.skipped_count,
        failed: 0,
        current_city: null,
        estimated_remaining_minutes: Math.round((result.total_count * (staggerRate === 'fast' ? 10 : staggerRate === 'slow' ? 60 : 30)) / 60),
      })
      startPolling(result.job_id)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to start send job')
    } finally {
      setStarting(false)
    }
  }

  const handlePause = async () => {
    if (!jobId) return
    await mmJobPause(jobId)
    setJobStatus(s => ({ ...s, status: 'paused' }))
  }

  const handleResume = async () => {
    if (!jobId) return
    await mmJobResume(jobId)
    setJobStatus(s => ({ ...s, status: 'running' }))
    startPolling(jobId)
  }

  const handleCancel = async () => {
    if (!jobId || !window.confirm('Cancel remaining sends? Emails already sent will not be undone.')) return
    await mmJobCancel(jobId)
    clearInterval(pollRef.current)
    setJobStatus(s => ({ ...s, status: 'cancelled' }))
  }

  if (jobStatus) {
    const { status, total, sent, skipped, failed, current_city, estimated_remaining_minutes } = jobStatus
    const progress = total > 0 ? Math.round((sent / total) * 100) : 0
    const done = ['completed', 'cancelled'].includes(status)

    return (
      <div className="space-y-5">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-800">
              {status === 'completed' ? '✓ Batch complete' :
               status === 'cancelled' ? 'Batch cancelled' :
               status === 'paused'    ? 'Paused' : 'Sending…'}
            </h3>
            <span className="text-sm text-gray-500">{sent} / {total} sent</span>
          </div>

          {/* Progress bar */}
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                status === 'completed' ? 'bg-green-500' :
                status === 'cancelled' ? 'bg-red-400' : 'bg-blue-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="text-xs text-gray-500 space-y-0.5">
            {current_city && status === 'running' && (
              <div>Currently sending to: <strong>{current_city}</strong></div>
            )}
            {!done && estimated_remaining_minutes > 0 && (
              <div>Estimated time remaining: ~{estimated_remaining_minutes} min</div>
            )}
            {failed > 0 && <div className="text-red-500">{failed} failed</div>}
            {skipped > 0 && <div className="text-gray-400">{skipped} skipped (no email / no mayor name)</div>}
          </div>

          {/* Controls */}
          {!done && (
            <div className="flex gap-2">
              {status === 'running' ? (
                <button onClick={handlePause}
                  className="text-sm px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50">
                  Pause
                </button>
              ) : (
                <button onClick={handleResume}
                  className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-500">
                  Resume
                </button>
              )}
              <button onClick={handleCancel}
                className="text-sm px-3 py-1.5 border border-red-200 text-red-600 rounded-lg hover:bg-red-50">
                Cancel remaining
              </button>
            </div>
          )}

          {status === 'completed' && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
              ✓ All done! {sent} emails sent. The Google Sheet will update within 30 seconds.
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="text-xs font-medium text-gray-500 block mb-2">Send speed</label>
        <div className="space-y-2 max-w-sm">
          {STAGGER_OPTIONS.map(opt => (
            <label key={opt.value} className="flex items-start gap-3 cursor-pointer">
              <input
                type="radio"
                name="stagger"
                value={opt.value}
                checked={staggerRate === opt.value}
                onChange={() => setStaggerRate(opt.value)}
                className="mt-0.5"
              />
              <div>
                <div className="text-sm text-gray-800">{opt.label}</div>
                <div className="text-xs text-gray-400">{opt.sub}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800">← Back</button>
        <button
          onClick={handleSend}
          disabled={starting}
          className="px-6 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-500 disabled:opacity-50"
        >
          {starting ? 'Starting…' : '🚀 Send batch'}
        </button>
      </div>
    </div>
  )
}

// ── Root component ────────────────────────────────────────────────────────────

export default function MailMerge({ initialCityIds = [], onBack }) {
  const [step, setStep] = useState(1)
  const [state, setState] = useState({
    // Template step
    selectedTemplateId: null,
    templateName: '',
    subject: '',
    bodyHtml: '',
    // Recipients step
    filters: { ...DEFAULT_FILTERS, city_ids: initialCityIds },
    emailPriority: ['mayor_work', 'mayor_personal', 'city'],
  })

  const STEP_TITLES = ['Write template', 'Choose recipients', 'Preview & test', 'Confirm & send']

  return (
    <div className="h-full overflow-auto bg-white">
      <div className="max-w-3xl mx-auto px-6 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button onClick={onBack} className="text-gray-400 hover:text-gray-700 text-lg leading-none">←</button>
          <div>
            <h2 className="text-base font-semibold text-gray-900">Mail Merge</h2>
            <p className="text-xs text-gray-400">{STEP_TITLES[step - 1]}</p>
          </div>
        </div>

        <StepHeader step={step} />

        {step === 1 && (
          <Step1Template
            state={state}
            setState={setState}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <Step2Recipients
            state={state}
            setState={setState}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <Step3Preview
            state={state}
            setState={setState}
            onBack={() => setStep(2)}
            onNext={() => setStep(4)}
          />
        )}
        {step === 4 && (
          <Step4Send
            state={state}
            setState={setState}
            onBack={() => setStep(3)}
          />
        )}
      </div>
    </div>
  )
}
