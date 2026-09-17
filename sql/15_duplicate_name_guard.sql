-- =====================================================================
-- SiaCore — Duplicate-name guard for Manufacturers and Distributors
-- =====================================================================
-- AddData.jsx now pre-checks for an existing name before inserting and
-- shows a friendly "already exists" message instead of submitting. That
-- check alone has a race condition (two people submitting the same new
-- name at nearly the same moment could both pass the pre-check) — this
-- adds the actual guard at the database level: a case-insensitive
-- unique index, so a genuine duplicate is rejected by Postgres even if
-- the app-level check was bypassed.
--
-- AddData.jsx now inserts Manufacturers/Distributors into `manufacturers`
-- /`distributor` (matching every other file in this project), not the
-- misspelled `manufactures`/`distributer` used in an earlier version of
-- that file — these indexes go on the correctly-spelled tables.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

create unique index if not exists manufacturers_name_unique_ci
  on manufacturers (lower("Manufacturer"));

create unique index if not exists distributor_name_unique_ci
  on distributor (lower("D_Name"));

-- If either of these fails with "could not create unique index —
-- duplicate keys" it means duplicate rows already exist today; find and
-- de-duplicate them first, e.g.:
--   select lower("Manufacturer"), count(*) from manufacturers
--   group by 1 having count(*) > 1;
