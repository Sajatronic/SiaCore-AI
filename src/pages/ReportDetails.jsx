import React, { useEffect, useState } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Sparkles, AlertTriangle, Lightbulb, Search, Package, Warehouse, Layers, ShoppingCart, GitBranch, Clock } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import RiskBadge from '../components/RiskBadge.jsx'

// Top-level fields rendered explicitly below — everything else in the
// jsonb row falls through to the generic prefix-grouped sections (or,
// failing that, a catch-all grid) so nothing from the report is ever
// silently dropped.
const EXPLAINED_KEYS = new Set([
  'id', 'Last_Modified_Date', 'MPN', 'Inventory ID',
  'Risk Level', 'Priority', 'Stock Band', 'Part Category',
  'Human Explanation', 'Business Impact', 'Executive Summary',
  'Root Cause Analysis', 'Final Recommendation', 'Route',
  'Total Financial Exposure', 'Is EOL', 'Requires Human Review', 'Review Reasons',
])

const PREFIX_GROUPS = [
  { prefix: 'alt_', title: 'Alternatives', icon: GitBranch },
  { prefix: 'supplier_', title: 'Supplier', icon: Layers },
  { prefix: 'buy_', title: 'Buy Recommendation', icon: ShoppingCart },
  { prefix: 'ltb_', title: 'Last-Time-Buy', icon: Clock },
]

function prettify(key) {
  return key
    .replace(/^(alt|supplier|buy|ltb)_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

// Some fields (e.g. buy_best_price, buy_fastest_lead_time) are stored as
// Python's str(dict) — single-quoted, None/True/False instead of
// null/true/false — not valid JSON. This converts and parses it so the
// UI can show real values instead of the raw "{'distributor_code': ...}"
// text. Returns null if the string isn't actually a dict-shaped value.
function parsePyDictString(value) {
  if (typeof value !== 'string' || !value.trim().startsWith('{')) return null
  try {
    const jsonish = value
      .replace(/'/g, '"')
      .replace(/\bNone\b/g, 'null')
      .replace(/\bTrue\b/g, 'true')
      .replace(/\bFalse\b/g, 'false')
    const parsed = JSON.parse(jsonish)
    return typeof parsed === 'object' && parsed !== null ? parsed : null
  } catch {
    return null
  }
}

// Renders any field value for the prefix-grouped sections. Falls back to
// the previous boolean/string handling for anything that isn't a
// dict-shaped string.
function formatFieldValue(key, value) {
  const parsed = parsePyDictString(value)
  if (parsed) {
    if (key === 'buy_best_price') {
      const price = parsed.unit_price != null ? `$${parsed.unit_price}` : 'price unavailable'
      const dist = parsed.distributor_code ? ` via ${parsed.distributor_code}` : ''
      const moq = parsed.moq != null ? ` · MOQ ${parsed.moq}` : ''
      return `${price}${dist}${moq}`
    }
    if (key === 'buy_fastest_lead_time') {
      const dist = parsed.distributor_code ?? 'Unknown supplier'
      const lt = parsed.lead_time_days != null ? `${parsed.lead_time_days} days` : 'lead time not reported'
      return `${dist} — ${lt}`
    }
    // Generic fallback: render every non-null key of the parsed object.
    return Object.entries(parsed)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => `${prettify(k)}: ${v}`)
      .join(' · ')
  }
  return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)
}

function normalizeReportRow(row) {
  if (!row || typeof row !== 'object') return row
  const aliases = {
    MPN: ['mpn', 'part_number'],
    'Inventory ID': ['inventory_id'],
    'Risk Level': ['risk_level', 'risk'],
    Priority: ['priority'],
    Route: ['route'],
    'Final Recommendation': ['final_recommendation', 'recommendation', 'recommended_action'],
    'Last_Modified_Date': ['last_modified_date', 'last_modified_at'],
    'Executive Summary': ['executive_summary', 'summary'],
    'Human Explanation': ['human_explanation', 'explanation'],
    'Business Impact': ['business_impact', 'impact'],
    'Total Financial Exposure': ['total_financial_exposure', 'ltb_total_extended_value'],
    'Part Category': ['part_category'],
    'Stock Band': ['stock_band'],
    'Is EOL': ['is_eol'],
    'Requires Human Review': ['requires_human_review'],
    'Review Reasons': ['review_reasons', 'review_reason'],
  }
  const result = { ...row }
  Object.entries(aliases).forEach(([target, keys]) => {
    if (result[target] === undefined || result[target] === null || result[target] === '') {
      const source = keys.find((key) => row[key] !== undefined && row[key] !== null && row[key] !== '')
      if (source) result[target] = row[source]
    }
  })
  return result
}

function Section({ icon: Icon, title, children, tone }) {
  return (
    <div className="surface card-hover rounded-xl p-5">
      <h2 className="font-display font-semibold flex items-center gap-2 mb-2.5">
        <Icon size={16} className={tone ?? 'text-royal'} /> {title}
      </h2>
      {children}
    </div>
  )
}

export default function ReportDetails() {
  const { type, id } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        const fetcher = type === 'inventory' ? api.getInventoryReport : api.getPartReport
        const lookupMpn = searchParams.get('mpn')
        const { data, error } = type === 'inventory' ? await fetcher(id, lookupMpn) : await fetcher(id)
        if (!active) return
        if (error) setError(error.message)
        else setError(null)
        const row = Array.isArray(data) ? data[0] : data
        setData(normalizeReportRow(row ?? null))
      } catch (err) {
        if (active) setError(err?.message ?? 'Failed to load report.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [type, id, searchParams])

  const scoreLabel = data?.['Risk Level'] ?? data?.['Stock Band'] ?? data?.['Part Category'] ?? 'Unknown'
  const reportDate = data?.['Last_Modified_Date'] ?? data?.last_modified_date ?? data?.created_at
  const scoreTitle = type === 'inventory' ? 'Inventory Risk' : 'Stock Band'

  return (
    <div className="pt-6 flex flex-col gap-6 max-w-4xl mx-auto">
      <button onClick={() => navigate('/reports')} className="text-secondary hover:text-royal text-xs flex items-center gap-1 w-fit transition">
        <ArrowLeft size={13} /> Back to Reports
      </button>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">Couldn't load report: {error}</div>}
      {loading && <div className="surface rounded-xl p-10 text-center text-secondary text-sm">Loading report…</div>}
      {!loading && !data && !error && (
        <div className="surface rounded-xl p-10 text-center text-secondary text-sm">
          Report not found. <Link to="/reports" className="text-royal hover:underline">Back to Reports</Link>
        </div>
      )}

      {!loading && data && (
        <>
          {/* Hero: MPN + the highlighted score */}
          <div className="rounded-2xl overflow-hidden surface">
            <div className={`h-1.5 bg-gradient-to-r ${type === 'inventory' ? 'from-violet to-magenta' : 'from-royal to-violet'}`} aria-hidden />
            <div className="p-6 flex flex-wrap items-center justify-between gap-5">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br ${type === 'inventory' ? 'from-violet to-magenta' : 'from-royal to-violet'} shadow-lg`}>
                  {type === 'inventory' ? <Warehouse size={20} className="text-white" /> : <Package size={20} className="text-white" />}
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h1 className="font-display text-xl font-bold">{data.MPN}</h1>
                    <span className="surface-2 text-secondary text-[11px] px-2 py-0.5 rounded-lg">
                      {type === 'inventory' ? 'Inventory Report' : 'Part Report'}
                    </span>
                  </div>
                  <p className="text-secondary text-xs mt-1">
                    {reportDate && new Date(reportDate).toLocaleString()}
                  </p>
                  {type === 'inventory' && data['Inventory ID'] && (
                    <p className="text-secondary text-xs mt-0.5">Inventory ID: {data['Inventory ID']}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <div className="text-secondary text-[11px] uppercase tracking-wide">{scoreTitle}</div>
                  <div className="mt-1"><RiskBadge level={scoreLabel} className="text-sm px-3 py-1" /></div>
                </div>
                {data['Total Financial Exposure'] != null && (
                  <div className="text-right">
                    <div className="text-secondary text-[11px] uppercase tracking-wide">Financial Exposure</div>
                    <div className="font-display text-lg font-bold mt-0.5">${data['Total Financial Exposure']}</div>
                  </div>
                )}
              </div>
            </div>
            {(data['Is EOL'] || data['Requires Human Review']) && (
              <div className="px-6 pb-5 flex flex-wrap gap-2">
                {data['Is EOL'] && (
                  <span className="bg-sunset-insight text-white text-xs px-2.5 py-1 rounded-full flex items-center gap-1">
                    <AlertTriangle size={12} /> End of Life
                  </span>
                )}
                {data['Requires Human Review'] && (
                  <span className="bg-violet/15 text-violet text-xs px-2.5 py-1 rounded-full flex items-center gap-1">
                    <Search size={12} /> Requires Human Review
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Explanation & recommendation */}
          {data['Executive Summary'] && (
            <Section icon={Sparkles} title="Executive Summary">
              <p className="text-secondary text-sm leading-relaxed">{data['Executive Summary']}</p>
            </Section>
          )}
          {data['Human Explanation'] && (
            <Section icon={Search} title="Explanation">
              <p className="text-secondary text-sm leading-relaxed">{data['Human Explanation']}</p>
            </Section>
          )}
          {data['Business Impact'] && (
            <Section icon={AlertTriangle} title="Business Impact" tone="text-magenta">
              <p className="text-secondary text-sm leading-relaxed">{data['Business Impact']}</p>
            </Section>
          )}

          {/* Recommendation — the payoff, styled as a standout callout */}
          {data['Final Recommendation'] && (
            <div className="rounded-xl p-5 bg-gradient-to-br from-teal/10 to-royal/10 border" style={{ borderColor: 'var(--border)' }}>
              <h2 className="font-display font-semibold flex items-center gap-2 mb-2 text-teal">
                <Lightbulb size={16} /> Final Recommendation
              </h2>
              <p className="text-sm leading-relaxed">{data['Final Recommendation']}</p>
            </div>
          )}

          {/* Generic prefix-grouped sections: Alternatives / Supplier /
              Buy Recommendation / Last-Time-Buy — whatever fields exist */}
          {PREFIX_GROUPS.map(({ prefix, title, icon }) => {
            const entries = Object.entries(data).filter(
              ([k, v]) => k.startsWith(prefix) && v !== null && v !== '' && !EXPLAINED_KEYS.has(k)
            )
            if (entries.length === 0) return null
            return (
              <Section key={prefix} icon={icon} title={title}>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 text-sm">
                  {entries.map(([k, v]) => (
                    <div key={k}>
                      <div className="text-secondary text-xs mb-0.5">{prettify(k)}</div>
                      <div className="font-medium break-words">{formatFieldValue(k, v)}</div>
                    </div>
                  ))}
                </div>
              </Section>
            )
          })}

        </>
      )}
    </div>
  )
}
