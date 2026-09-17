import React, { useEffect, useState } from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { AlertTriangle, ShieldCheck, TrendingUp, Boxes } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import StatCard from '../components/StatCard.jsx'
import DateFilter from '../components/DateFilter.jsx'

export default function Landing() {
  const [range, setRange] = useState('12m')
  const [summary, setSummary] = useState(null)
  const [trend, setTrend] = useState([])
  const [topRisks, setTopRisks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      setError(null)
      const months = range === '12m' ? 12 : range === '90d' ? 3 : range === '30d' ? 1 : 24
      const [s, t, r] = await Promise.all([
        api.getDashboardSummary(),
        api.getRiskTrend(months),
        api.getTopRiskCategories(5),
      ])
      if (!active) return
      if (s.error || t.error || r.error) {
        setError(s.error?.message || t.error?.message || r.error?.message)
      } else {
        setSummary(s.data?.[0] ?? s.data)
        setTrend(t.data ?? [])
        setTopRisks(r.data ?? [])
      }
      setLoading(false)
    }
    load()
    return () => {
      active = false
    }
  }, [range])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Risk Overview</h1>
          <p className="text-secondary text-sm">Supply chain risk intelligence, refreshed live from Supabase.</p>
        </div>
        <DateFilter value={range} onChange={setRange} />
      </div>

      {error && (
        <div className="surface rounded-xl p-4 text-magenta text-sm">
          Couldn't load dashboard data: {error}
        </div>
      )}

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="surface rounded-xl p-5 lg:col-span-2">
          <h2 className="font-display font-semibold mb-4">Risk Trend</h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="period" stroke="var(--text-secondary)" fontSize={12} />
              <YAxis stroke="var(--text-secondary)" fontSize={12} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8 }}
              />
              <Line type="monotone" dataKey="risk_score" stroke="#2563EB" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="surface rounded-xl p-5">
          <h2 className="font-display font-semibold mb-4">Top Risk Categories</h2>
          <div className="flex flex-col gap-3">
            {topRisks.map((r) => (
              <div key={r.category} className="flex items-center justify-between text-sm">
                <span className="text-secondary">{r.category}</span>
                <span className="font-medium">{r.pct}%</span>
              </div>
            ))}
            {!loading && topRisks.length === 0 && (
              <p className="text-secondary text-sm">No risk categories yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
