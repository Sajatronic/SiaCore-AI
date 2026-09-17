import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import DateFilter from '../components/DateFilter.jsx'
import RiskBadge from '../components/RiskBadge.jsx'

function defaultRange() {
  return { start: '', end: '' }
}

function normalizeMpn(value) {
  return String(value ?? '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
}

export default function PartsStock() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState(searchParams.get('search') || '')
  const [range, setRange] = useState(defaultRange)
  const [lifecycle, setLifecycle] = useState('')
  const [lifecycleOptions, setLifecycleOptions] = useState([])
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Search-fallback state: when the local filter over the loaded page comes
  // up empty for a non-trivial query, we go back to the server for an exact
  // MPN lookup instead of just reporting "No parts found". This is what
  // catches parts that exist but fall outside the capped page load below.
  const [fallbackRows, setFallbackRows] = useState(null)
  const [fallbackLoading, setFallbackLoading] = useState(false)

  // Populate the lifecycle dropdown from whatever values actually exist
  // in the stock table (Active, EOL, NRND, etc.) rather than hardcoding.
  useEffect(() => {
    let active = true
    api.getLifecycleStatuses().then(({ data, error }) => {
      if (!active || error || !data) return
      setLifecycleOptions(data.map((r) => r.lifecycle_status).filter(Boolean))
    })
    return () => {
      active = false
    }
  }, [])

  // Debounced, cancellable fetch — loads the base page (lifecycle/date
  // filtered, unfiltered by search) so the search box can filter locally
  // for the common case without a network round-trip per keystroke.
  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null
    const handle = setTimeout(async () => {
      setLoading(true)
      const { data, error } = await api.getPartsWithStock({
        search: null,
        lifecycle: lifecycle || null,
        start,
        end,
        limit: 10000,
      })
      if (!active) return
      if (error) setError(error.message)
      else {
        setError(null)
        setRows(data ?? [])
      }
      setLoading(false)
    }, 250)
    return () => {
      active = false
      clearTimeout(handle)
    }
  }, [range, lifecycle])

  const clearSearch = () => setSearch('')

  const rangeLabel = useMemo(() => {
    if (!range.start && !range.end) return 'Showing all data — no date filter applied.'
    return null
  }, [range])

  const locallyFiltered = useMemo(() => {
    const needle = normalizeMpn(search)
    if (!needle) return rows
    return rows.filter((row) => normalizeMpn(row.mpn) === needle)
  }, [rows, search])

  // Whenever the local filter misses on a real query, ask the backend
  // directly — this hits get_part_for_search plus its exact-MPN fallback
  // against the `parts` table, so a part outside the loaded page is still found.
  useEffect(() => {
    let active = true
    const needle = normalizeMpn(search)

    if (!needle || locallyFiltered.length > 0) {
      setFallbackRows(null)
      return
    }

    const handle = setTimeout(async () => {
      setFallbackLoading(true)
      const { data, error } = await api.getPartsWithStock({
        search,
        lifecycle: lifecycle || null,
        start: range.start || null,
        end: range.end || null,
        limit: 10000,
      })
      if (!active) return
      if (!error && Array.isArray(data)) setFallbackRows(data)
      setFallbackLoading(false)
    }, 250)

    return () => {
      active = false
      clearTimeout(handle)
    }
  }, [search, locallyFiltered.length, lifecycle, range])

  const visibleRows = locallyFiltered.length > 0 ? locallyFiltered : (fallbackRows ?? [])
  const isSearching = Boolean(normalizeMpn(search)) && locallyFiltered.length === 0 && fallbackLoading

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Parts & Stock</h1>
          <p className="text-secondary text-sm">
            Live part master data joined with current stock and pricing.{' '}
            {rangeLabel && <span className="text-teal">{rangeLabel}</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by MPN"
              className="surface rounded-lg pl-9 pr-9 py-2 text-sm w-64 outline-none focus:ring-2 focus:ring-royal"
            />
            {search && (
              <button
                onClick={clearSearch}
                aria-label="Clear search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-secondary hover:text-royal"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <select
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value)}
            className="surface rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-royal"
          >
            <option value="">All lifecycles</option>
            {lifecycleOptions.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
          <DateFilter value={range} onChange={setRange} />
          {(range.start || range.end) && (
            <button onClick={() => setRange(defaultRange())} className="text-xs text-secondary hover:text-royal transition">
              Clear dates
            </button>
          )}
        </div>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">{error}</div>}

      <div className="surface rounded-xl overflow-hidden card-hover">
        <table className="w-full text-sm">
          <thead className="surface-2 text-secondary text-left">
            <tr>
              <th className="px-4 py-3 font-medium">MPN</th>
              <th className="px-4 py-3 font-medium">Manufacturer</th>
              <th className="px-4 py-3 font-medium">Part Category</th>
              <th className="px-4 py-3 font-medium">Inventory Risk</th>
              <th className="px-4 py-3 font-medium">Stock Risk</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((r) => (
              <tr
                key={r.mpn}
                onClick={() => navigate(`/parts-stock/${encodeURIComponent(r.mpn)}`)}
                className="border-t cursor-pointer transition-colors hover:bg-[var(--bg-surface-2)]"
                style={{ borderColor: 'var(--border)' }}
              >
                <td className="px-4 py-3 font-medium">{r.mpn}</td>
                <td className="px-4 py-3 text-secondary">{r.manufacturer}</td>
                <td className="px-4 py-3">
                  <RiskBadge level={r.category || r.part_category || 'Uncategorized'} />
                </td>
                <td className="px-4 py-3">
                  <RiskBadge level={r.inventory_risk_level} />
                </td>
                <td className="px-4 py-3">
                  <RiskBadge level={r.stock_risk_level} />
                </td>
              </tr>
            ))}
            {(loading || isSearching) && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-secondary">
                  {isSearching ? 'Searching…' : 'Loading…'}
                </td>
              </tr>
            )}
            {!loading && !isSearching && visibleRows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-secondary">
                  No parts found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
