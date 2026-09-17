import React from 'react'

const TONES = {
  Critical: 'bg-sunset-insight text-white',
  'Very High': 'bg-sunset-insight text-white',
  High: 'bg-sunset-insight text-white',
  Medium: 'bg-violet/15 text-violet',
  Low: 'bg-teal/15 text-teal',
  'Very Low': 'bg-teal/15 text-teal',
}

export default function RiskBadge({ level, className = '' }) {
  const tone = TONES[level] ?? 'surface-2 text-secondary'
  return <span className={`px-2 py-0.5 rounded-full text-xs whitespace-nowrap ${tone} ${className}`}>{level ?? 'Unknown'}</span>
}
