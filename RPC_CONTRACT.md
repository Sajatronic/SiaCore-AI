# RPC Contract — what the frontend expects from your stored procedures

The frontend never queries tables directly (except the generic insert on the
Add Data page). Every screen calls a named Postgres function through
`supabase.rpc(name, params)` — see `src/lib/supabaseClient.js` for the exact
call sites.

**You don't need to touch any frontend code.** Just create each function
below in your Supabase SQL editor, using your real table/column names, and
returning exactly these column names and types. As long as the signature
matches, the UI will render it.

**Date filtering convention:** most Overview-screen functions take optional
`p_start date, p_end date` parameters, both defaulting to `null`. The
calendar picker on the Overview screen (`DateFilter`) starts with no dates
selected, and the frontend passes `null`/`null` in that state — every one
of these functions treats `null` as "no bound," so leaving the picker empty
returns all data with no date filtering at all. Picking only a start date
(or only an end date) filters on just that side, unbounded on the other.

---

## Overview screen

### `get_database_totals()`
No parameters. Returns **one row** — top-level counts shown as the "Database
at a Glance" row at the very top of the Overview screen:
| column | type |
|---|---|
| total_parts | integer |
| total_manufacturers | integer |
| total_distributors | integer |
| total_warehouses | integer |
| total_orders | integer |
| total_inventory_records | integer |
| total_risk_events | integer |
| total_alerts | integer |

### `get_part_risk_insights(p_limit integer, p_start date, p_end date)`
Ranked watchlist of the highest-risk parts (highest `part_score` first) —
the "which MPN needs attention" table on the Overview screen. Sourced
directly from `stock_risk` (real computed `Risk_Category` /
`Final_Market_Risk_Score` per MPN), joined to `parts`/`manufactures` only
for a readable name.
| column | type |
|---|---|
| mpn | text |
| manufacturer | text |
| stock_risk_level | text |
| part_score | numeric |

### `get_dashboard_summary(p_start date, p_end date)`
No parameters. Returns **one row**:
| column | type |
|---|---|
| overall_risk_score | numeric |
| risk_score_trend | numeric |
| compliant_parts_pct | numeric |
| non_compliant_count | integer |
| optimization_score | numeric |
| tracked_sku_count | integer |
| new_sku_count | integer |

### `get_risk_trend(p_months integer)`
Returns multiple rows, one per month:
| column | type |
|---|---|
| period | text (e.g. `"Jan 26"`) |
| risk_score | numeric |

### `get_risk_trend_range(p_start date, p_end date)`
Used when the user picks a custom range in the calendar date picker
(the "Custom" button in `DateFilter`) instead of a 7D/30D/90D/12M preset.
| column | type |
|---|---|
| period | text (e.g. `"Jul 08"`, weekly buckets recommended) |
| risk_score | numeric |

### `get_top_risk_categories(p_limit integer, p_start date, p_end date)`
| column | type |
|---|---|
| category | text |
| pct | numeric |

---

## Overview screen — database analysis widgets

> **Not currently shown on the Overview page.** The Overview UI was
> simplified down to the 4 highest-value widgets (Database at a Glance,
> the 4 KPI cards, Risk Trend, Top At-Risk Parts). The functions below
> still exist in `sql/01_stored_procedures.sql` and work — they're just
> not called from any page right now. Wire one back in (a new page, or
> back into Overview) whenever you want that detail again; no need to
> recreate the SQL.


These power the lower "analysis" section of the Overview screen and pull
from tables not otherwise summarized above (`compliance_risk`,
`Manufacturer_Risk`, `distributer`, `orders`, `order_items`, `inventory`,
`agent_logs`, `risk_events`).

> **Note on `compliance_risk`:** this table has two different risk columns
> that are easy to mix up — `Compliance_Risk_Tier` is the text bucket
> ('Low'/'Medium'/'High', confirmed via `select "Compliance_Risk_Level",
> pg_typeof(...)` on the real database), while `Compliance_Risk_Level` is
> a numeric score (`bigint`, e.g. 1–5). Every function here compares
> against `Compliance_Risk_Tier`; `Compliance_Risk_Level` isn't used
> anywhere in these functions.

### `get_compliance_breakdown(p_start date, p_end date)`
| column | type |
|---|---|
| tier | text |
| count | integer |

### `get_manufacturer_risk_distribution(p_start date, p_end date)`
| column | type |
|---|---|
| risk_level | text |
| count | integer |
| avg_score | numeric |

### `get_distributor_risk_distribution(p_start date, p_end date)`
| column | type |
|---|---|
| risk_level | text |
| count | integer |
| avg_on_time_rate | numeric |

### `get_order_performance_summary(p_start date, p_end date)`
Returns **one row**:
| column | type |
|---|---|
| open_orders | integer |
| avg_supplier_on_time_rate | numeric |
| avg_order_risk_score | numeric |
| late_delivery_rate_pct | numeric |

### `get_inventory_health_breakdown(p_start date, p_end date)`
| column | type |
|---|---|
| stock_status | text |
| count | integer |

### `get_pipeline_health(p_limit integer, p_start date, p_end date)`
Latest scraper/agent runs from `agent_logs`:
| column | type |
|---|---|
| source_name | text |
| run_timestamp | timestamptz |
| status | text |
| records_fetched | integer |
| records_updated | integer |
| records_skipped | integer |
| error_message | text |

### `get_events_by_severity(p_start date, p_end date)`
| column | type |
|---|---|
| severity_signal | text |
| count | integer |

---

## Parts & Stock screen

### `get_parts_with_stock(p_search text, p_lifecycle text, p_limit integer, p_offset integer)`
`p_search` and `p_lifecycle` may be `null` — treat null as "no filter."
| column | type |
|---|---|
| mpn | text |
| manufacturer | text |
| lifecycle_status | text |
| distributor_code | text |
| current_stock | numeric |
| unit_price | numeric |
| lead_time_days | numeric |

### `get_part_alternatives(p_mpn text)`
| column | type |
|---|---|
| alternative_part | text |
| manufacturer | text |
| relationship | text |
| description | text |

---

## Inventory Records screen

### `get_inventory_records(p_warehouse_id text, p_limit integer, p_offset integer)`
| column | type |
|---|---|
| inventory_id | text |
| mpn | text |
| warehouse_name | text |
| qty_on_hand | numeric |
| available_stock | numeric |
| reorder_point | numeric |
| stock_status | text |

### `get_inventory_kpis()`
Returns **one row**:
| column | type |
|---|---|
| total_qty_on_hand | numeric |
| avg_stock_sufficiency_ratio | numeric |
| avg_lead_time_days | numeric |
| shortage_risk_sku_count | integer |

### `get_inventory_forecast(p_inventory_id text)`
| column | type |
|---|---|
| forecast_date | date |
| forecast_demand | numeric |
| safety_stock | numeric |
| reorder_point | numeric |
| min_stock | numeric |
| max_stock | numeric |

---

## Compliance / Risk (used across screens)

### `get_compliance_summary()`
Returns **one row**:
| column | type |
|---|---|
| total_parts | integer |
| compliant | integer |
| non_compliant | integer |
| unknown | integer |

### `get_manufacturer_risk(p_limit integer)`
| column | type |
|---|---|
| manufacturer | text |
| risk_score | numeric |
| risk_level | text |
| confidence_score | numeric |
| is_acquired | boolean |

### `get_distributor_risk(p_limit integer)`
| column | type |
|---|---|
| distributor_name | text |
| relationship_tier | text |
| relationship_risk_score | numeric |
| relationship_risk_level | text |
| on_time_delivery_rate | numeric |

---

## News & Risk Events screen

### `get_recent_events(p_severity_min integer, p_limit integer)`
| column | type |
|---|---|
| event_id | uuid |
| title | text |
| summary | text |
| severity_signal | text |
| retrieved_at | timestamptz |

### `get_recent_alerts(p_limit integer)`
| column | type |
|---|---|
| id | uuid |
| rule_name | text |
| matched_at | timestamptz |

---

## Reports screen

### `get_reports(p_limit integer)`
| column | type |
|---|---|
| id | text |
| datetime | timestamptz |
| report | text |

---

## Add Data screen

This one does **not** call a stored procedure — it inserts directly into a
table via `supabase.from(table).insert(row)`, defined in
`src/pages/AddData.jsx` (`TABLES`). It currently supports four tables, each
with its full field set from your schema:

- `parts`
- `manufactures`
- `distributer`
- `inventory`

Make sure Row Level Security policies allow `INSERT` on all four tables for
whatever role your anon/publishable key uses, or every save will fail with
an RLS error even though the connection itself is fine.

---

## How to add your own procedure

1. Pick a function from the list above.
2. Write it against your real tables in the Supabase SQL editor:
   ```sql
   create or replace function get_dashboard_summary()
   returns table (
     overall_risk_score numeric,
     risk_score_trend numeric,
     compliant_parts_pct numeric,
     non_compliant_count integer,
     optimization_score numeric,
     tracked_sku_count integer,
     new_sku_count integer
   )
   language sql
   stable
   as $$
     -- your real query here, referencing your actual table/column names
     select ...
   $$;

   grant execute on function get_dashboard_summary() to anon, authenticated;
   ```
3. Run `npm run test:db` — it currently checks `get_dashboard_summary`
   specifically, but you can temporarily edit `scripts/test-connection.mjs`
   to point at whichever function you just wrote.
4. Reload the page for that screen — no frontend changes needed.

`sql/01_stored_procedures.sql` still has full example implementations if you
want a starting point to copy and adapt column names in, rather than writing
each one from scratch.
