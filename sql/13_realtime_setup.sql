-- =====================================================================
-- SiaCore — Realtime setup for the notification bell
-- =====================================================================
-- useNotifications.js subscribes to INSERTs on `reports`, `inventory`,
-- and (as of this file) `alert_matches` via Supabase Realtime. None of
-- that works unless these tables are added to the `supabase_realtime`
-- publication — this wasn't in any earlier file despite being
-- referenced in a comment, so the bell likely hasn't been receiving
-- live events at all until this runs.
-- =====================================================================

alter publication supabase_realtime add table reports;
alter publication supabase_realtime add table inventory;
alter publication supabase_realtime add table alert_matches;

-- If a table is already in the publication, the ADD TABLE above will
-- error ("relation is already member of publication") — safe to ignore
-- for that specific table and re-run the rest.
