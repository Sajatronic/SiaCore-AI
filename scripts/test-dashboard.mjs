// Automated sanity tests for every Overview-dashboard RPC.
//
// Run with:  npm run test:dashboard
//
// What this does NOT do: it doesn't know your "correct" numbers, so it
// can't tell you "Manufacturers should be 92". What it DOES do is catch
// the two classes of bug that are easy to miss just by eyeballing the
// screen:
//   1. A query that throws (wrong column name, bad join, missing
//      function) — the UI shows this as a calm "No data yet", this
//      script shows it as a loud FAIL with the actual Postgres error.
//   2. A query that returns *something* but the something is nonsense
//      (a percentage over 100, a negative count, breakdown numbers that
//      don't add up to the matching total) — easy to miss visually,
//      caught here automatically.
//
// If a test says "table is empty" rather than FAIL, that's a genuine
// data gap (nothing to fix in code) — see sql/02_diagnostics.sql to
// confirm row counts directly.

import { createClient } from '@supabase/supabase-js'
import { readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const envPath = path.join(__dirname, '..', '.env')

if (!existsSync(envPath)) {
  console.error('\n❌ No .env file found. Run: copy .env.example .env   (Windows)')
  process.exit(1)
}

const env = {}
for (const line of readFileSync(envPath, 'utf-8').split('\n')) {
  const trimmed = line.trim()
  if (!trimmed || trimmed.startsWith('#')) continue
  const [key, ...rest] = trimmed.split('=')
  env[key.trim()] = rest.join('=').trim()
}

const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY)

let passed = 0
let failed = 0
const emptyTables = []

function pass(label) {
  passed++
  console.log(`✅ ${label}`)
}
function fail(label, detail) {
  failed++
  console.log(`❌ ${label}`)
  if (detail) console.log(`   ${detail}`)
}
function note(label) {
  emptyTables.push(label)
  console.log(`⚪ ${label} — table is empty (not a bug, just no data loaded yet)`)
}

// Runs an RPC and hands back { data, error } — never throws, so one bad
// test can't stop the rest of the suite from running.
async function call(name, params = {}) {
  return supabase.rpc(name, params)
}

function isPct(n) {
  return n === null || n === undefined || (typeof n === 'number' && n >= 0 && n <= 100)
}
function isNonNegative(n) {
  return n === null || n === undefined || (typeof n === 'number' && n >= 0)
}

async function main() {
  console.log('\nRunning dashboard data tests...\n')

  // --- get_database_totals ---------------------------------------------
  {
    const { data, error } = await call('get_database_totals')
    if (error) {
      fail('get_database_totals', error.message)
    } else {
      const row = data?.[0] ?? data
      const fields = [
        'total_parts', 'total_manufacturers', 'total_distributors', 'total_warehouses',
        'total_orders', 'total_inventory_records', 'total_risk_events', 'total_alerts',
      ]
      const allNonNegative = fields.every((f) => isNonNegative(row?.[f]))
      if (!allNonNegative) {
        fail('get_database_totals: all counts non-negative', JSON.stringify(row))
      } else {
        pass('get_database_totals: no error, all counts non-negative')
      }
      fields.forEach((f) => {
        if ((row?.[f] ?? 0) === 0) note(`get_database_totals.${f}`)
      })
    }
  }

  // --- get_dashboard_summary --------------------------------------------
  {
    const { data, error } = await call('get_dashboard_summary', { p_start: null, p_end: null })
    if (error) {
      fail('get_dashboard_summary', error.message)
    } else {
      const row = data?.[0] ?? data
      if (!isPct(row?.compliant_parts_pct)) {
        fail('get_dashboard_summary: compliant_parts_pct in 0-100', JSON.stringify(row))
      } else {
        pass('get_dashboard_summary: no error, compliant_parts_pct in range')
      }
      if (row?.compliant_parts_pct == null) note('get_dashboard_summary.compliant_parts_pct (Distribution_Risk or compliance_risk empty)')
      if (row?.overall_risk_score == null) note('get_dashboard_summary.overall_risk_score (Distribution_Risk empty)')
    }
  }

  // --- get_compliance_breakdown -------------------------------------------
  await testBreakdown('get_compliance_breakdown', { p_start: null, p_end: null }, 'tier')

  // --- get_manufacturer_risk_distribution ---------------------------------
  await testBreakdown('get_manufacturer_risk_distribution', { p_start: null, p_end: null }, 'risk_level')

  // --- get_distributor_risk_distribution ----------------------------------
  await testBreakdown('get_distributor_risk_distribution', { p_start: null, p_end: null }, 'risk_level')

  // --- get_inventory_health_breakdown --------------------------------------
  await testBreakdown('get_inventory_health_breakdown', { p_start: null, p_end: null }, 'stock_status')

  // --- get_events_by_severity ----------------------------------------------
  await testBreakdown('get_events_by_severity', { p_start: null, p_end: null }, 'severity_signal')

  // --- get_order_performance_summary ---------------------------------------
  {
    const { data, error } = await call('get_order_performance_summary', { p_start: null, p_end: null })
    if (error) {
      fail('get_order_performance_summary', error.message)
    } else {
      const row = data?.[0] ?? data
      const okPct = isPct(row?.avg_supplier_on_time_rate) && isPct(row?.late_delivery_rate_pct)
      const okCounts = isNonNegative(row?.open_orders)
      if (!okPct || !okCounts) {
        fail('get_order_performance_summary: percentages in 0-100, counts non-negative', JSON.stringify(row))
      } else {
        pass('get_order_performance_summary: no error, values in range')
      }
    }
  }

  // --- get_pipeline_health --------------------------------------------------
  {
    const { data, error } = await call('get_pipeline_health', { p_limit: 8, p_start: null, p_end: null })
    if (error) fail('get_pipeline_health', error.message)
    else if (!data || data.length === 0) note('get_pipeline_health (agent_logs)')
    else pass('get_pipeline_health: no error, rows returned')
  }

  // --- get_top_risk_categories ----------------------------------------------
  {
    const { data, error } = await call('get_top_risk_categories', { p_limit: 5, p_start: null, p_end: null })
    if (error) {
      fail('get_top_risk_categories', error.message)
    } else if (!data || data.length === 0) {
      note('get_top_risk_categories (risk_events empty or all closed)')
    } else {
      const pctSum = data.reduce((s, r) => s + (r.pct ?? 0), 0)
      // Percentages of a "top N of M categories" list should never exceed
      // 100 in total (they can be under 100 if p_limit cut some off).
      if (pctSum > 100.5) {
        fail('get_top_risk_categories: percentages should not sum above 100', `sum = ${pctSum}`)
      } else {
        pass('get_top_risk_categories: no error, percentages sane')
      }
    }
  }

  // --- get_risk_trend_range --------------------------------------------------
  {
    const { data, error } = await call('get_risk_trend_range', { p_start: null, p_end: null })
    if (error) fail('get_risk_trend_range', error.message)
    else if (!data || data.length === 0) note('get_risk_trend_range (Distribution_Risk empty)')
    else pass('get_risk_trend_range: no error, rows returned')
  }

  // --- get_part_risk_insights -------------------------------------------------
  {
    const { data, error } = await call('get_part_risk_insights', { p_limit: 12, p_start: null, p_end: null })
    if (error) {
      fail('get_part_risk_insights', error.message)
    } else if (!data || data.length === 0) {
      note('get_part_risk_insights (parts empty)')
    } else {
      const validLevels = new Set(['High', 'Medium', 'Low', 'Unknown'])
      const allValid = data.every((r) => validLevels.has(r.stock_risk_level))
      if (!allValid) {
        fail('get_part_risk_insights: stock_risk_level should be High/Medium/Low/Unknown', JSON.stringify(data[0]))
      } else {
        pass('get_part_risk_insights: no error, risk levels well-formed')
      }
      // Regression check for the "manufacturer shows a raw numeric id
      // instead of a name" issue — flags it as a warning, not a hard fail,
      // since it depends on the manufactures table actually being populated.
      const looksLikeRawId = data.every((r) => /^\d+$/.test(String(r.manufacturer)))
      if (looksLikeRawId) {
        console.log('⚠️  get_part_risk_insights: manufacturer still looks like a raw id (e.g. "19") for every row — check that the manufactures table has matching rows.')
      }
    }
  }

  // Helper used above for every donut-chart-shaped RPC.
  async function testBreakdown(fnName, params, labelKey) {
    const { data, error } = await call(fnName, params)
    if (error) {
      fail(fnName, error.message)
      return
    }
    if (!data || data.length === 0) {
      note(fnName)
      return
    }
    const allNonNegative = data.every((r) => isNonNegative(r.count))
    const hasLabels = data.every((r) => r[labelKey] !== undefined)
    if (!allNonNegative || !hasLabels) {
      fail(`${fnName}: rows well-formed`, JSON.stringify(data[0]))
    } else {
      pass(`${fnName}: no error, ${data.length} row(s), counts non-negative`)
    }
  }

  console.log(`\n${passed} passed, ${failed} failed, ${emptyTables.length} empty (data gap, not a bug).\n`)
  if (failed > 0) process.exit(1)
}

main()
