import React, { useEffect, useState } from 'react'
import { supabase, api } from '../lib/supabaseClient.js'
import { CheckCircle2, AlertCircle, Package, Factory, Truck, Warehouse } from 'lucide-react'
import CsvUploader from '../components/CsvUploader.jsx'

// Deliberately minimal for Parts/Manufacturers/Distributors: only the
// fields you'd actually type by hand. Everything else (compliance data,
// risk scores, technical specs, etc.) is enrichment the scraping/risk
// pipeline fills in later. Inventory keeps its full column set since
// those values genuinely do need to be entered per stock record.
//
// Table names (`manufacturers`, `distributor`) and every field's type
// below were cross-checked directly against real ERD screenshots of
// these four tables — not guessed.
//
// Duplicate protection is handled entirely by the database now (see
// sql/15_duplicate_name_guard.sql, sql/27_parts_mpn_unique.sql) — an
// earlier client-side pre-check here was removed after it repeatedly
// produced a false "already exists" result. Errors currently show the
// raw Postgres message (see handleSubmit) rather than a friendly
// paraphrase, specifically so a real constraint violation is
// distinguishable from whatever caused that false positive.
const TABLES = {
  parts: {
    label: 'Parts',
    icon: Package,
    table: 'parts',
    accent: 'from-royal to-violet',
    description: 'A new manufacturer part number, linked to its manufacturer.',
    fields: [
      { name: 'mpn', label: 'MPN', type: 'text', required: true, placeholder: 'e.g. ATTINY13ASSU' },
      { name: 'mfr_id', label: 'Manufacturer', type: 'select-ref', required: true, refTable: 'manufacturers', refValue: 'id', refLabel: 'manufacturer' },
      { name: 'description', label: 'Description', type: 'text', placeholder: 'Optional short description' },
    ],
  },
  manufactures: {
    label: 'Manufacturers',
    icon: Factory,
    table: 'manufacturers',
    accent: 'from-teal to-royal',
    description: 'Just the name — enrichment (compliance, risk, tiering) is filled in by the pipeline.',
    fields: [{ name: 'manufacturer', label: 'Manufacturer Name', type: 'text', required: true, placeholder: 'e.g. Analog Devices' }],
  },
  distributer: {
    label: 'Distributors',
    icon: Truck,
    table: 'distributor',
    accent: 'from-magenta to-royal',
    description: 'Just the name — a distributor code is assigned automatically.',
    fields: [{ name: 'd_name', label: 'Distributor Name', type: 'text', required: true, placeholder: 'e.g. Arrow Electronics' }],
  },
  inventory: {
    label: 'Inventory',
    icon: Warehouse,
    table: 'inventory',
    accent: 'from-violet to-magenta',
    description: 'Full stock record for a part, at a warehouse, sourced from a distributor.',
    fields: [
      { name: 'mpn', label: 'MPN', type: 'select-ref', required: true, refTable: 'parts', refValue: 'mpn', refLabel: 'mpn' },
      { name: 'supplier_id', label: 'Distributor', type: 'select-ref', refTable: 'distributor', refValue: 'd_code', refLabel: 'd_name' },
      { name: 'warehouse_id', label: 'Warehouse', type: 'select-ref', refTable: 'warehouses', refValue: 'warehouse_id', refLabel: 'warehouse_name' },
      { name: 'date', label: 'Date', type: 'date' },
      { name: 'qty_on_hand', label: 'Qty on Hand', type: 'number', required: true },
      { name: 'qty_allocated', label: 'Qty Allocated', type: 'number' },
      { name: 'available_stock', label: 'Available Stock', type: 'number' },
      { name: 'stock_status', label: 'Stock Status', type: 'text' },
      { name: 'product_status', label: 'Product Status', type: 'text' },
      { name: 'reorder_point', label: 'Reorder Point', type: 'text' },
      { name: 'safety_stock', label: 'Safety Stock', type: 'text' },
      { name: 'max_stock', label: 'Max Stock', type: 'text' },
      { name: 'min_stock', label: 'Min Stock', type: 'text' },
      { name: 'unit_cost', label: 'Unit Cost', type: 'number' },
      { name: 'holding_cost', label: 'Holding Cost', type: 'number' },
      { name: 'shortage_cost', label: 'Shortage Cost', type: 'number' },
      { name: 'lead_time_days', label: 'Lead Time (days)', type: 'number' },
      { name: 'lead_time_variability', label: 'Lead Time Variability', type: 'number' },
      { name: 'avg_daily_usage', label: 'Avg Daily Usage', type: 'number' },
      { name: 'avg_weekly_usage', label: 'Avg Weekly Usage', type: 'number' },
      { name: 'avg_monthly_usage', label: 'Avg Monthly Usage', type: 'number' },
      { name: 'demand_variability', label: 'Demand Variability', type: 'number' },
      { name: 'seasonality_factor', label: 'Seasonality Factor', type: 'number' },
      { name: 'forecast_demand', label: 'Forecast Demand', type: 'number' },
      { name: 'demand_category', label: 'Demand Category', type: 'text' },
      { name: 'season', label: 'Season', type: 'text' },
      // FIXED: inventory.promotion_flag is float8 in the real schema —
      // sending the strings 'Yes'/'No' would fail with "invalid input
      // syntax for type double precision" on every submit that touched
      // this field. Now a numeric-valued select instead.
      {
        name: 'promotion_flag',
        label: 'Promotion Flag',
        type: 'select-numeric',
        options: [
          { label: 'No promotion', value: 0 },
          { label: 'Active promotion', value: 1 },
        ],
      },
    ],
  },
}

const TABLE_KEYS = Object.keys(TABLES)

export default function AddData() {
  const [tableKey, setTableKey] = useState(TABLE_KEYS[0])
  const [values, setValues] = useState({})
  const [status, setStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [refOptions, setRefOptions] = useState({})
  const [refError, setRefError] = useState(null)

  const config = TABLES[tableKey]

  useEffect(() => {
    let active = true
    const refFields = config.fields.filter((f) => f.type === 'select-ref')
    if (refFields.length === 0) return
    setRefError(null)
    Promise.all(
      refFields.map((f) =>
        supabase
          .from(f.refTable)
          .select(f.refValue === f.refLabel ? f.refValue : `${f.refValue}, ${f.refLabel}`)
          .order(f.refLabel)
          .limit(500)
      )
    ).then((results) => {
      if (!active) return
      const next = {}
      let firstError = null
      results.forEach((res, i) => {
        const f = refFields[i]
        if (res.error) {
          firstError = firstError ?? `Couldn't load ${f.label} options from "${f.refTable}": ${res.error.message}`
          next[f.name] = []
        } else {
          next[f.name] = res.data ?? []
        }
      })
      setRefOptions((prev) => ({ ...prev, ...next }))
      if (firstError) setRefError(firstError)
    })
    return () => {
      active = false
    }
  }, [tableKey])

  function handleChange(name, val) {
    setValues((v) => ({ ...v, [name]: val }))
  }

  function selectTable(key) {
    setTableKey(key)
    setValues({})
    setStatus(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setStatus(null)

    // NOTE: the client-side pre-check that used to live here (a SELECT
    // before the INSERT) was removed after it repeatedly reported a
    // false "already exists" for a value directly confirmed absent via
    // SQL — the cause was never conclusively identified, and rather
    // than keep guessing at a fix for an unreproducible discrepancy,
    // duplicate protection now relies entirely on the database's own
    // unique constraint (sql/15_duplicate_name_guard.sql for
    // Manufacturers/Distributors; parts.mpn should already be unique-
    // constrained — see sql/27_parts_mpn_unique.sql if not). That's a
    // single source of truth with no separate read step that can go
    // stale. Errors currently surface the raw Postgres message (see
    // below) rather than a friendly paraphrase, so a real constraint
    // violation is distinguishable from an unrelated one.

    const payload = { ...values }
    config.fields.forEach((f) => {
      // 'number' and 'select-numeric' both need to end up as JS numbers,
      // not strings, to match their float8/numeric DB columns.
      if ((f.type === 'number' || f.type === 'select-numeric') && payload[f.name] != null && payload[f.name] !== '') {
        payload[f.name] = Number(payload[f.name])
      }
    })
    const { error } = await api.insertRow(config.table, payload)
    setSubmitting(false)
    if (error) {
      // FIXED: was masking every 23505 (unique_violation) with a
      // generic "already exists" message, assuming it was always the
      // field we expected (e.g. mpn). That's an assumption, not a
      // fact — the real Postgres error/details (surfaced below)
      // include the actual constraint name, which tells us for
      // certain whether it's really mpn, or something else entirely
      // (e.g. the parts.id primary key colliding because the sequence
      // from sql/25 is out of sync with rows inserted by another
      // process). Once this is confirmed to reliably mean "duplicate
      // value in the field the person just typed," this can go back
      // to a friendly paraphrase — until then, showing the real error
      // is more useful than guessing at a nicer one.
      const detail = error.details ? ` (${error.details})` : ''
      setStatus({ ok: false, message: `${error.message}${detail} [code: ${error.code ?? 'unknown'}]` })
    } else {
      setStatus({ ok: true, message: `Row added to ${config.label}.` })
      setValues({})
    }
  }

  return (
    <div className="pt-6 flex flex-col gap-6 max-w-5xl mx-auto">
      <div>
        <h1 className="font-display text-2xl font-bold">Add data to the database</h1>
        <p className="text-secondary text-sm">Choose a table, then fill in just the essentials.</p>
      </div>

      {/* Table picker */}
      <div className="flex flex-wrap items-center gap-3">
        {TABLE_KEYS.map((key) => {
          const { label, icon: Icon, accent } = TABLES[key]
          const active = key === tableKey
          return (
            <button
              key={key}
              onClick={() => selectTable(key)}
              className={`relative flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all duration-200 overflow-hidden ${
                active ? 'text-white shadow-lg shadow-royal/25' : 'surface hover:bg-[var(--bg-surface-2)]'
              }`}
              style={!active ? { border: '1px solid var(--border)' } : undefined}
            >
              {active && <span aria-hidden className={`absolute inset-0 bg-gradient-to-r ${accent}`} />}
              <Icon size={16} className={`relative ${active ? 'text-white' : 'text-secondary'}`} />
              <span className="relative">{label}</span>
            </button>
          )
        })}
      </div>

      <div className={`grid grid-cols-1 gap-6 items-start ${tableKey === 'inventory' ? 'lg:grid-cols-5' : ''}`}>
        {/* Bulk CSV upload — Inventory only. The other tabs each have a
            relational field (Manufacturer, Distributor, MPN) that needs
            validating against its real table row-by-row, which a raw
            CSV import can't guarantee. */}
        {tableKey === 'inventory' && (
          <div className="lg:col-span-2">
            <CsvUploader tableConfig={config} />
          </div>
        )}

        {/* Single-record form */}
        <div className={`surface rounded-2xl overflow-hidden ${tableKey === 'inventory' ? 'lg:col-span-3' : 'max-w-xl'}`}>
          <div className={`h-1.5 bg-gradient-to-r ${config.accent}`} aria-hidden />
          <div className="p-6 flex flex-col gap-6">
            <div className="flex items-start gap-3">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 bg-gradient-to-br ${config.accent} shadow-lg`}>
                <config.icon size={19} className="text-white" />
              </div>
              <div>
                <h2 className="font-display font-semibold text-lg">{config.label}</h2>
                <p className="text-secondary text-xs mt-0.5">{config.description}</p>
                {refError && <p className="text-magenta text-xs mt-1">{refError}</p>}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-5">
                {config.fields.map((f) => (
                  <div key={f.name}>
                    <label className="text-sm text-secondary block mb-1.5">
                      {f.label}
                      {f.required && <span className="text-magenta"> *</span>}
                    </label>
                    {f.type === 'select' ? (
                      <select
                        required={f.required}
                        value={values[f.name] ?? ''}
                        onChange={(e) => handleChange(f.name, e.target.value)}
                        className="surface-2 rounded-lg px-3 py-2.5 text-sm w-full outline-none focus:ring-2 focus:ring-royal transition"
                      >
                        <option value="" disabled>
                          Select…
                        </option>
                        {f.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : f.type === 'select-numeric' ? (
                      <select
                        required={f.required}
                        value={values[f.name] ?? ''}
                        onChange={(e) => handleChange(f.name, e.target.value === '' ? '' : Number(e.target.value))}
                        className="surface-2 rounded-lg px-3 py-2.5 text-sm w-full outline-none focus:ring-2 focus:ring-royal transition"
                      >
                        <option value="" disabled>
                          Select…
                        </option>
                        {f.options.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : f.type === 'select-ref' ? (
                      <select
                        required={f.required}
                        value={values[f.name] ?? ''}
                        onChange={(e) => handleChange(f.name, e.target.value)}
                        className="surface-2 rounded-lg px-3 py-2.5 text-sm w-full outline-none focus:ring-2 focus:ring-royal transition"
                      >
                        <option value="" disabled>
                          {(refOptions[f.name]?.length ?? 0) === 0 ? 'Loading…' : `Select ${f.label}…`}
                        </option>
                        {(refOptions[f.name] ?? []).map((opt) => (
                          <option key={opt[f.refValue]} value={opt[f.refValue]}>
                            {opt[f.refLabel]}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                        required={f.required}
                        placeholder={f.placeholder}
                        value={values[f.name] ?? ''}
                        onChange={(e) => handleChange(f.name, e.target.value)}
                        className="surface-2 rounded-lg px-3 py-2.5 text-sm w-full outline-none focus:ring-2 focus:ring-royal transition placeholder:text-secondary/50"
                      />
                    )}
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-4 pt-1">
                <button
                  type="submit"
                  disabled={submitting}
                  className={`bg-gradient-to-r ${config.accent} text-white rounded-lg px-6 py-2.5 text-sm font-medium hover:opacity-90 hover:shadow-lg hover:shadow-royal/25 transition disabled:opacity-50`}
                >
                  {submitting ? 'Saving…' : `Save to ${config.label}`}
                </button>
                {status && (
                  <div className={`flex items-center gap-2 text-sm ${status.ok ? 'text-teal' : 'text-magenta'}`}>
                    {status.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                    {status.message}
                  </div>
                )}
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
