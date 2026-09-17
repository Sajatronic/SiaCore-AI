import React, { useEffect, useRef, useState } from 'react'
import { Search, X, Newspaper, Activity, Gauge, Sparkles, MapPin, Siren, ChevronDown, ChevronUp } from 'lucide-react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { api } from '../lib/supabaseClient.js'
import DateFilter from '../components/DateFilter.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import Logo from '../components/Logo.jsx'

function defaultRange() {
  return { start: '', end: '' }
}

function scoreTone(level) {
  switch (level) {
    case 'Critical':
    case 'High':
      return 'bg-sunset-insight text-white'
    case 'Medium':
      return 'bg-violet/15 text-violet'
    case 'Low':
    case 'Very Low':
      return 'bg-teal/15 text-teal'
    default:
      return 'surface-2 text-secondary'
  }
}

// Same tiering as scoreTone, but as real hex colors for Leaflet markers
// (which can't use Tailwind utility classes) — kept in sync with the
// brand palette in tailwind.config.js.
function severityColor(score) {
  const s = Number(score) || 0
  if (s >= 80) return '#D946EF' // magenta — Critical/High
  if (s >= 50) return '#7C3AED' // violet — Medium
  return '#00C2AB' // teal — Low/Very Low
}

function StatBox({ label, value, icon: Icon }) {
  return (
    <div className="surface card-hover rounded-xl p-4 flex items-center justify-between gap-3">
      <div>
        <div className="text-secondary text-[11px] uppercase tracking-wide">{label}</div>
        <div className="font-display text-2xl font-bold mt-1">{value ?? '—'}</div>
      </div>
      {Icon && (
        <div className="w-9 h-9 rounded-lg bg-ocean-intel flex items-center justify-center shrink-0">
          <Icon size={16} className="text-white" />
        </div>
      )}
    </div>
  )
}

// Plain Leaflet (not react-leaflet) — one map instance created once on
// mount, markers re-synced whenever `events` changes. Avoids pulling in
// an extra React-binding dependency for what's fundamentally an
// imperative widget anyway.
function GeoIntelligenceMap({ events, onSelect }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = L.map(containerRef.current, {
      worldCopyJump: true,
      zoomControl: true,
    }).setView([20, 10], 2)

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OSM &copy; CARTO',
      maxZoom: 18,
    }).addTo(map)

    markersRef.current = L.layerGroup().addTo(map)
    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!markersRef.current) return
    markersRef.current.clearLayers()
    const withCoords = events.filter((e) => e.latitude != null && e.longitude != null)
    withCoords.forEach((ev) => {
      const marker = L.circleMarker([ev.latitude, ev.longitude], {
        radius: 6 + Math.min(6, (Number(ev.severity_score) || 0) / 20),
        color: severityColor(ev.severity_score),
        fillColor: severityColor(ev.severity_score),
        fillOpacity: 0.75,
        weight: 1.5,
      })
      marker.bindTooltip(ev.title, { direction: 'top', offset: [0, -6] })
      marker.on('click', () => onSelect?.(ev))
      markersRef.current.addLayer(marker)
    })
  }, [events, onSelect])

  return (
    <div className="surface card-hover rounded-xl overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-display font-semibold flex items-center gap-2 text-sm">
          <MapPin size={15} className="text-royal" />
          Geo Intelligence
        </h3>
        <span className="text-secondary text-xs">
          {events.filter((e) => e.latitude != null && e.longitude != null).length} points
        </span>
      </div>
      <div ref={containerRef} className="h-72 w-full" />
    </div>
  )
}

// Compact, severity-sorted feed of the top open events — reuses the same
// `events` array News already fetches (no second query needed) rather
// than re-deriving "active alerts" from scratch server-side.
function ActiveAlerts({ events, onSelect }) {
  const sorted = [...events].sort((a, b) => (Number(b.severity_score) || 0) - (Number(a.severity_score) || 0))
  return (
    <div className="surface card-hover rounded-xl overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-display font-semibold flex items-center gap-2 text-sm">
          <Siren size={15} className="text-magenta" />
          Active Alerts
        </h3>
        <span className="bg-sunset-insight text-white text-xs font-bold px-2 py-0.5 rounded-full">{sorted.length}</span>
      </div>
      <div className="h-72 overflow-y-auto divide-y" style={{ borderColor: 'var(--border)' }}>
        {sorted.map((ev) => (
          <button
            key={ev.event_id}
            onClick={() => onSelect?.(ev)}
            className="w-full text-left px-4 py-3 hover:bg-[var(--bg-surface-2)] transition-colors flex flex-col gap-1.5"
            style={{ borderColor: 'var(--border)' }}
          >
            <span className="text-sm font-medium leading-snug line-clamp-2">{ev.title}</span>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`px-1.5 py-0.5 rounded-full text-[11px] font-bold ${scoreTone(ev.severity_signal)}`}>
                {ev.severity_score ?? '—'}
              </span>
              {ev.event_category && <span className="surface-2 text-secondary text-[11px] px-1.5 py-0.5 rounded-lg">{ev.event_category}</span>}
              {ev.geo_region && <span className="surface-2 text-secondary text-[11px] px-1.5 py-0.5 rounded-lg">{ev.geo_region}</span>}
            </div>
          </button>
        ))}
        {sorted.length === 0 && <p className="text-secondary text-sm text-center py-8">No active alerts.</p>}
      </div>
    </div>
  )
}

// Category-tinted, collapsible tag group for the supply-chain-links
// section of the event modal — a flat wall of 30+ pills reads as noise,
// so long lists collapse to a first slice with a "Show N more" toggle,
// and each category gets its own accent color instead of one flat grey.
function LinkTagGroup({ label, names, accent }) {
  const [expanded, setExpanded] = useState(false)
  const LIMIT = 12
  const visible = expanded ? names : names.slice(0, LIMIT)
  const hasMore = names.length > LIMIT

  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: accent }} />
        <h4 className="text-secondary text-[11px] uppercase tracking-wide">{label}</h4>
        <span className="text-secondary text-[11px]">({names.length})</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((name, i) => (
          <span
            key={`${name}-${i}`}
            className="text-xs px-2 py-1 rounded-lg"
            style={{ background: `${accent}22`, color: accent }}
          >
            {name}
          </span>
        ))}
        {hasMore && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs px-2 py-1 rounded-lg surface-2 text-royal hover:underline flex items-center gap-1"
          >
            {expanded ? (
              <>
                Show less <ChevronUp size={12} />
              </>
            ) : (
              <>
                Show {names.length - LIMIT} more <ChevronDown size={12} />
              </>
            )}
          </button>
        )}
      </div>
    </div>
  )
}

export default function News() {
  const [range, setRange] = useState(defaultRange)
  const [search, setSearch] = useState('')
  const [events, setEvents] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [articles, setArticles] = useState([])
  const [supplyChain, setSupplyChain] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    let active = true
    const start = range.start || null
    const end = range.end || null
    const handle = setTimeout(async () => {
      setLoading(true)
      try {
        const [e, s] = await Promise.all([
          api.getRecentEvents({ limit: 30, start, end, search: search.trim() || null }),
          api.getNewsStats(start, end),
        ])
        if (!active) return
        if (e.error || s.error) setError(e.error?.message || s.error?.message)
        else setError(null)
        setEvents(e.data ?? [])
        setStats(s.data?.[0] ?? s.data ?? null)
      } catch (err) {
        // A thrown error (network failure, missing env vars, RPC that
        // doesn't exist yet) used to leave the page stuck on "Loading…"
        // forever, because nothing after the throw ever ran — including
        // setLoading(false). This is why it never resolved.
        if (active) setError(err?.message ?? 'Failed to load news.')
      } finally {
        if (active) setLoading(false)
      }
    }, 250)
    return () => {
      active = false
      clearTimeout(handle)
    }
  }, [range, search])

  const openEvent = async (ev) => {
    setSelected(ev)
    setDetail(null)
    setArticles([])
    setSupplyChain(null)
    setDetailLoading(true)
    try {
      const [d, a, sc] = await Promise.all([
        api.getEventDetails(ev.event_id),
        api.getEventArticles(ev.event_id),
        api.getEventSupplyChain(ev.event_id),
      ])
      setDetail(d.data?.[0] ?? d.data ?? null)
      setArticles(a.data ?? [])
      setSupplyChain(sc.data?.[0] ?? sc.data ?? null)
    } catch {
      setDetail(null)
      setArticles([])
      setSupplyChain(null)
    } finally {
      setDetailLoading(false)
    }
  }
  const closeEvent = () => {
    setSelected(null)
    setDetail(null)
    setArticles([])
    setSupplyChain(null)
  }

  return (
    <div className="pt-6 flex flex-col gap-6">
      {/* SiaEye branding header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-teal shrink-0" />
            <span className="text-teal text-[11px] font-bold tracking-[0.25em] uppercase">SiaEye</span>
          </div>
          <Logo height={30} />
          <p className="text-secondary text-sm mt-1.5">Ancient Wisdom. Modern Intelligence. — Supply chain events scraped and scored by the risk engine.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search events…"
              className="surface rounded-lg pl-9 pr-9 py-2 text-sm w-56 outline-none focus:ring-2 focus:ring-royal"
            />
            {search && (
              <button onClick={() => setSearch('')} aria-label="Clear search" className="absolute right-2.5 top-1/2 -translate-y-1/2 text-secondary hover:text-royal">
                <X size={14} />
              </button>
            )}
          </div>
          <DateFilter value={range} onChange={setRange} />
          {(range.start || range.end) && (
            <button onClick={() => setRange(defaultRange())} className="text-xs text-secondary hover:text-royal transition">
              Clear
            </button>
          )}
        </div>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">Couldn't load news: {error}</div>}

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatBox label="Events" value={loading ? '—' : stats?.event_count} icon={Newspaper} />
        <StatBox label="Avg Severity" value={loading ? '—' : stats?.avg_severity} icon={Activity} />
        <StatBox label="Peak Severity" value={loading ? '—' : stats?.peak_severity} icon={Gauge} />
        <StatBox label="AI Analysis" value={loading ? '—' : stats?.ai_analysis_count} icon={Sparkles} />
      </div>

      {/* Geo Intelligence map + Active Alerts feed — both driven off the
          same `events` fetch above, so opening an alert or a map pin
          both reuse the exact same openEvent() modal. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <GeoIntelligenceMap events={events} onSelect={openEvent} />
        </div>
        <ActiveAlerts events={events} onSelect={openEvent} />
      </div>

      <div className="flex flex-col gap-3 min-w-0">
          {events.map((ev) => (
            <button
              key={ev.event_id}
              onClick={() => openEvent(ev)}
              className="surface card-hover rounded-xl p-4 flex flex-col gap-2 min-w-0 text-left w-full"
            >
              <div className="flex items-start justify-between gap-3 min-w-0">
                <h3 className="font-medium flex items-start gap-2 min-w-0 flex-1">
                  <Newspaper size={16} className="text-royal shrink-0 mt-0.5" />
                  <span className="break-words">{ev.title}</span>
                </h3>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${scoreTone(ev.severity_level)}`}
                  >
                    {ev.severity_score ?? '—'}
                  </span>
                  <RiskBadge level={ev.severity_level} />
                </div>
              </div>
              <p className="text-secondary text-sm break-words line-clamp-2">{ev.summary}</p>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {ev.event_category && <span className="surface-2 text-secondary text-xs px-2 py-0.5 rounded-lg">{ev.event_category}</span>}
                {ev.geo_region && <span className="surface-2 text-secondary text-xs px-2 py-0.5 rounded-lg">{ev.geo_region}</span>}
                <span className="text-xs text-secondary ml-auto">
                  {ev.retrieved_at ? new Date(ev.retrieved_at).toLocaleString() : '—'}
                </span>
              </div>
            </button>
          ))}
          {loading && <div className="surface rounded-xl p-6 text-center text-secondary text-sm">Loading events…</div>}
          {!loading && events.length === 0 && (
            <div className="surface rounded-xl p-6 text-center text-secondary text-sm">No recent events.</div>
          )}
      </div>

      {/* Event detail modal */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={closeEvent}>
          <div
            className="surface rounded-xl p-6 max-w-lg w-full max-h-[85vh] overflow-y-auto"
            style={{ background: 'var(--bg-surface-2)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 mb-3">
              <h3 className="font-display font-semibold text-lg break-words">{selected.title}</h3>
              <button onClick={closeEvent} className="text-secondary hover:text-royal shrink-0">
                <X size={18} />
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span
                className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${scoreTone(detail?.severity_level ?? selected.severity_level)}`}
              >
                {detail?.severity_score ?? selected.severity_score ?? '—'}
              </span>
              <RiskBadge level={detail?.severity_level ?? selected.severity_level} />
              {detail?.event_category && <span className="surface-2 text-secondary text-xs px-2 py-0.5 rounded-lg">{detail.event_category}</span>}
              {detail?.geo_region && <span className="surface-2 text-secondary text-xs px-2 py-0.5 rounded-lg">{detail.geo_region}</span>}
            </div>

            {detailLoading && <p className="text-secondary text-sm">Loading details…</p>}

            {!detailLoading && (
              <div className="flex flex-col gap-4 text-sm">
                <p className="text-secondary break-words">{detail?.summary ?? selected.summary}</p>

                {detail?.executive_summary && (
                  <div>
                    <h4 className="font-display font-semibold mb-1">Executive Summary</h4>
                    <p className="text-secondary break-words">{detail.executive_summary}</p>
                  </div>
                )}
                {detail?.business_impact && (
                  <div>
                    <h4 className="font-display font-semibold mb-1">Business Impact</h4>
                    <p className="text-secondary break-words">{detail.business_impact}</p>
                  </div>
                )}

                {articles.length > 0 && (
                  <div>
                    <h4 className="font-display font-semibold mb-1">Sources</h4>
                    <ul className="flex flex-col gap-1">
                      {articles.map((a, i) => (
                        <li key={i}>
                          <a
                            href={a.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-royal hover:underline break-words text-xs"
                          >
                            {a.provider ? `${a.provider} — ` : ''}
                            {a.title ?? a.url}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Real resolved supply-chain links — read straight from
                    risk_events.supply_chain_links (the same finalized
                    payload the Python pipeline computes and stores),
                    not re-derived. Manufacturers and Affected
                    Manufacturers are genuinely distinct categories in
                    that data (affected_manufacturers already merges in
                    AI-extracted names at write time) so they're kept
                    separate here rather than collapsed into one bucket. */}
                {supplyChain &&
                  [
                    ['linked_components', 'Components', '#00C2AB'],
                    ['linked_suppliers', 'Distributors', '#2563EB'],
                    ['linked_manufacturers', 'Manufacturers', '#7C3AED'],
                    ['affected_manufacturers', 'Affected Manufacturers', '#D946EF'],
                    ['linked_locations', 'Linked Locations', '#FF8A3D'],
                  ].some(([key]) => (supplyChain[key]?.length ?? 0) > 0) && (
                    <div className="flex flex-col gap-4 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                      {[
                        ['linked_components', 'Components', '#00C2AB'],
                        ['linked_suppliers', 'Distributors', '#2563EB'],
                        ['linked_manufacturers', 'Manufacturers', '#7C3AED'],
                        ['affected_manufacturers', 'Affected Manufacturers', '#D946EF'],
                        ['linked_locations', 'Linked Locations', '#FF8A3D'],
                      ].map(([key, label, accent]) => {
                        const names = supplyChain[key] ?? []
                        if (names.length === 0) return null
                        return <LinkTagGroup key={key} label={label} names={names} accent={accent} />
                      })}
                    </div>
                  )}

                {(detail?.geo_country || detail?.geo_region) && (
                  <div>
                    <h4 className="text-secondary text-[11px] uppercase tracking-wide mb-1.5">Locations</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {detail?.geo_country && <span className="surface-2 text-xs px-2 py-1 rounded-lg">{detail.geo_country}</span>}
                      {detail?.geo_region && detail.geo_region !== detail?.geo_country && (
                        <span className="surface-2 text-xs px-2 py-1 rounded-lg">{detail.geo_region}</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
