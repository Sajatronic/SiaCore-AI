import React from 'react'
import { Calendar } from 'lucide-react'

/**
 * value: { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
 * onChange receives the same shape back.
 */
export default function DateFilter({ value, onChange }) {
  const { start = '', end = '' } = value || {}

  return (
    <div className="surface flex items-center gap-2 rounded-full pl-4 pr-2 py-2">
      <Calendar size={15} className="text-secondary shrink-0" />
      <input
        type="date"
        value={start}
        max={end || undefined}
        onChange={(e) => onChange({ start: e.target.value, end })}
        className="bg-transparent text-sm outline-none w-[120px] font-body"
      />
      <span className="text-secondary text-sm">to</span>
      <input
        type="date"
        value={end}
        min={start || undefined}
        onChange={(e) => onChange({ start, end: e.target.value })}
        className="bg-transparent text-sm outline-none w-[120px] font-body"
      />
      <Calendar size={15} className="text-secondary shrink-0" />
    </div>
  )
}
