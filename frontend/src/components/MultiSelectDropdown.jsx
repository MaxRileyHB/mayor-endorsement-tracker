import { useState, useEffect, useRef } from 'react'

export default function MultiSelectDropdown({ label, options, selected, onChange, formatOption }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggle = val =>
    onChange(selected.includes(val) ? selected.filter(v => v !== val) : [...selected, val])

  const fmt = val => formatOption ? formatOption(val) : val

  const buttonLabel =
    selected.length === 0 ? `All ${label}`
    : selected.length === 1 ? fmt(selected[0])
    : `${selected.length} ${label}`

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={`text-sm border rounded-lg px-2.5 py-1.5 bg-white flex items-center gap-1.5 whitespace-nowrap transition-colors ${
          selected.length > 0
            ? 'border-blue-400 text-blue-700 font-medium'
            : 'border-gray-200 text-gray-700 hover:border-gray-300'
        }`}
      >
        {buttonLabel}
        <svg className="w-3 h-3 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg min-w-[180px] max-h-64 overflow-y-auto">
          {selected.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="w-full text-left px-3 py-2 text-xs text-red-500 hover:bg-red-50 border-b border-gray-100"
            >
              Clear selection
            </button>
          )}
          {options.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-400 italic">No options yet</p>
          ) : (
            options.map(opt => (
              <label key={opt} className="flex items-center gap-2.5 px-3 py-1.5 hover:bg-gray-50 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.includes(opt)}
                  onChange={() => toggle(opt)}
                  className="rounded border-gray-300 text-blue-600 cursor-pointer"
                />
                <span className="text-sm text-gray-700">{fmt(opt)}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  )
}
