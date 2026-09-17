import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  RefreshCw,
  Play,
  Factory,
  Boxes,
  ShieldCheck,
  GitBranch,
  Gauge,
  Layers,
  ImageOff,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Info,
} from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import DateFilter from '../components/DateFilter.jsx'
import RiskBadge from '../components/RiskBadge.jsx'

function defaultRange() {
  return { start: '', end: '' }
}

function RiskCard({ label, score, level, icon: Icon, note, decimals = 2, round = true }) {
  const numericScore = score === null || score === undefined || score === '' ? null : Number(score)
  const hasValue = numericScore !== null && Number.isFinite(numericScore)
  const display = hasValue && round ? numericScore.toFixed(decimals) : score
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
      <span className="font-display text-2xl font-bold">{hasValue ? display : '—'}</span>
      <RiskBadge level={level || 'Unknown'} />
      {note && <span className="text-secondary text-xs -mt-1">{note}</span>}
    </div>
  )
}

export default function PartDetails() {
  const { mpn } = useParams()
  const navigate = useNavigate()
  const [range, setRange] = useState(defaultRange)
  const [detail, setDetail] = useState(null)
  const [suppliers, setSuppliers] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [batchStatus, setBatchStatus] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(
    async (showRefreshSpinner = false) => {
      if (showRefreshSpinner) setRefreshing(true)
      else setLoading(true)
      const start = range.start || null
      const end = range.end || null
      const [d, s, sum] = await Promise.all([
        api.getPartDetails(mpn, start, end),
        api.getPartStockSuppliers(mpn, start, end),
        api.getPartStockSummary(mpn, start, end),
      ])
      if (d.error) setError(d.error.message)
      else {
        setError(null)
        setDetail(d.data?.[0] ?? d.data ?? null)
      }
      setSuppliers(s.data ?? [])
      setSummary(sum.data?.[0] ?? sum.data ?? null)
      setLoading(false)
      setRefreshing(false)
    },
    [mpn, range]
  )

  const runFullScrape = async () => {
    setBatchStatus('starting')
    const started = await api.runFullScrape()
    if (started.error) {
      setError(started.error.message)
      setBatchStatus(null)
      return
    }
    let status = 'queued'
    while (status === 'queued' || status === 'running') {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      const current = await api.getWorkflowJob(started.data.job_id)
      if (current.error) {
        setError(current.error.message)
        setBatchStatus(null)
        return
      }
      status = current.data?.status || status
      setBatchStatus(status)
    }
    if (status === 'success') {
      await load(false)
      setBatchStatus(null)
    } else {
      setError('Full scraping workflow failed. Check the scraper agent logs.')
      setBatchStatus(null)
    }
  }

  const refreshPart = async () => {
    setRefreshing(true)
    const workflow = await api.runPartRefresh(mpn)
    if (workflow.error) {
      setError(workflow.error.message)
      setRefreshing(false)
      return
    }
    await load(false)
  }

  useEffect(() => {
    load(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mpn, range])

  // Group price-break rows by distributor so each supplier appears once,
  // with its quantity tiers nested underneath — replaces the flat
  // one-row-per-price-break table (and the removed "Best Suppliers"
  // comparison feature) with an expandable, per-distributor view.
  const groupedSuppliers = useMemo(() => {
    const byKey = new Map()
    for (const s of suppliers) {
      const distributorCode = s.distributor_code ?? s.distributer_code ?? s.d_code ?? s.D_code
      const distributorName = s.distributor_name ?? s.distributer_name ?? s.d_name ?? s.D_name
      const key = distributorCode || distributorName || 'unknown'
      if (!byKey.has(key)) {
        byKey.set(key, {
          key,
          distributorCode,
          distributorName,
          distributorRiskLevel: s.distributor_risk_level,
          availableStock: s.available_stock,
          authorized: s.authorized,
          buyLink: s.buy_link,
          scrapedAt: s.scraped_at,
          packagingType: s.packaging_type,
          tiers: [],
        })
      }
      byKey.get(key).tiers.push({
        packageQty: s.package_qty,
        unitPrice: s.unit_price,
        extendedPrice: s.extended_price,
      })
    }
    return [...byKey.values()].map((d) => ({
      ...d,
      tiers: d.tiers.sort((a, b) => (a.packageQty ?? 0) - (b.packageQty ?? 0)),
    }))
  }, [suppliers])

  const [expanded, setExpanded] = useState(() => new Set())
  const toggleExpanded = (key) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate('/parts-stock')}
            className="text-secondary hover:text-royal text-xs flex items-center gap-1 mb-2 transition"
          >
            <ArrowLeft size={13} /> Back to Parts & Stock
          </button>
          <h1 className="font-display text-2xl font-bold">{mpn}</h1>
          <p className="text-secondary text-sm">Full risk and stock picture for this part, live from Supabase.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DateFilter value={range} onChange={setRange} />
          <button
            onClick={refreshPart}
            disabled={refreshing || batchStatus}
            className="surface rounded-full pl-3 pr-4 py-2 text-sm flex items-center gap-2 hover:bg-[var(--bg-surface-2)] transition disabled:opacity-60"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh Part Information'}
          </button>
          <button
            onClick={runFullScrape}
            disabled={Boolean(batchStatus) || refreshing}
            className="surface rounded-full pl-3 pr-4 py-2 text-sm flex items-center gap-2 hover:bg-[var(--bg-surface-2)] transition disabled:opacity-60"
          >
            <Play size={14} className={batchStatus === 'running' ? 'animate-pulse' : ''} />
            {batchStatus ? `Full scrape ${batchStatus}…` : 'Run Full Scrape'}
          </button>
        </div>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">{error}</div>}

      {!loading && !detail && !error && (
        <div className="surface rounded-xl p-10 text-center text-secondary text-sm">
          No data found for <span className="font-medium">{mpn}</span>.{' '}
          <Link to="/parts-stock" className="text-royal hover:underline">
            Back to Parts & Stock
          </Link>
        </div>
      )}

      {(loading || detail) && (
        <>
          {/* Basic Information */}
          <div className="surface card-hover rounded-xl p-6">
            <h2 className="font-display font-semibold mb-4">Basic Information</h2>
            <div className="flex flex-col lg:flex-row gap-6">
              <div className="w-full lg:w-48 shrink-0">
                <div className="aspect-square w-full max-w-[192px] rounded-xl overflow-hidden surface-2 flex items-center justify-center mx-auto lg:mx-0">
                  {detail?.image_url ? (
                    <img
                      src={detail.image_url}
                      alt={detail?.mpn ? `${detail.mpn} component` : 'Part image'}
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                        e.currentTarget.nextSibling.style.display = 'flex'
                      }}
                    />
                  ) : null}
                  <div
                    className="w-full h-full flex-col items-center justify-center gap-2 text-secondary"
                    style={{ display: detail?.image_url ? 'none' : 'flex' }}
                  >
                    <ImageOff size={28} />
                    <span className="text-xs">No image available</span>
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4 text-sm flex-1">
                <Field label="MPN" value={detail?.mpn} loading={loading} />
                <Field label="Manufacturer" value={detail?.manufacturer} loading={loading} />
                <Field label="Category" value={detail?.category} loading={loading} />
                <Field label="Lifecycle Status" value={detail?.lifecycle_status} loading={loading} />
                <Field label="Current Inventory" value={detail?.current_inventory?.toLocaleString?.() ?? detail?.current_inventory} loading={loading} />
                <Field label="Warehouse" value={detail?.warehouse_name} loading={loading} />
                <Field label="Part Score" value={detail?.part_score} loading={loading} />
                <Field label="Description" value={detail?.description} loading={loading} full />
              </div>
            </div>
          </div>

          {/* Risk Summary */}
          <div>
            <h2 className="font-display font-semibold mb-3">Risk Summary</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
              <RiskCard label="Manufacturer Risk" score={detail?.manufacturer_risk_score} level={detail?.manufacturer_risk_level} icon={Factory} />
              <RiskCard label="Inventory Risk" score={detail?.inventory_risk_score} level={detail?.inventory_risk_level} icon={Boxes} decimals={0} />
              <RiskCard label="Compliance Risk" score={detail?.compliance_risk_score} level={detail?.compliance_risk_level} icon={ShieldCheck} />
              <RiskCard label="Stock Risk"                 score={detail?.stock_risk_score}
                level={detail?.stock_risk_level}
                icon={Layers}
                decimals={0} />
              <RiskCard
                label="Alternative Parts"
                score={detail?.alternative_count}
                level={detail?.alternative_risk_level}
                icon={GitBranch}
                round={false}
              />
              <RiskCard
                label="Overall Part Score"
                score={detail?.overall_part_score}
                level={detail?.overall_part_level || detail?.stock_risk_level || detail?.inventory_risk_level || detail?.manufacturer_risk_level}
                icon={Gauge}
                decimals={0}
              />
            </div>
          </div>

          {/* Latest Stock Information */}
          <div className="surface card-hover rounded-xl p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <h2 className="font-display font-semibold">Latest Stock Information</h2>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
              <SummaryStat label="Total Stock" value={summary?.total_stock?.toLocaleString?.() ?? '—'} />
              <SummaryStat label="Suppliers" value={summary?.supplier_count ?? '—'} />
              <SummaryStat label="Lowest" value={summary?.lowest_price != null ? `$${summary.lowest_price}` : '—'} />
              <SummaryStat label="Highest" value={summary?.highest_price != null ? `$${summary.highest_price}` : '—'} />
              <SummaryStat label="Avg" value={summary?.avg_price != null ? `$${summary.avg_price}` : '—'} />
            </div>

            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-sm">
                <thead className="surface-2 text-secondary text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium w-8" />
                    <th className="px-3 py-2 font-medium">Distributor</th>
                    <th className="px-3 py-2 font-medium">Available Stock</th>
                    <th className="px-3 py-2 font-medium">Distributor Risk</th>
                    <th className="px-3 py-2 font-medium">Price Range</th>
                    <th className="px-3 py-2 font-medium">Packaging</th>
                    <th className="px-3 py-2 font-medium">Pricing Tiers</th>
                    <th className="px-3 py-2 font-medium">Authorized</th>
                    <th className="px-3 py-2 font-medium">Scraped At</th>
                    <th className="px-3 py-2 font-medium">Buy</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedSuppliers.map((d) => {
                    const isOpen = expanded.has(d.key)
                    const prices = d.tiers.map((t) => t.unitPrice).filter((p) => p != null)
                    const lowest = prices.length ? Math.min(...prices) : null
                    const highest = prices.length ? Math.max(...prices) : null
                    return (
                      <React.Fragment key={d.key}>
                        <tr
                          className="border-t cursor-pointer hover:bg-[var(--bg-surface-2)] transition-colors"
                          style={{ borderColor: 'var(--border)' }}
                          onClick={() => toggleExpanded(d.key)}
                        >
                          <td className="px-3 py-2.5 text-secondary">
                            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </td>
                          <td className="px-3 py-2.5 font-medium">
                            <span className="inline-flex items-center gap-1.5">
                              {d.distributorName}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  if (d.distributorCode) navigate(`/distributors/${encodeURIComponent(d.distributorCode)}`)
                                }}
                                aria-label={`View full details for ${d.distributorName}`}
                                title="View full distributor details"
                                className="text-secondary hover:text-royal transition"
                              >
                                <Info size={13} />
                              </button>
                            </span>
                          </td>
                          <td className="px-3 py-2.5">{d.availableStock?.toLocaleString?.() ?? d.availableStock ?? '—'}</td>
                          <td className="px-3 py-2.5">
                            <RiskBadge level={d.distributorRiskLevel} />
                          </td>
                          <td className="px-3 py-2.5">
                            {lowest != null
                              ? lowest === highest
                                ? `$${lowest}`
                                : `$${lowest} – $${highest}`
                              : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-secondary">{d.packagingType ?? '—'}</td>
                          <td className="px-3 py-2.5 text-secondary">
                            {d.tiers.length} tier{d.tiers.length === 1 ? '' : 's'}
                          </td>
                          <td className="px-3 py-2.5">
                            <AuthorizedBadge value={d.authorized} />
                          </td>
                          <td className="px-3 py-2.5 text-secondary">
                            {d.scrapedAt ? new Date(d.scrapedAt).toLocaleString() : '—'}
                          </td>
                          <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                            {d.buyLink ? (
                              <a
                                href={d.buyLink}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs font-medium rounded-lg px-2.5 py-1.5 bg-ocean-intel text-white hover:opacity-90 transition"
                              >
                                Buy <ExternalLink size={12} />
                              </a>
                            ) : (
                              <span className="text-secondary text-xs">—</span>
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="border-t" style={{ borderColor: 'var(--border)' }}>
                            <td />
                            <td colSpan={9} className="px-3 pb-3 pt-1">
                              <div className="surface-2 rounded-lg overflow-hidden">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="text-secondary text-left">
                                      <th className="px-3 py-2 font-medium">Quantity Break</th>
                                      <th className="px-3 py-2 font-medium">Unit Price</th>
                                      <th className="px-3 py-2 font-medium">Extended Price</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {d.tiers.map((t, i) => (
                                      <tr key={i} className="border-t" style={{ borderColor: 'var(--border)' }}>
                                        <td className="px-3 py-2">{t.packageQty != null ? `${t.packageQty.toLocaleString?.() ?? t.packageQty}+` : '—'}</td>
                                        <td className="px-3 py-2">{t.unitPrice != null ? `$${t.unitPrice}` : '—'}</td>
                                        <td className="px-3 py-2">{t.extendedPrice != null ? `$${t.extendedPrice.toLocaleString?.() ?? t.extendedPrice}` : '—'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                  {!loading && groupedSuppliers.length === 0 && (
                    <tr>
                      <td colSpan={10} className="px-3 py-8 text-center text-secondary">
                        No supplier stock records for this part in the selected range.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

    </div>
  )
}
function SummaryStat({ label, value }) {
  return (
    <div className="surface-2 rounded-lg px-3 py-2.5">
      <div className="text-secondary text-[11px] uppercase tracking-wide mb-0.5">{label}</div>
      <div className="font-display font-semibold text-sm">{value}</div>
    </div>
  )
}

function AuthorizedBadge({ value }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-secondary text-xs">Unknown</span>
  }
  const normalized = String(value).trim().toLowerCase()
  const isAuthorized = ['yes', 'y', 'true', 'authorized', '1'].includes(normalized)
  const isExplicitlyNo = ['no', 'n', 'false', 'unauthorized', 'non-authorized', '0'].includes(normalized)
  const label = isAuthorized ? 'Authorized' : isExplicitlyNo ? 'Non-Authorized' : String(value)
  const colorClass = isAuthorized
    ? 'text-teal bg-teal/10'
    : isExplicitlyNo
    ? 'text-magenta bg-magenta/10'
    : 'text-secondary surface-2'
  return (
    <span className={`inline-block text-xs font-medium rounded-full px-2.5 py-1 ${colorClass}`}>{label}</span>
  )
}

function Field({ label, value, loading, full = false }) {
  return (
    <div className={full ? 'col-span-2 sm:col-span-3' : ''}>
      <div className="text-secondary text-xs uppercase tracking-wide mb-1">{label}</div>
      <div className="font-medium">{loading ? '—' : value ?? '—'}</div>
    </div>
  )
}
