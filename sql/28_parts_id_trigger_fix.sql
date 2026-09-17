-- =====================================================================
-- FIX (for real this time): parts.id collision — sequence drift
-- =====================================================================
-- sql/25_parts_id_default.sql gave parts.id a DEFAULT of nextval() on
-- a sequence seeded once from max(id) at that moment. That works right
-- up until anything ELSE inserts a row into parts with its own id
-- value — almost certainly your scraping/enrichment pipeline, given
-- how this table is described as being populated — at which point the
-- sequence's counter has no way to know the table's real max just
-- moved, and it eventually hands out a value that collides with one
-- of those externally-inserted rows. That's exactly the
-- "parts_id_key" violation you hit — nothing to do with mpn at all.
--
-- Fix: drop the sequence-based default, replace it with a BEFORE
-- INSERT trigger that computes max(id)+1 FRESH from the table every
-- time a row is inserted without an explicit id. This can't drift out
-- of sync the way a cached sequence counter can, because it never
-- caches anything — it always looks at the table's actual current
-- state. (Trade-off: under truly concurrent inserts two requests could
-- theoretically compute the same max+1 — for a low-traffic manual
-- entry form this is an acceptable trade for "never collides with an
-- external pipeline," which was the actual problem here.)
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

alter table parts alter column id drop default;
drop sequence if exists parts_id_seq;

create or replace function trg_set_parts_id()
returns trigger
language plpgsql
as $$
begin
  if new.id is null then
    select coalesce(max(id), 0) + 1 into new.id from parts;
  end if;
  return new;
end;
$$;

drop trigger if exists set_parts_id on parts;
create trigger set_parts_id
  before insert on parts
  for each row
  execute function trg_set_parts_id();
