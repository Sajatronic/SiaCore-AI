import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import RiskBadge from '../components/RiskBadge.jsx'

export default function Distributors() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const handle = setTimeout(async () => {
      setLoading(true)
      const { data, error } = await api.getAllDistributors({ search: search.trim() || null, limit: 200 })
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
  }, [search])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Distributors</h1>
          <p className="text-secondary text-sm">
            Every distributor in the database, live from Supabase. Lowest risk shown first.
          </p>
        </div>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, code, or country"
            className="surface rounded-lg pl-9 pr-9 py-2 text-sm w-72 outline-none focus:ring-2 focus:ring-royal"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-secondary hover:text-royal"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">{error}</div>}

      <div className="surface rounded-xl overflow-hidden card-hover">
        <table className="w-full text-sm">
          <thead className="surface-2 text-secondary text-left">
            <tr>
              <th className="px-4 py-3 font-medium">Distributor</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Country</th>
              <th className="px-4 py-3 font-medium">Risk</th>
              <th className="px-4 py-3 font-medium">Authorized</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr
                key={d.d_code}
                onClick={() => navigate(`/distributors/${encodeURIComponent(d.d_code)}`)}
                className="border-t cursor-pointer transition-colors hover:bg-[var(--bg-surface-2)]"
                style={{ borderColor: 'var(--border)' }}
              >
                <td className="px-4 py-3 font-medium">{d.d_name}</td>
                <td className="px-4 py-3 text-secondary">{d.d_type ?? '—'}</td>
                <td className="px-4 py-3 text-secondary">{d.d_country ?? '—'}</td>
                <td className="px-4 py-3">
                  <RiskBadge level={d.relationship_risk_level} />
                </td>
                <td className="px-4 py-3 text-secondary">{d.d_authorized ?? '—'}</td>
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
                  No distributors found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
