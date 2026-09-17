import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Package, Warehouse, ChevronRight } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import DateFilter from '../components/DateFilter.jsx'
import RiskBadge from '../components/RiskBadge.jsx'

function defaultRange() {
  return { start: '', end: '' }
}

const TYPE_META = {
  inventory: { icon: Warehouse, label: 'Inventory Report', accent: 'from-violet to-magenta' },
  part: { icon: Package, label: 'Part Report', accent: 'from-royal to-violet' },
}

function getRiskScore(row) {
  const value = row?.risk_score
    ?? row?.riskScore
    ?? row?.['Risk Score']
    ?? row?.part_score
    ?? row?.['Part Score']
    ?? row?.inventory_risk_score
    ?? row?.Final_Market_Risk_Score
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export default function Reports() {
  const navigate = useNavigate()
  const [range, setRange] = useState(defaultRange)
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null
    async function load() {
      setLoading(true)
      try {
        const rpcResult = await api.getReports(1000000, start, end)
        if (!active) return
        let rows = Array.isArray(rpcResult.data) ? rpcResult.data : rpcResult.data ? [rpcResult.data] : []
        let loadError = rpcResult.error

        // If the RPC is not deployed, returns no rows, or returns only one
        // report type, retry the source-table loader. This protects against
        // an older part-only get_reports function still cached in Supabase.
        const types = new Set(rows.map((row) => row.report_type ?? row.type).filter(Boolean))
        if (rows.length === 0 || types.size < 2) {
          const fallback = await api.getReportRowsFromSourceTables(1000000, start, end)
          if (!fallback.error && (fallback.data ?? []).length > 0) {
            const fallbackTypes = new Set((fallback.data ?? []).map((row) => row.report_type).filter(Boolean))
            // Prefer the fallback when it has both categories; otherwise keep
            // a valid RPC result instead of replacing it with less data.
            if (fallbackTypes.size >= 2 || rows.length === 0) rows = fallback.data ?? []
            loadError = null
          } else if (!loadError) {
            loadError = fallback.error
          }
        }

        if (!active) return
        setError(loadError?.message ?? null)
        setReports(rows)
      } catch (err) {
        if (active) setError(err?.message ?? 'Failed to load reports.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [range])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Reports</h1>
          <p className="text-secondary text-sm">Generated risk, inventory, and compliance reports.</p>
        </div>
        <div className="flex items-center gap-2">
          <DateFilter value={range} onChange={setRange} />
          {(range.start || range.end) && (
            <button onClick={() => setRange(defaultRange())} className="text-xs text-secondary hover:text-royal transition">
              Clear
            </button>
          )}
        </div>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">Couldn't load reports: {error}</div>}

      <div className="flex flex-col gap-3">
        {reports.map((r) => {
          const meta = TYPE_META[r.report_type] ?? TYPE_META.part
          const Icon = meta.icon
          const reportDate = r.created_at ?? r.last_modified_date ?? r.updated_at
          const riskScore = getRiskScore(r)
          return (
            <button
              key={`${r.report_type}-${r.report_id}-${reportDate ?? ''}`}
              onClick={() => navigate(`/reports/${r.report_type}/${encodeURIComponent(r.report_id)}${r.mpn ? `?mpn=${encodeURIComponent(r.mpn)}` : ''}`)}
              className="surface card-hover rounded-xl p-4 flex items-center gap-4 text-left w-full"
            >
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 bg-gradient-to-br ${meta.accent} shadow-lg`}>
                <Icon size={18} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium">{r.mpn}</span>
                  <span className="surface-2 text-secondary text-[11px] px-2 py-0.5 rounded-lg">{meta.label}</span>
                </div>
                <p className="text-secondary text-sm truncate mt-0.5">{r.summary}</p>
              </div>
              <div className="hidden sm:flex items-center gap-2 shrink-0">
                <RiskBadge level={r.score_label} />
              </div>
              <span className="text-xs text-secondary shrink-0 hidden md:block">
                {reportDate ? new Date(reportDate).toLocaleDateString() : '—'}
              </span>
              <ChevronRight size={16} className="text-secondary shrink-0" />
            </button>
          )
        })}
        {loading && <div className="surface rounded-xl p-10 text-center text-secondary text-sm">Loading reports…</div>}
        {!loading && reports.length === 0 && (
          <div className="surface rounded-xl p-10 text-center text-secondary text-sm">
            No reports found. If the source tables contain data, check the error shown above for a missing table, permission, or RLS problem.
          </div>
        )}
      </div>
    </div>
  )
}
