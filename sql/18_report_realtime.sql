-- =====================================================================
-- SiaCore — Realtime setup for new-report notifications
-- =====================================================================
-- useNotifications.js now also listens for INSERTs on inventory_report
-- and part_report to power a bell notification when a new report is
-- generated. Same requirement as sql/13_realtime_setup.sql: a table
-- has to be added to the supabase_realtime publication before
-- Supabase will push its changes to any client.
-- =====================================================================

alter publication supabase_realtime add table inventory_report;
alter publication supabase_realtime add table part_report;

-- If either is already in the publication this errors ("already a
-- member") — safe to ignore for that one table and re-run the rest.
