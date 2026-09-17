-- =====================================================================
-- New tables for the Inventory Root Cause Analysis Engine and the
-- Inventory Recommendation Engine outputs.
-- =====================================================================
-- Designed to match your existing schema conventions:
--   - History-appending, not upsert-in-place. Your other analysis
--     tables (stock_risk, inventory_risk, compliance_risk, part_score)
--     all accumulate a new row per pipeline run and let downstream
--     queries pick "distinct on (...) order by Last_Modified_Date desc"
--     for the latest snapshot. These two follow the same pattern, so
--     the same query style works across your whole schema instead of
--     needing a different strategy for these two tables specifically.
--   - "Last_Modified_Date" (quoted, timestamptz) as the freshness
--     column, same name/case as every other _risk table.
--   - inventory_id as a real foreign key to inventory(inventory_id) --
--     confirmed varchar on both sides from your actual schema, so this
--     is a hard constraint now rather than the soft/unenforced version
--     from before. ON DELETE SET NULL rather than CASCADE: if an
--     inventory row is ever archived/deleted, the historical root-cause
--     explanation for it is still worth keeping (it's an audit record
--     of what the engine concluded at the time), it just loses its
--     live link back to a row that no longer exists.
--   - mpn as a foreign key to parts(mpn). NOTE: this requires
--     parts.mpn to have a UNIQUE constraint -- every function in this
--     project joins to parts via mpn as if it's unique, but that's
--     never been explicitly confirmed (only parts.id was confirmed as
--     the actual primary key). If this line errors with something like
--     "there is no unique constraint matching given keys for referenced
--     table", either add one first --
--       alter table parts add constraint parts_mpn_unique unique (mpn);
--     -- or just drop "references parts(mpn) on delete set null" from
--     both mpn columns below and keep them as plain text columns.
-- =====================================================================

create table if not exists inventory_root_cause (
  id bigint generated always as identity primary key,
  inventory_id varchar references inventory(inventory_id) on delete set null,
  mpn text references parts(mpn) on delete set null,
  risk_score numeric,
  risk_level text,
  priority text,
  detected_root_causes text,
  human_explanation text,
  business_impact text,
  executive_summary text,
  total_financial_exposure numeric,
  recommendations text,
  llm_polished boolean default false,
  "Last_Modified_Date" timestamptz not null default now()
);

create index if not exists idx_inventory_root_cause_inventory_id on inventory_root_cause (inventory_id);
create index if not exists idx_inventory_root_cause_mpn on inventory_root_cause (mpn);
create index if not exists idx_inventory_root_cause_risk_level on inventory_root_cause (risk_level);
create index if not exists idx_inventory_root_cause_last_modified on inventory_root_cause ("Last_Modified_Date" desc);


create table if not exists inventory_recommendation (
  id bigint generated always as identity primary key,
  inventory_id varchar references inventory(inventory_id) on delete set null,
  mpn text references parts(mpn) on delete set null,
  risk_level text,
  priority text,
  route text,
  final_recommendation text,

  -- Alternative-sourcing sub-analysis
  alt_status text,
  alt_pars_score numeric,
  alt_pars_category text,
  alt_n_real_alternatives integer,
  alt_confidence text,
  alt_reason text,

  -- Supplier/distributor sub-analysis
  supplier_status text,
  supplier_supplier text,
  supplier_authorized boolean,
  supplier_distributor_risk_score numeric,
  supplier_n_options integer,
  supplier_has_authorized_option boolean,

  -- Buy/purchasing sub-analysis. jsonb, not separate scalar columns --
  -- these are naturally small structured objects (a single best offer,
  -- a single fastest-lead-time offer), and jsonb is already how your
  -- schema handles this shape of data elsewhere (risk_events.linked_entities,
  -- risk_events.provenance, alert_matches.match_metadata).
  buy_status text,
  buy_best_price jsonb,
  buy_fastest_lead_time jsonb,
  buy_n_in_stock_offers integer,

  "Last_Modified_Date" timestamptz not null default now()
);

create index if not exists idx_inventory_recommendation_inventory_id on inventory_recommendation (inventory_id);
create index if not exists idx_inventory_recommendation_mpn on inventory_recommendation (mpn);
create index if not exists idx_inventory_recommendation_route on inventory_recommendation (route);
create index if not exists idx_inventory_recommendation_last_modified on inventory_recommendation ("Last_Modified_Date" desc);

-- GIN indexes for querying inside the jsonb columns (e.g. "find every
-- recommendation whose best price came from a specific distributor").
create index if not exists idx_inventory_recommendation_buy_best_price on inventory_recommendation using gin (buy_best_price);
create index if not exists idx_inventory_recommendation_buy_fastest_lead on inventory_recommendation using gin (buy_fastest_lead_time);
