import React from 'react'

export default function StatCard({ label, value, delta, deltaTone = 'positive', icon: Icon }) {
  const toneClass =
    deltaTone === 'positive' ? 'text-teal' : deltaTone === 'negative' ? 'text-magenta' : 'text-secondary'

  return (
    <div className="surface card-hover rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-secondary text-sm">{label}</span>
        {Icon && (
          <div className="w-8 h-8 rounded-lg bg-ocean-intel flex items-center justify-center shrink-0">
            <Icon size={15} className="text-white" />
          </div>
        )}
      </div>
      <span className="font-display text-2xl font-bold">{value}</span>
      {delta && <span className={`text-xs font-medium ${toneClass}`}>{delta}</span>}
    </div>
  )
}
