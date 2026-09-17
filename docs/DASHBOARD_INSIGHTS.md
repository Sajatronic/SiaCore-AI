# Overview Dashboard — Insight Reference

What every card on the Risk Overview screen means, where its number comes
from, and how to read it when it's empty. Source of truth for the SQL is
`sql/01_stored_procedures.sql`; the frontend wiring is `src/pages/Overview.jsx`
via `src/lib/supabaseClient.js`.

**Reading "No data yet" / "—" / "0" correctly:** after the fixes in this
update, a card shows an empty state for exactly one reason — the table(s)
behind it have no rows. If a query itself fails (bad column name, missing
function, etc.), the card now shows a red **"Couldn't load this: …"**
message with the actual database error instead of pretending the data is
just missing. If you ever see the old blank-empty look again, that's a
genuine data gap — check row counts with `sql/02_diagnostics.sql`.

---

## Database at a Glance (top row)

RPC: `get_database_totals()` — no filters, one flat count per table.

| Card | Table counted | Notes |
|---|---|---|
| Manufacturers | `manufactures` | |
| Distributors | `distributer` | |
| Parts | `parts` | |
| Warehouses | `warehouses` | |
| Orders | `orders` | |
| Inventory Records | `inventory` | |
| Open Risk Events | `risk_events` | only rows where `status <> 'closed'` |
| Active Alerts | `alert_matches` | every row (no status concept yet) |

If any of these read 0, that table has no rows loaded — confirmed directly
by `select count(*) from <table>` in `sql/02_diagnostics.sql`.

---

## Top KPI row

RPC: `get_dashboard_summary(p_start, p_end)` — respects the date filter,
one row of aggregates.

- **Overall Risk Score** — average of `"Distribution_Risk".final_risk_score`
  across the filtered date range. Empty if `Distribution_Risk` has no rows
  in range.
- **Risk trend delta** (small text under the score) — % change between the
  last 30 days' average risk score and the average before that. Needs at
  least some rows on both sides of the 30-day line to be meaningful;
  otherwise shows nothing.
- **Compliant Parts %** — share of rows in `compliance_risk` where
  `"Compliance_Risk_Level" = 'Low'`. This is a percentage of *compliance
  records*, not of `parts` rows directly — if a part has no compliance
  record, it isn't counted either way.
- **non-compliant count** (small text) — rows in `compliance_risk` where
  `hard_stop_flag is true`.
- **Inventory Optimization %** — `100 - average(inventory_kpi.risk_score)`,
  i.e. higher is better. Not date-filtered (there's no date column on
  `inventory_kpi` in the current schema).
- **Tracked SKUs** — distinct `mpn` values in `stock` within the filtered
  range. **new_sku_count** — distinct `mpn` first seen in the last 30 days
  (not affected by the date filter, always "last 30 days" from now).

**Fixed in this update:** this function previously did
`from "Distribution_Risk" dr left join compliance_risk cr on true` — an
unconditional cross join. Mathematically the compliance percentage still
came out right by coincidence (both sides of the ratio scaled by the same
factor), but `non_compliant_count` would have been wildly inflated
(multiplied by however many `Distribution_Risk` rows exist) the moment both
tables have real data at the same time. Rewrote it as two independent
subqueries so the compliance numbers are correct regardless of how many
rows either table has.

---

## Risk Trend (line chart)

RPC: `get_risk_trend_range(p_start, p_end)` — weekly average of
`"Distribution_Risk".final_risk_score`, grouped by week. Same source table
as Overall Risk Score above, so it's empty for the same reason: no rows in
`Distribution_Risk` for the selected range.

---

## Top Risk Categories

RPC: `get_top_risk_categories(p_limit, p_start, p_end)` — groups **open**
`risk_events` (`status <> 'closed'`) by `event_category`, as a % share of
all open events, top 5 by default. Empty if `risk_events` has no rows, or
every row is already `closed`.

---

## Top At-Risk Parts (table)

RPC: `get_part_risk_insights(p_limit, p_start, p_end)` — one row per part,
combining two independent risk signals:

- **Stock Risk** — from `stock."Current_Stock"` in the filtered range:
  `< 100` → High, `< 500` → Medium, else Low.
- **Inventory Risk** — from `inventory → inventory_forecast → inventory_kpi`
  chain: the worst (`max`) `risk_level` and average `risk_score` per part.
- **Part Score** — currently just the average inventory risk score
  (0–100). Doesn't yet blend in compliance or manufacturer risk — see
  "Possible follow-ups" below if you want a fuller composite score.

**Fixed in this update:** the Manufacturer column was showing the raw
`parts.mfr_id` value (e.g. `"19"`) instead of a name, because it wasn't
joined against `manufactures` at all. It now joins `manufactures.id` and
falls back to the raw id only if no matching manufacturer row exists —
which will still happen if the `manufactures` table itself is empty (see
Database at a Glance above).

---

## Database Analysis section

### Open Orders / Avg Supplier On-Time / Avg Order Risk Score / Late Delivery Rate

RPC: `get_order_performance_summary(p_start, p_end)`.
- **Open Orders** — `orders` where `status not in ('Delivered', 'Cancelled')`.
- **Avg Supplier On-Time** — average `orders.supplier_on_time_rate`.
- **Avg Order Risk Score** — average `orders.order_risk_score`.
- **Late Delivery Rate** — % of `order_items` with `late_delivery_flag = 1`,
  joined to `orders` for the date filter.

### Compliance Risk Tiers (donut)

RPC: `get_compliance_breakdown(p_start, p_end)` — groups `compliance_risk`
by risk tier, filtered on `last_modified`.

**Fixed in this update:** this function was querying a column called
`"Compliance_Risk_Tier"`, while the rest of the file (`get_dashboard_summary`,
`get_compliance_summary`) queries `"Compliance_Risk_Level"` for the exact
same table. Only one of those names can be the real column — querying the
wrong one throws a Postgres "column does not exist" error, which the old
frontend code swallowed and showed as "No data yet". Standardized on
`"Compliance_Risk_Level"` everywhere. **Please confirm this is in fact the
real column name in your `compliance_risk` table** — Section 1b of
`sql/02_diagnostics.sql` lists every column on this table so you can check.

### Manufacturer Risk Levels (donut)

RPC: `get_manufacturer_risk_distribution(p_start, p_end)` — groups
`"Manufacturer_Risk"` by `risk_level`, filtered on `"Last_Modified_Date"`.
If this is empty, it's a genuine data gap: the `Manufacturer_Risk` table
has no rows (consistent with Manufacturers reading 0 at the top of the
page too).

### Distributor Risk Levels (donut)

RPC: `get_distributor_risk_distribution(p_start, p_end)` — groups
`distributer` by `relationship_risk_level`, filtered on
`"Last_Modified_Date"`.

### Inventory Health (donut)

RPC: `get_inventory_health_breakdown(p_start, p_end)` — groups `inventory`
by `stock_status`, filtered on `date`.

### Open Events by Severity (donut)

RPC: `get_events_by_severity(p_start, p_end)` — groups **open** `risk_events`
(`status <> 'closed'`) by `severity_signal`, filtered on
`retrieval_timestamp`. Same underlying table as Top Risk Categories and
Open Risk Events above — if all three are empty together, `risk_events`
has no open rows.

### Pipeline Health (latest runs)

RPC: `get_pipeline_health(p_limit, p_start, p_end)` — most recent rows from
`agent_logs` (your scraper/pipeline run log), filtered on `run_timestamp`.

---

## Related fixes made outside this doc's scope

- `get_manufacturer_risk()` (used elsewhere, not on this screen) was
  joining `manufactures."Manufacturer"` (a name) against
  `"Manufacturer_Risk"."M_ID"` (an id) — a name-to-id join that would
  return zero or wrong rows. Changed to join `manufactures.id` to
  `"M_ID"` instead.
- `get_inventory_records()` had a typo'd column reference,
  `"Last_Modified_Data"`, which doesn't exist — fixed to
  `"Last_Modified_Date"`.

---

## Possible follow-ups (not applied, just flagged)

- **Part Score** currently ignores compliance and manufacturer risk
  entirely. If you want it to be a true composite risk score, it would
  need to also pull in `compliance_risk` and `Manufacturer_Risk` per part.
- **risk_score_trend** in `get_dashboard_summary` divides by the
  pre-30-day average risk score; if that's ever exactly 0, the trend
  shows nothing (safely, via `nullif`) rather than a divide-by-zero error.
- Any donut/table above will look "correct but empty" for as long as its
  underlying table is genuinely unpopulated. That's expected while your
  scraping/ETL pipeline is still filling in `Manufacturer_Risk`,
  `compliance_risk`, `Distribution_Risk`, and `risk_events` — run
  `sql/02_diagnostics.sql` any time to check current row counts.
