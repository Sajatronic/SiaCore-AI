-- =====================================================================
-- SiaCore — Patch: real supply-chain-link resolution for one event
-- =====================================================================
-- Mirrors the Python resolution logic (link_names / finalize_supply_
-- chain_links) against the actual stored data instead of re-deriving it:
-- risk_events.supply_chain_links (jsonb) is the finalized payload your
-- pipeline already computed — {components, distributors, manufacturers,
-- affected_manufacturers, locations}, each a list of {name/id, ...}
-- objects. This just extracts display names per category, the same way
-- link_names() does (name, falling back to id; de-duplicated, order
-- preserved), with linked_entities as a fallback source per category if
-- supply_chain_links doesn't have one populated yet — same fallback
-- shape as finalize_supply_chain_links's "if not components and
-- linked_payload.get(...)" pattern.
--
-- Run this, then: NOTIFY pgrst, 'reload schema';
-- =====================================================================

create or replace function get_event_supply_chain(p_event_id uuid)
returns table (
  linked_components text[],
  linked_suppliers text[],
  linked_manufacturers text[],
  affected_manufacturers text[],
  linked_locations text[]
)
language sql
stable
as $$
  with event_row as (
    select
      coalesce(re.supply_chain_links, '{}'::jsonb) as links,
      coalesce(re.linked_entities, '{}'::jsonb)      as linked
    from risk_events re
    where re.event_id = p_event_id
    limit 1
  ),
  -- One extraction per category: pull every element's "name", falling
  -- back to "id" if name is missing (same fallback link_names() does),
  -- de-duplicated while keeping first-seen order.
  extracted as (
    select
      -- components: prefer supply_chain_links.components, fall back to
      -- linked_entities.linked_components if the former is empty —
      -- mirrors "if not components and linked_payload.get('linked_components')".
      (select array_agg(distinct coalesce(elem->>'name', elem->>'id'))
         from jsonb_array_elements(
           case when jsonb_array_length(coalesce(links->'components', '[]'::jsonb)) > 0
                then links->'components'
                else coalesce(linked->'linked_components', '[]'::jsonb)
           end
         ) elem
         where coalesce(elem->>'name', elem->>'id') is not null)              as linked_components,

      (select array_agg(distinct coalesce(elem->>'name', elem->>'id'))
         from jsonb_array_elements(
           case when jsonb_array_length(coalesce(links->'distributors', '[]'::jsonb)) > 0
                then links->'distributors'
                else coalesce(linked->'linked_suppliers', '[]'::jsonb)
           end
         ) elem
         where coalesce(elem->>'name', elem->>'id') is not null)              as linked_suppliers,

      (select array_agg(distinct coalesce(elem->>'name', elem->>'id'))
         from jsonb_array_elements(
           case when jsonb_array_length(coalesce(links->'manufacturers', '[]'::jsonb)) > 0
                then links->'manufacturers'
                else coalesce(linked->'linked_manufacturers', '[]'::jsonb)
           end
         ) elem
         where coalesce(elem->>'name', elem->>'id') is not null)              as linked_manufacturers,

      -- affected_manufacturers is its own list (merge_link_entries in
      -- Python already combined manufacturers + AI-extracted names into
      -- this at write time) — read as stored, no separate fallback.
      (select array_agg(distinct coalesce(elem->>'name', elem->>'id'))
         from jsonb_array_elements(coalesce(links->'affected_manufacturers', '[]'::jsonb)) elem
         where coalesce(elem->>'name', elem->>'id') is not null)              as affected_manufacturers,

      (select array_agg(distinct coalesce(elem->>'name', elem->>'id'))
         from jsonb_array_elements(
           case when jsonb_array_length(coalesce(links->'locations', '[]'::jsonb)) > 0
                then links->'locations'
                else coalesce(linked->'linked_locations', '[]'::jsonb)
           end
         ) elem
         where coalesce(elem->>'name', elem->>'id') is not null)              as linked_locations
    from event_row
  )
  select
    coalesce(linked_components, '{}'),
    coalesce(linked_suppliers, '{}'),
    coalesce(linked_manufacturers, '{}'),
    coalesce(affected_manufacturers, '{}'),
    coalesce(linked_locations, '{}')
  from extracted;
$$;

grant execute on function get_event_supply_chain(uuid) to anon, authenticated;

NOTIFY pgrst, 'reload schema';
