import { createClient } from '@supabase/supabase-js'

const rawUrl = import.meta.env.VITE_SUPABASE_URL
const rawKey = import.meta.env.VITE_SUPABASE_ANON_KEY

function isValidUrl(value) {
  try {
    // eslint-disable-next-line no-new
    new URL(value)
    return true
  } catch {
    return false
  }
}

const isConfigured = Boolean(rawUrl) && Boolean(rawKey) && isValidUrl(rawUrl)

if (!isConfigured) {
  // eslint-disable-next-line no-console
  console.warn(
    'Missing or invalid VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY. Copy .env.example to .env, ' +
      'fill in your real Supabase project URL + anon key, then restart `npm run dev`. ' +
      'Falling back to a placeholder client so the app can still render — every Supabase call will fail until this is fixed.'
  )
}

// createClient() throws synchronously on an invalid URL, which — without
// this guard — happens during module import, before React even mounts,
// producing a fully blank page with only a console error. Falling back to
// a syntactically-valid placeholder URL lets the app render normally and
// fail per-request instead (visible as errors in each screen, not a blank page).
export const supabase = createClient(
  isConfigured ? rawUrl : 'https://placeholder.supabase.co',
  isConfigured ? rawKey : 'placeholder-anon-key'
)

export const supabaseConfigured = isConfigured

const pick = (row, keys) => keys.map((key) => row?.[key]).find((value) => value !== undefined && value !== null && value !== '')
const normalizePartDetail = (row) => {
  if (!row || typeof row !== 'object') return row
  const risk = row.pcn_risk && typeof row.pcn_risk === 'object' ? row.pcn_risk : {}
  const merged = { ...row, ...risk }
  return {
    ...row,
    mpn: pick(merged, ['mpn', 'MPN', 'part_number', 'Part Number']) ?? row.mpn,
    manufacturer_risk_score: pick(merged, ['manufacturer_risk_score', 'Manufacturer Risk Score', 'manufacturer_score', 'Manufacturer Score']),
    manufacturer_risk_level: pick(merged, ['manufacturer_risk_level', 'Manufacturer Risk Level', 'manufacturer_level', 'Manufacturer Level']),
    inventory_risk_score: pick(merged, ['inventory_risk_score', 'Inventory Risk Score', 'inventory_score', 'Inventory Score']),
    inventory_risk_level: pick(merged, ['inventory_risk_level', 'Inventory Risk Level', 'inventory_level', 'Inventory Level']),
    compliance_risk_score: pick(merged, ['compliance_risk_score', 'Compliance_Risk_Score', 'Final_Compliance_Risk_Score', 'Compliance Risk Score', 'compliance_score', 'Compliance Score', 'risk_score', 'Risk Score', 'score']),
    compliance_risk_level: pick(merged, ['compliance_risk_level', 'Compliance_Risk_Level', 'Compliance_Risk_Tier', 'Compliance Risk Level', 'compliance_risk_tier', 'Compliance Risk Tier', 'risk_tier', 'Risk Tier', 'risk_level', 'Risk Level', 'tier']),
    stock_risk_score: pick(merged, ['stock_risk_score', 'Stock Risk Score', 'risk_score', 'Risk Score', 'Final_Market_Risk_Score', 'final_market_risk_score']),
    stock_risk_level: pick(merged, ['stock_risk_level', 'Stock Risk Level', 'risk_category', 'Risk Category']),
    alternative_count: pick(merged, ['alternative_count', 'Alternative Count', 'alternatives_count', 'Alternatives Count']),
    overall_part_score: pick(merged, ['overall_part_score', 'Overall Part Score', 'part_score', 'Part Score', 'Final_Market_Risk_Score', 'final_market_risk_score']),
  }
}

/**
 * Every function below calls a Postgres function (RPC) defined in
 * sql/01_stored_procedures.sql. Keeping the aggregation logic in the
 * database means the frontend only ever asks for exactly the shape
 * of data it needs to render.
 */
export const api = {
  // Landing / overview screen
  getDashboardSummary: (start = null, end = null) =>
    supabase.rpc('get_dashboard_summary', { p_start: start, p_end: end }),
  getDatabaseTotals: () => supabase.rpc('get_database_totals'),
  getPartRiskInsights: (limit = 15, start = null, end = null) =>
    supabase.rpc('get_part_risk_insights', { p_limit: limit, p_start: start, p_end: end }),
  getRiskTrend: (months = 12) => supabase.rpc('get_risk_trend', { p_months: months }),
  getRiskTrendRange: (start = null, end = null) =>
    supabase.rpc('get_risk_trend_range', { p_start: start, p_end: end }),
  getTopRiskCategories: (limit = 5, start = null, end = null) =>
    supabase.rpc('get_top_risk_categories', { p_limit: limit, p_start: start, p_end: end }),

  // Deeper database analysis widgets (Overview screen, lower section)
  // Every one of these takes an optional (start, end) date range — pass
  // null/null (the default) to include all data with no date filtering.
  getComplianceBreakdown: (start = null, end = null) =>
    supabase.rpc('get_compliance_breakdown', { p_start: start, p_end: end }),
  getManufacturerRiskDistribution: (start = null, end = null) =>
    supabase.rpc('get_manufacturer_risk_distribution', { p_start: start, p_end: end }),
  getDistributorRiskDistribution: (start = null, end = null) =>
    supabase.rpc('get_distributor_risk_distribution', { p_start: start, p_end: end }),
  getOrderPerformanceSummary: (start = null, end = null) =>
    supabase.rpc('get_order_performance_summary', { p_start: start, p_end: end }),
  getInventoryHealthBreakdown: (start = null, end = null) =>
    supabase.rpc('get_inventory_health_breakdown', { p_start: start, p_end: end }),
  getPipelineHealth: (limit = 8, start = null, end = null) =>
    supabase.rpc('get_pipeline_health', { p_limit: limit, p_start: start, p_end: end }),
  getEventsBySeverity: (start = null, end = null) =>
    supabase.rpc('get_events_by_severity', { p_start: start, p_end: end }),

  // Starts the external scraper workflow for one MPN. Configure the
  // endpoint with VITE_SCRAPER_WORKFLOW_URL; secrets remain on the agent host.
  runPartRefresh: async (mpn) => {
    const endpoint = import.meta.env.VITE_SCRAPER_WORKFLOW_URL
    if (!endpoint) return { data: null, error: new Error('VITE_SCRAPER_WORKFLOW_URL is not configured') }
    try {
      const response = await fetch(`${endpoint.replace(/\/$/, '')}/refresh-part`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mpn }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) return { data: null, error: new Error(body.detail || `Workflow failed (${response.status})`) }
      return { data: body, error: null }
    } catch (error) {
      return { data: null, error }
    }
  },
  runFullScrape: async ({ limit = null, resetCheckpoint = false } = {}) => {
    const endpoint = import.meta.env.VITE_SCRAPER_WORKFLOW_URL
    if (!endpoint) return { data: null, error: new Error('VITE_SCRAPER_WORKFLOW_URL is not configured') }
    try {
      const response = await fetch(`${endpoint.replace(/\/$/, '')}/refresh-all`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit, reset_checkpoint: resetCheckpoint }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) return { data: null, error: new Error(body.detail || `Workflow failed (${response.status})`) }
      return { data: body, error: null }
    } catch (error) { return { data: null, error } }
  },
  getWorkflowJob: async (jobId) => {
    const endpoint = import.meta.env.VITE_SCRAPER_WORKFLOW_URL
    if (!endpoint) return { data: null, error: new Error('VITE_SCRAPER_WORKFLOW_URL is not configured') }
    try {
      const response = await fetch(`${endpoint.replace(/\/$/, '')}/jobs/${encodeURIComponent(jobId)}`)
      const body = await response.json().catch(() => ({}))
      if (!response.ok) return { data: null, error: new Error(body.detail || `Workflow status failed (${response.status})`) }
      return { data: body, error: null }
    } catch (error) { return { data: null, error } }
  },

  // Parts & Stock screen
  // Matches get_parts_with_stock(p_search, p_lifecycle, p_start, p_end, p_limit, p_offset)
  // in sql/04_add_lifecycle_filter.sql — param NAMES must match exactly,
  // PostgREST resolves RPC args by name, not position.
  // p_lifecycle filters on stock."Lifecycle_Status" (e.g. Active, EOL, NRND).
  getPartsWithStock: async ({ search = null, lifecycle = null, start = null, end = null, limit = 100, offset = 0 } = {}) => {
    const rpcName = search && String(search).trim() ? 'search_parts_by_mpn' : 'get_parts_with_stock'
    const base = await supabase.rpc(rpcName, {
      p_search: search,
      p_lifecycle: lifecycle,
      p_start: start,
      p_end: end,
      p_limit: limit,
      p_offset: offset,
    })
    // Do not fall back to the old paginated function during a search: an
    // older deployment may ignore p_search and return unrelated first-page rows.
    if (base.error || !Array.isArray(base.data) || base.data.length === 0) return base

    const categories = await supabase.rpc('get_part_categories_by_mpn')
    const byMpn = !categories.error && Array.isArray(categories.data)
      ? new Map(categories.data.map((row) => [String(row.mpn).trim().toLowerCase(), row.category]))
      : new Map()

    // Risk/inventory tables can contain several records for one MPN. The
    // Parts & Stock page is a part-level view, so render one row per MPN.
    const seen = new Set()
    const data = base.data
      .map((row) => {
        const key = String(row.mpn ?? '').trim().toLowerCase()
        const category = byMpn.get(key)
        return category ? { ...row, category } : row
      })
      .filter((row) => {
        const key = String(row.mpn ?? '').trim().toLowerCase()
        if (!key || seen.has(key)) return false
        seen.add(key)
        return true
      })

    return { ...base, data }
  },
  getPartAlternatives: (mpn) => supabase.rpc('get_part_alternatives', { p_mpn: mpn }),
  getLifecycleStatuses: () => supabase.rpc('get_lifecycle_statuses'),

  // Part Details screen — get_part_details / get_part_stock_suppliers /
  // get_part_stock_summary, all (p_mpn, p_start, p_end).
  getPartDetails: async (mpn, start = null, end = null) => {
    const enrichCompliance = async (items) => {
      const normalized = items.map(normalizePartDetail)
      let compliance = await supabase.rpc('get_compliance_risk_by_mpn_v3', { p_mpn: mpn })
      if (compliance.error) compliance = await supabase.rpc('get_compliance_risk_by_mpn_v2', { p_mpn: mpn })
      if (compliance.error || !compliance.data) return normalized
      const complianceRow = Array.isArray(compliance.data) ? compliance.data[0] : compliance.data
      return complianceRow
        ? normalized.map((item) => normalizePartDetail({ ...item, ...complianceRow }))
        : normalized
    }
    const rpc = await supabase.rpc('get_part_details', { p_mpn: mpn, p_start: start, p_end: end })
    const rows = Array.isArray(rpc.data) ? rpc.data : rpc.data ? [rpc.data] : []
    if (rows.length > 0) return { data: await enrichCompliance(rows), error: null }

    // Retry without date filters when an older deployed RPC rejects the
    // optional arguments or returns no row for an otherwise valid MPN.
    const retry = await supabase.rpc('get_part_details', { p_mpn: mpn, p_start: null, p_end: null })
    const retryRows = Array.isArray(retry.data) ? retry.data : retry.data ? [retry.data] : []
    return retryRows.length > 0
      ? { data: await enrichCompliance(retryRows), error: null }
      : { data: [], error: rpc.error ?? retry.error }
  },
  getPartStockSuppliers: async (mpn, start = null, end = null) => {
    const latest = await supabase.rpc('get_part_stock_suppliers_v2', { p_mpn: mpn, p_start: start, p_end: end })
    const response = latest.error
      ? await supabase.rpc('get_part_stock_suppliers', { p_mpn: mpn, p_start: start, p_end: end })
      : latest
    if (response.error || !Array.isArray(response.data)) return response

    // Ensure the displayed timestamp is the maximum timestamp returned for
    // each distributor, even when an older RPC/fallback supplies mixed rows.
    const maxByDistributor = new Map()
    response.data.forEach((row) => {
      const code = row.distributor_code ?? row.distributer_code ?? row.d_code ?? row.D_code ?? row.distributor_name
      const value = row.scraped_at ?? row.last_updated
      if (!code || !value) return
      const current = maxByDistributor.get(code)
      if (!current || new Date(value).getTime() > new Date(current).getTime()) maxByDistributor.set(code, value)
    })
    return {
      ...response,
      data: response.data.map((row) => {
        const code = row.distributor_code ?? row.distributer_code ?? row.d_code ?? row.D_code ?? row.distributor_name
        const maxTimestamp = maxByDistributor.get(code)
        return maxTimestamp ? { ...row, scraped_at: maxTimestamp } : row
      }),
    }
  },
  getPartStockSummary: async (mpn, start = null, end = null) => {
    const v2 = await supabase.rpc('get_part_stock_summary_v2', { p_mpn: mpn, p_start: start, p_end: end })
    if (!v2.error && v2.data) return v2
    const legacy = await supabase.rpc('get_part_stock_summary', { p_mpn: mpn, p_start: start, p_end: end })
    if (!legacy.error && legacy.data) return legacy

    // Last-resort client aggregation supports deployments where only the
    // stock table is readable but the summary RPC has not been installed.
    const raw = await supabase.from('stock').select('*').eq('mpn', mpn)
    if (!raw.error && Array.isArray(raw.data)) {
      const inRange = raw.data.filter((row) => {
        const day = row?.scraped_at ? new Date(row.scraped_at).toISOString().slice(0, 10) : null
        return (!start || (day && day >= start)) && (!end || (day && day <= end))
      })
      const number = (row, ...keys) => Number(keys.map((key) => row?.[key]).find((value) => value !== undefined && value !== null))
      const stock = inRange.map((row) => number(row, 'Current_Stock', 'current_stock')).filter(Number.isFinite)
      const prices = inRange.map((row) => number(row, 'Unit_Price', 'unit_price')).filter(Number.isFinite)
      const codes = new Set(inRange.map((row) => row?.distributer_code ?? row?.distributor_code).filter(Boolean))
      return { data: [{ total_stock: stock.reduce((sum, value) => sum + value, 0), supplier_count: codes.size, lowest_price: prices.length ? Math.min(...prices) : null, highest_price: prices.length ? Math.max(...prices) : null, avg_price: prices.length ? prices.reduce((sum, value) => sum + value, 0) / prices.length : null }], error: null }
    }
    return { data: null, error: v2.error ?? legacy.error ?? raw.error }
  },
  // Full distributer record for the click-to-expand modal on Part Details —
  // matches get_distributor_details(p_distributor_code) in
  // sql/07_part_details_distributor_patch.sql.
  getDistributorDetails: (distributorCode) =>
    supabase.rpc('get_distributor_details', { p_distributor_code: distributorCode }),
  // Full distributor directory — matches get_all_distributors(p_search, p_limit, p_offset)
  // in sql/08_distributors_page.sql.
  getAllDistributors: ({ search = null, limit = 100, offset = 0 } = {}) =>
    supabase.rpc('get_all_distributors', { p_search: search, p_limit: limit, p_offset: offset }),

  // Inventory records screen
  // Matches get_inventory_records(p_warehouse_id, p_start, p_end, p_limit, p_offset)
  getInventoryRecords: ({ warehouseId = null, start = null, end = null, limit = 100, offset = 0 } = {}) =>
    supabase.rpc('get_inventory_records', {
      p_warehouse_id: warehouseId,
      p_start: start,
      p_end: end,
      p_limit: limit,
      p_offset: offset,
    }),
  getInventoryKpis: (start = null, end = null) =>
    supabase.rpc('get_inventory_kpis', { p_start: start, p_end: end }),
  getInventoryForecast: (inventoryId) =>
    supabase.rpc('get_inventory_forecast', { p_inventory_id: inventoryId }),

  // Compliance / Manufacturer & Distributor risk
  getComplianceSummary: () => supabase.rpc('get_compliance_summary'),
  getManufacturerRisk: (limit = 50) => supabase.rpc('get_manufacturer_risk', { p_limit: limit }),
  getDistributorRisk: (limit = 50) => supabase.rpc('get_distributor_risk', { p_limit: limit }),

  // News / events screen
  // Matches get_recent_events(p_severity_min, p_limit, p_start, p_end)
  // Matches get_recent_events(p_severity_min, p_limit, p_start, p_end, p_search)
  getRecentEvents: ({ severityMin = 0, limit = 50, start = null, end = null, search = null } = {}) =>
    supabase.rpc('get_recent_events', {
      p_severity_min: severityMin,
      p_limit: limit,
      p_start: start,
      p_end: end,
      p_search: search,
    }),
  // Matches get_news_stats(p_start, p_end) — Events / Avg Severity / Peak Severity / AI Analysis KPIs
  getNewsStats: (start = null, end = null) => supabase.rpc('get_news_stats', { p_start: start, p_end: end }),
  // Matches get_event_details(p_event_id) — powers the click-through modal
  getEventDetails: (eventId) => supabase.rpc('get_event_details', { p_event_id: eventId }),
  // Matches get_event_articles(p_event_id) — source articles for that modal
  getEventArticles: (eventId) => supabase.rpc('get_event_articles', { p_event_id: eventId }),
  // Matches get_event_location_exposure(p_event_id, p_limit) — real
  // manufacturers/distributors/parts from YOUR database that share
  // geography with this event, as opposed to AI-extracted entity names.
  getEventLocationExposure: (eventId, limit = 20) =>
    supabase.rpc('get_event_location_exposure', { p_event_id: eventId, p_limit: limit }),
  // Real resolved supply-chain links for one event — mirrors the Python
  // pipeline's link_names()/finalize_supply_chain_links() logic, reading
  // straight from risk_events.supply_chain_links (with linked_entities as
  // fallback), rather than re-deriving exposure via a fresh join.
  // Matches get_event_supply_chain(p_event_id) in sql/11_event_supply_chain.sql.
  getEventSupplyChain: (eventId) => supabase.rpc('get_event_supply_chain', { p_event_id: eventId }),
  // Matches get_recent_alerts(p_limit, p_start, p_end)
  getRecentAlerts: (limit = 50, start = null, end = null) =>
    supabase.rpc('get_recent_alerts', { p_limit: limit, p_start: start, p_end: end }),

  // Reports screen — unified feed across inventory_root_cause,
  // inventory_recommendation, part_root_cause, and part_recommendation.
  // Matches get_reports(p_limit, p_start, p_end) in sql/17.
  getReports: async (limit = 1000000, start = null, end = null) => {
    // Inventory and part reports are intentionally requested separately.
    // A legacy get_reports overload can otherwise return only part rows.
    const [inventory, parts] = await Promise.all([
      supabase.rpc('get_inventory_reports', { p_limit: limit, p_start: start, p_end: end }),
      supabase.rpc('get_part_reports', { p_limit: limit, p_start: start, p_end: end }),
    ])
    const inventoryRows = Array.isArray(inventory.data) ? inventory.data : inventory.data ? [inventory.data] : []
    const partRows = Array.isArray(parts.data) ? parts.data : parts.data ? [parts.data] : []
    let rows = [...inventoryRows, ...partRows]
      .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))

    // Some deployed report functions return the level but not the numeric
    // score. Enrich each row from the latest stock_risk record by MPN.
    const mpns = [...new Set(rows.map((row) => row.mpn).filter((mpn) => mpn && mpn !== 'Unknown'))]
    if (mpns.length > 0) {
      const riskResult = await supabase.from('stock_risk').select('*').in('mpn', mpns)
      if (!riskResult.error && Array.isArray(riskResult.data)) {
        const latestRisk = new Map()
        riskResult.data.forEach((risk) => {
          const key = risk?.mpn
          const value = risk?.Final_Market_Risk_Score
            ?? risk?.final_market_risk_score
            ?? risk?.['Final Market Risk Score']
            ?? risk?.risk_score
          const score = Number(value)
          if (!key || !Number.isFinite(score)) return
          const date = risk?.Last_Modified_Date ?? risk?.last_modified_date ?? ''
          const previous = latestRisk.get(key)
          if (!previous || String(date) > String(previous.date)) latestRisk.set(key, { score, date })
        })
        rows = rows.map((row) => {
          if (row.risk_score != null) return row
          const risk = latestRisk.get(row.mpn)
          return risk ? { ...row, risk_score: Math.round(risk.score * 10) / 10 } : row
        })
      }
    }

    if (rows.length > 0) return { data: rows, error: null }

    const fallback = await api.getReportRowsFromSourceTables(limit || 1000000, start, end)
    return !fallback.error && (fallback.data ?? []).length > 0
      ? { data: fallback.data, error: null }
      : { data: [], error: inventory.error ?? parts.error ?? fallback.error }
  },

  // Fallback for deployments where the reports RPC migration has not yet
  // been applied. Reads every source record directly and supports both
  // lowercase and legacy quoted timestamp keys.
  getReportRowsFromSourceTables: async (limit = 50, start = null, end = null) => {
    const sources = [
      { table: 'inventory_root_cause', type: 'inventory', kind: 'root' },
      { table: 'inventory_recommendation', type: 'inventory', kind: 'recommendation' },
      { table: 'part_root_cause', type: 'part', kind: 'root' },
      { table: 'part_recommendation', type: 'part', kind: 'recommendation' },
    ]

    const results = await Promise.all(
      sources.map(({ table }) => supabase.from(table).select('*'))
    )
    const readableSources = sources
      .map((source, index) => ({ ...source, result: results[index] }))
      .filter(({ result }) => !result.error)
    const sourceErrors = sources
      .map((source, index) => ({ table: source.table, error: results[index].error }))
      .filter(({ error }) => error)

    // A report is valid when any source table is readable and contains rows.
    // Do not discard part reports because an inventory table is empty (or
    // vice versa). Only return an error when none of the source tables can
    // be read at all.
    if (readableSources.length === 0) {
      const details = sourceErrors.map(({ table, error }) => `${table}: ${error.message}`).join('; ')
      return { data: [], error: new Error(`Cannot read any report source table: ${details}`) }
    }

    const inRange = (value) => {
      if (!value) return false
      const day = String(value).slice(0, 10)
      return (!start || day >= start) && (!end || day <= end)
    }
    const valueOf = (row, ...keys) => keys.map((key) => row?.[key]).find((value) => value !== undefined && value !== null)
    const rows = []

    readableSources.forEach(({ type, kind, result }) => {
      ;(result.data ?? []).forEach((row) => {
        const date = valueOf(row, 'last_modified_date', 'Last_Modified_Date', 'created_at', 'Created_At')
        if ((start || end) && !inRange(date)) return
        const isInventory = type === 'inventory'
        const reportId = valueOf(row, 'id')
        const mpn = valueOf(row, 'mpn', 'MPN')
        const summary = kind === 'root'
          ? valueOf(row, 'executive_summary', 'Executive Summary', 'human_explanation', 'Human Explanation', 'detected_root_causes')
          : valueOf(row, 'final_recommendation', 'Final Recommendation')
        const scoreLabel = isInventory
          ? valueOf(row, 'risk_level', 'Risk Level')
          : kind === 'recommendation'
            ? valueOf(row, 'tier', 'Stock Band')
            : valueOf(row, 'part_category', 'Part Category')
        rows.push({
          report_id: reportId == null ? '' : String(reportId),
          report_type: type,
          mpn: mpn == null ? 'Unknown' : String(mpn),
          summary: summary || (isInventory ? 'Inventory report' : 'Part report'),
          score_label: scoreLabel || 'Unknown',
          risk_score: (() => {
            const raw = valueOf(row, 'risk_score', 'Risk Score', 'part_score', 'Part Score', 'inventory_risk_score')
            const parsed = Number(raw)
            return Number.isFinite(parsed) ? Math.round(parsed) : null
          })(),
          priority: valueOf(
            row,
            'priority', 'Priority',
            'tier', 'Stock Band',
            'risk_level', 'Risk Level',
            'part_category', 'Part Category'
          ) || 'Unknown',
          created_at: date || null,
        })
      })
    })

    rows.sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))

    // Keep both report types visible when one category has many more rows.
    // Fill half the page from parts and half from inventory, then use any
    // remaining capacity from the category that has additional records.
    const partRows = rows.filter((row) => row.report_type === 'part')
    const inventoryRows = rows.filter((row) => row.report_type === 'inventory')
    const partTarget = Math.ceil(limit / 2)
    const inventoryTarget = Math.floor(limit / 2)
    let selected = [
      ...partRows.slice(0, partTarget),
      ...inventoryRows.slice(0, inventoryTarget),
    ]
    if (selected.length < limit) {
      const selectedKeys = new Set(selected.map((row) => `${row.report_type}:${row.report_id}:${row.created_at ?? ''}`))
      selected = [
        ...selected,
        ...rows.filter((row) => !selectedKeys.has(`${row.report_type}:${row.report_id}:${row.created_at ?? ''}`)),
      ].slice(0, limit)
    }
    selected.sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))

    return {
      data: selected,
      // Partial source errors are intentionally not fatal when at least one
      // source table returned readable report rows.
      error: rows.length === 0 && sourceErrors.length === sources.length
        ? new Error(sourceErrors.map(({ table, error }) => `${table}: ${error.message}`).join('; '))
        : null,
    }
  },
  // Direct detail fallback. It is used when the RPC is missing, returns
  // no row, or the report list came from a recommendation record.
  getSourceReportDetail: async (type, id) => {
    const isInventory = type === 'inventory'
    const rootTable = isInventory ? 'inventory_root_cause' : 'part_root_cause'
    const recommendationTable = isInventory ? 'inventory_recommendation' : 'part_recommendation'
    const [rootResult, recommendationResult] = await Promise.all([
      supabase.from(rootTable).select('*').eq('id', id).maybeSingle(),
      supabase.from(recommendationTable).select('*').eq('id', id).maybeSingle(),
    ])
    if (rootResult.error && recommendationResult.error) {
      return { data: null, error: new Error(`${rootTable}: ${rootResult.error.message}; ${recommendationTable}: ${recommendationResult.error.message}`) }
    }

    let root = rootResult.data ?? null
    let recommendation = recommendationResult.data ?? null
    const valueOf = (row, ...keys) => keys.map((key) => row?.[key]).find((value) => value !== undefined && value !== null)
    const rootMpn = valueOf(root, 'mpn', 'MPN')
    if (!recommendation && rootMpn) {
      const result = await supabase.from(recommendationTable).select('*').eq('mpn', rootMpn).limit(1).maybeSingle()
      recommendation = result.data ?? null
    }
    const recommendationMpn = valueOf(recommendation, 'mpn', 'MPN')
    if (!root && recommendationMpn) {
      const result = await supabase.from(rootTable).select('*').eq('mpn', recommendationMpn).limit(1).maybeSingle()
      root = result.data ?? null
    }
    if (!root && !recommendation) return { data: null, error: null }

    const date = valueOf(root, 'last_modified_date', 'Last_Modified_Date', 'created_at', 'Created_At') ?? valueOf(recommendation, 'last_modified_date', 'Last_Modified_Date', 'created_at', 'Created_At')
    const mpn = valueOf(root, 'mpn', 'MPN') ?? valueOf(recommendation, 'mpn', 'MPN')
    return {
      data: {
        id: valueOf(root, 'id') ?? valueOf(recommendation, 'id') ?? id,
        'Last_Modified_Date': date,
        'MPN': mpn,
        'Risk Level': valueOf(root, 'risk_level', 'Risk Level') ?? valueOf(recommendation, 'risk_level', 'Risk Level', 'tier'),
        'Stock Band': valueOf(recommendation, 'tier', 'Stock Band'),
        'Part Category': valueOf(root, 'part_category', 'Part Category'),
        'Inventory ID': valueOf(root, 'inventory_id', 'Inventory ID') ?? valueOf(recommendation, 'inventory_id', 'Inventory ID'),
        'Priority': valueOf(root, 'priority', 'Priority') ?? valueOf(recommendation, 'priority', 'Priority'),
        'Executive Summary': valueOf(root, 'executive_summary', 'Executive Summary'),
        'Human Explanation': valueOf(root, 'human_explanation', 'Human Explanation'),
        'Business Impact': valueOf(root, 'business_impact', 'Business Impact'),
        'Root Cause Analysis': valueOf(root, 'detected_root_causes', 'Root Cause Analysis'),
        'Final Recommendation': valueOf(recommendation, 'final_recommendation', 'Final Recommendation'),
        'Requires Human Review': valueOf(recommendation, 'requires_human_review', 'Requires Human Review'),
        'Review Reasons': valueOf(recommendation, 'review_reason', 'review_reasons', 'Review Reasons'),
        'alt_status': valueOf(recommendation, 'alt_status'),
        'alt_pars_score': valueOf(recommendation, 'alt_pars_score'),
        'alt_pars_category': valueOf(recommendation, 'alt_pars_category'),
        'supplier_status': valueOf(recommendation, 'supplier_status'),
        'supplier_supplier': valueOf(recommendation, 'supplier_supplier'),
        'supplier_authorized': valueOf(recommendation, 'supplier_authorized'),
        'buy_status': valueOf(recommendation, 'buy_status'),
        'buy_best_price': valueOf(recommendation, 'buy_best_price'),
        'buy_fastest_lead_time': valueOf(recommendation, 'buy_fastest_lead_time'),
        'ltb_status': valueOf(recommendation, 'ltb_status'),
        'ltb_total_extended_value': valueOf(recommendation, 'ltb_total_extended_value'),
        'ltb_total_extended_value_usd': valueOf(recommendation, 'ltb_total_extended_value_usd'),
        'ltb_total_units_available': valueOf(recommendation, 'ltb_total_units_available'),
        'ltb_n_offers_summed': valueOf(recommendation, 'ltb_n_offers_summed'),
      },
      error: null,
    }
  },

  // Full JSONB report for one report. Fall back to the source tables when
  // the RPC is unavailable or cannot resolve a recommendation record.
  getInventoryReport: async (id, mpn = null) => {
    // Use the exact database detail function first. It merges the selected
    // root-cause row with its related recommendation row.
    const rpc = await supabase.rpc('get_inventory_report_v2', { p_id: String(id), p_mpn: mpn })
    const rpcData = Array.isArray(rpc.data) ? rpc.data[0] : rpc.data
    if (!rpc.error && rpcData) return { data: rpcData, error: null }

    // Fallback for deployments where the migration has not been installed.
    const tables = ['inventory_recommendation', 'inventory_root_cause']
    const lookups = await Promise.all(tables.flatMap((table) => [
      supabase.from(table).select('*').eq('id', id).maybeSingle(),
      supabase.from(table).select('*').eq('inventory_id', id).maybeSingle(),
      ...(mpn ? [supabase.from(table).select('*').ilike('mpn', String(mpn).trim()).limit(1).maybeSingle()] : []),
    ]))
    const rows = lookups.map((result) => result.data).filter(Boolean)
    if (rows.length > 0) {
      const merged = rows.reduce((acc, row) => ({ ...acc, ...row }), {})
      return { data: merged, error: null }
    }
    return api.getSourceReportDetail('inventory', id)
  },
  getPartReport: async (id) => {
    const rpc = await supabase.rpc('get_part_report', { p_id: id })
    const data = Array.isArray(rpc.data) ? rpc.data[0] : rpc.data
    return data ? { data, error: null } : api.getSourceReportDetail('part', id)
  },

  // PCN Reports — read through SECURITY DEFINER RPCs first so RLS cannot
  // silently turn an existing pcn table into an empty feed.
  getPcnReports: async () => {
    const rpc = await supabase.rpc('get_pcn_reports')
    if (!rpc.error && Array.isArray(rpc.data)) {
      const data = rpc.data.map((row) => row?.payload ?? row).filter(Boolean)
      return { data, error: null }
    }
    return supabase.from('pcn').select('*')
  },
  getPcnReport: async (id) => {
    const rpc = await supabase.rpc('get_pcn_report', { p_id: String(id) })
    if (!rpc.error && rpc.data) return { data: rpc.data?.payload ?? rpc.data, error: null }
    const candidates = ['id', 'pcn_id', 'PCN_ID', 'pcn_number', 'PCN_Number']
    for (const key of candidates) {
      const result = await supabase.from('pcn').select('*').eq(key, id).maybeSingle()
      if (result.data) return result
    }
    return { data: null, error: rpc.error ?? null }
  },

  // Add Data screen — generic upsert helpers (call table inserts directly,
  // RLS + policies should restrict who can write)
  insertRow: (table, row) => supabase.from(table).insert(row).select(),
}
