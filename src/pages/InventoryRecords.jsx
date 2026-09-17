import React, { useEffect, useState } from 'react'
import { api } from '../lib/supabaseClient.js'
import StatCard from '../components/StatCard.jsx'
import DateFilter from '../components/DateFilter.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import { Package, TrendingDown, Clock, AlertOctagon, ChevronLeft, ChevronRight } from 'lucide-react'

const PAGE_SIZE = 25

function defaultRange() {
  return { start: '', end: '' }
}

export default function InventoryRecords() {
  const [range, setRange] = useState(defaultRange)
  const [page, setPage] = useState(0)
  const [kpis, setKpis] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Reset to page 1 whenever the date filter changes.
  useEffect(() => {
    setPage(0)
  }, [range])

  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null
    async function load() {
      setLoading(true)
      const [k, r] = await Promise.all([
        api.getInventoryKpis(start, end),
        api.getInventoryRecords({ start, end, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
      ])
      if (!active) return
      if (k.error || r.error) setError(k.error?.message || r.error?.message)
      else setError(null)
      setKpis(k.data?.[0] ?? k.data)
      // Records already come back newest-first from get_inventory_records
      // (order by record_date desc) — keep that as the default sort here.
      setRows(r.data ?? [])
      setLoading(false)
    }
    load()
    return () => {
      active = false
    }
  }, [range, page])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Inventory Records</h1>
          <p className="text-secondary text-sm">Warehouse stock levels, allocation, and shortage exposure.</p>
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

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="On Hand (units)" value={loading ? '—' : kpis?.total_qty_on_hand?.toLocaleString?.() ?? '—'} icon={Package} />
        <StatCard label="Stock Sufficiency" value={loading ? '—' : `${kpis?.avg_stock_sufficiency_ratio ?? '—'}%`} icon={TrendingDown} deltaTone="neutral" />
        <StatCard label="Avg Lead Time" value={loading ? '—' : `${kpis?.avg_lead_time_days ?? '—'}d`} icon={Clock} deltaTone="neutral" />
        <StatCard label="Shortage Risk SKUs" value={loading ? '—' : kpis?.shortage_risk_sku_count ?? '—'} icon={AlertOctagon} deltaTone="negative" />
      </div>

      <div className="surface rounded-xl overflow-hidden card-hover">
        <table className="w-full text-sm">
          <thead className="surface-2 text-secondary text-left">
            <tr>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Part (MPN)</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium">Quantity</th>
              <th className="px-4 py-3 font-medium">Warehouse</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.inventory_id} className="border-t" style={{ borderColor: 'var(--border)' }}>
                <td className="px-4 py-3 text-secondary">{r.record_date ? new Date(r.record_date).toLocaleDateString() : '—'}</td>
                <td className="px-4 py-3 font-medium">{r.mpn}</td>
                <td className="px-4 py-3">
                  <RiskBadge level={r.risk_level} />
                </td>
                <td className="px-4 py-3">{r.qty_on_hand?.toLocaleString?.() ?? r.qty_on_hand}</td>
                <td className="px-4 py-3 text-secondary">{r.warehouse_name}</td>
              </tr>
            ))}
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-secondary">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-secondary">
                  No inventory records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="flex items-center justify-between px-4 py-3 border-t text-xs text-secondary" style={{ borderColor: 'var(--border)' }}>
          <span>Page {page + 1}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || loading}
              className="surface rounded-lg px-3 py-1.5 flex items-center gap-1 disabled:opacity-40 hover:bg-[var(--bg-surface-2)] transition"
            >
              <ChevronLeft size={13} /> Prev
            </button>
            <button
              onClick={() => setPage((p) => (rows.length < PAGE_SIZE ? p : p + 1))}
              disabled={rows.length < PAGE_SIZE || loading}
              className="surface rounded-lg px-3 py-1.5 flex items-center gap-1 disabled:opacity-40 hover:bg-[var(--bg-surface-2)] transition"
            >
              Next <ChevronRight size={13} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
