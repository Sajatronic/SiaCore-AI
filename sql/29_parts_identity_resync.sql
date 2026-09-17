-- =====================================================================
-- FIX (correct approach): resync parts.id's IDENTITY sequence
-- =====================================================================
-- The error from trying to run sql/28 revealed that parts.id is
-- already a proper GENERATED ... AS IDENTITY column — not a plain
-- column needing a manually-built default or trigger, which is what
-- both sql/25 and sql/28 wrongly assumed. Ignore both of those files;
-- this replaces them.
--
-- An identity column has its own built-in sequence, but that sequence
-- can still drift out of sync with the table's real max(id) if
-- anything ever inserted a row with an EXPLICIT id (bulk import,
-- direct SQL, another tool) — Postgres doesn't automatically bump the
-- identity sequence just because a higher id showed up some other way.
-- That drift is what caused the "parts_id_key" collision, not a
-- missing default.
--
-- pg_get_serial_sequence() finds the real underlying sequence for an
-- identity (or serial) column, and setval() resyncs it to one past the
-- table's actual current max — after this, the normal identity
-- mechanism just works, with no custom trigger needed.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

select setval(
  pg_get_serial_sequence('parts', 'id'),
  (select coalesce(max(id), 0) from parts) + 1,
  false
);

-- Sanity check: last_value should now be higher than parts' current max id.
select schemaname, sequencename, last_value
from pg_sequences
where schemaname || '.' || sequencename = pg_get_serial_sequence('parts', 'id');
