import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import {
  AlertTriangle,
  ShieldCheck,
  TrendingUp,
  Boxes,
  Factory,
  Truck,
  PackageCheck,
  Package,
  Warehouse,
  BellRing,
  Siren,
  Database,
  ArrowRight,
} from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import StatCard from '../components/StatCard.jsx'
import DateFilter from '../components/DateFilter.jsx'

function defaultRange() {
  // Empty = no date filter selected = all data, matching how DateFilter
  // and every RPC's optional p_start/p_end (null = no bound) behave.
  return { start: '', end: '' }
}

function RiskBadge({ level }) {
  const tone =
    level === 'High' || level === 'Critical'
      ? 'bg-sunset-insight text-white'
      : level === 'Medium'
      ? 'bg-violet/15 text-violet'
      : level === 'Low'
      ? 'bg-teal/15 text-teal'
      : 'surface-2 text-secondary'
  return <span className={`px-2 py-0.5 rounded-full text-xs ${tone}`}>{level ?? 'Unknown'}</span>
}

/**
 * Deliberately kept small. Only four things live here, in order of how
 * a supply-chain-risk person actually reads a dashboard:
 *   1. Database at a Glance  — is there data here at all, and how much
 *   2. Four core KPIs        — overall risk, compliance, optimization, SKUs
 *   3. Risk Trend            — is it getting better or worse over time
 *   4. Top At-Risk Parts     — which specific MPN to act on right now
 * Everything else that was here before (order performance stats, five
 * separate breakdown widgets, pipeline health) was cut — useful detail,
 * but not "most important," and it made real bugs harder to spot.
 */
export default function Overview() {
  const [range, setRange] = useState(defaultRange)
  const [summary, setSummary] = useState(null)
  const [totals, setTotals] = useState(null)
  const [totalsLoading, setTotalsLoading] = useState(true)
  const [trend, setTrend] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [partRisks, setPartRisks] = useState([])
  const [partRisksLoading, setPartRisksLoading] = useState(true)

  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null

    async function load() {
      setLoading(true)
      setError(null)
      const [s, t] = await Promise.all([
        api.getDashboardSummary(start, end),
        api.getRiskTrendRange(start, end),
      ])
      if (!active) return
      if (s.error || t.error) {
        setError(s.error?.message || t.error?.message)
      } else {
        setSummary(s.data?.[0] ?? s.data)
        setTrend(t.data ?? [])
      }
      setLoading(false)
    }
    load()
    return () => {
      active = false
    }
  }, [range])

  useEffect(() => {
    let active = true
    async function loadTotals() {
      setTotalsLoading(true)
      const { data } = await api.getDatabaseTotals()
      if (!active) return
      setTotals(data?.[0] ?? data)
      setTotalsLoading(false)
    }
    loadTotals()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null

    async function loadPartRisks() {
      setPartRisksLoading(true)
      const { data } = await api.getPartRiskInsights(12, start, end)
      if (!active) return
      setPartRisks(data ?? [])
      setPartRisksLoading(false)
    }
    loadPartRisks()
    return () => {
      active = false
    }
  }, [range])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Risk Overview</h1>
          <p className="text-secondary text-sm">
            Supply chain risk intelligence, refreshed live from Supabase.{' '}
            {!range.start && !range.end && <span className="text-teal">Showing all data — no date filter applied.</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DateFilter value={range} onChange={setRange} />
          {(range.start || range.end) && (
            <button
              onClick={() => setRange({ start: '', end: '' })}
              className="text-xs text-secondary hover:text-royal transition"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="surface rounded-xl p-4 text-magenta text-sm">
          Couldn't load dashboard data: {error}
        </div>
      )}

      {/* 1. Database at a Glance */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Database size={15} className="text-teal" />
          <h2 className="font-display text-sm font-semibold text-secondary uppercase tracking-wide">
            Database at a Glance
          </h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3">
          <StatCard label="Manufacturers" value={totalsLoading ? '—' : totals?.total_manufacturers ?? '—'} icon={Factory} />
          <StatCard label="Distributors" value={totalsLoading ? '—' : totals?.total_distributors ?? '—'} icon={Truck} />
          <StatCard label="Parts" value={totalsLoading ? '—' : totals?.total_parts ?? '—'} icon={Package} />
          <StatCard label="Warehouses" value={totalsLoading ? '—' : totals?.total_warehouses ?? '—'} icon={Warehouse} />
          <StatCard label="Orders" value={totalsLoading ? '—' : totals?.total_orders ?? '—'} icon={PackageCheck} />
          <StatCard label="Inventory Records" value={totalsLoading ? '—' : totals?.total_inventory_records ?? '—'} icon={Boxes} />
          <StatCard label="Open Risk Events" value={totalsLoading ? '—' : totals?.total_risk_events ?? '—'} icon={Siren} deltaTone="negative" />
          <StatCard label="Active Alerts" value={totalsLoading ? '—' : totals?.total_alerts ?? '—'} icon={BellRing} deltaTone="negative" />
        </div>
      </div>

      {/* 2. Four core KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Overall Risk Score"
          value={loading ? '—' : summary?.overall_risk_score ?? '—'}
          delta={summary?.risk_score_trend ? `${summary.risk_score_trend}% vs prior period` : null}
          deltaTone={summary?.risk_score_trend > 0 ? 'negative' : 'positive'}
          icon={AlertTriangle}
        />
        <StatCard
          label="Compliant Parts"
          value={loading ? '—' : `${summary?.compliant_parts_pct ?? '—'}%`}
          delta={summary?.non_compliant_count != null ? `${summary.non_compliant_count} non-compliant` : null}
          deltaTone="neutral"
          icon={ShieldCheck}
        />
        <StatCard
          label="Inventory Optimization"
          value={loading ? '—' : `+${summary?.optimization_score ?? '—'}%`}
          delta="vs last month"
          deltaTone="positive"
          icon={TrendingUp}
        />
        <StatCard
          label="Tracked SKUs"
          value={loading ? '—' : summary?.tracked_sku_count ?? '—'}
          delta={summary?.new_sku_count ? `+${summary.new_sku_count} new` : null}
          deltaTone="positive"
          icon={Boxes}
        />
      </div>

      {/* 3. Risk Trend */}
      <div className="surface card-hover rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4">Risk Trend</h2>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={trend}>
            <defs>
              <linearGradient id="oceanIntelStroke" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#00C2AB" />
                <stop offset="55%" stopColor="#2563EB" />
                <stop offset="100%" stopColor="#7C3AED" />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="period" stroke="var(--text-secondary)" fontSize={12} />
            <YAxis stroke="var(--text-secondary)" fontSize={12} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, backdropFilter: 'blur(12px)' }}
            />
            <Line type="monotone" dataKey="risk_score" stroke="url(#oceanIntelStroke)" strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 4. Top At-Risk Parts — the single most actionable widget */}
      <div className="surface card-hover rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold flex items-center gap-2">
            <AlertTriangle size={16} className="text-magenta" />
            Top At-Risk Parts
          </h2>
          <Link
            to="/parts-stock"
            className="text-xs text-royal hover:underline flex items-center gap-1 shrink-0"
          >
            View all parts <ArrowRight size={12} />
          </Link>
        </div>

        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm">
            <thead className="text-secondary text-left">
              <tr>
                <th className="px-3 py-2 font-medium">MPN</th>
                <th className="px-3 py-2 font-medium">Manufacturer</th>
                <th className="px-3 py-2 font-medium">Stock Risk</th>
                <th className="px-3 py-2 font-medium">Part Score</th>
              </tr>
            </thead>
            <tbody>
              {partRisks.map((p) => (
                <tr key={p.mpn} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="px-3 py-2.5 font-medium">{p.mpn}</td>
                  <td className="px-3 py-2.5 text-secondary">{p.manufacturer}</td>
                  <td className="px-3 py-2.5">
                    <RiskBadge level={p.stock_risk_level} />
                  </td>
                  <td className="px-3 py-2.5 font-medium">{p.part_score}</td>
                </tr>
              ))}
              {!partRisksLoading && partRisks.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-secondary">
                    No part risk data yet.
                  </td>
                </tr>
              )}
              {partRisksLoading && (
                <tr>
                  <td colSpan={4} className="px-3 py-8 text-center text-secondary">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
