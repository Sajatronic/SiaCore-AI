-- =====================================================================
-- get_event_location_exposure — given a risk event, find which of YOUR
-- actual tracked manufacturers, distributors, and parts are exposed
-- based on shared geography with the event.
-- =====================================================================
-- This is deliberately separate from risk_events.linked_entities /
-- supply_chain_links (the jsonb fields an AI pipeline likely populated
-- when the event was scraped) — those are extracted guesses at entity
-- NAMES mentioned in the article text, which may not exactly match how
-- an entity is spelled in your own tables. This function instead does a
-- real join against manufacturers."HQ Country" and distributer.D_country,
-- so every result returned is a verified, currently-tracked row in your
-- database — not a text-matched guess.
--
-- Returns one flat table with an entity_type discriminator column
-- (Manufacturer / Distributor / Part) so the frontend can group client-
-- side into separate sections.
-- =====================================================================
create or replace function get_event_location_exposure(p_event_id uuid, p_limit integer default 20)
returns table (
  entity_type text,
  entity_name text,
  entity_detail text
)
language sql
stable
as $$
  with ev as (
    select geo_country, geo_region
    from risk_events
    where event_id = p_event_id
  ),
  exposed_manufacturers as (
    select
      'Manufacturer'::text as entity_type,
      m."Manufacturer"     as entity_name,
      m."HQ Country"        as entity_detail
    from manufacturers m, ev
    where ev.geo_country is not null
      and m."HQ Country" ilike '%' || ev.geo_country || '%'
  ),
  exposed_distributors as (
    select
      'Distributor'::text as entity_type,
      d."D_Name"           as entity_name,
      d."D_country"        as entity_detail
    from distributer d, ev
    where ev.geo_country is not null
      and d."D_country" ilike '%' || ev.geo_country || '%'
  ),
  exposed_parts as (
    -- Parts sourced from a manufacturer headquartered in the event's
    -- country — the actual components at risk, not just the manufacturer.
    select
      'Part'::text    as entity_type,
      p.mpn           as entity_name,
      m."Manufacturer" as entity_detail
    from parts p
    join manufacturers m on m.id = p.mfr_id
    cross join ev
    where ev.geo_country is not null
      and m."HQ Country" ilike '%' || ev.geo_country || '%'
  )
  select * from exposed_manufacturers
  union all
  select * from exposed_distributors
  union all
  select * from exposed_parts
  limit p_limit;
$$;

grant execute on function get_event_location_exposure(uuid, integer) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
