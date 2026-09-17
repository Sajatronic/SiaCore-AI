-- =====================================================================
-- SiaCore — Ensure parts.mpn is actually unique at the DB level
-- =====================================================================
-- AddData.jsx no longer does a client-side "does this already exist"
-- check before inserting — that check was producing an unexplained
-- false positive, and duplicate protection now relies entirely on the
-- database rejecting a real duplicate with a 23505 (unique_violation),
-- which the frontend already handles gracefully.
--
-- This makes sure that constraint actually exists. Per the ERD, mpn
-- has its own key-like icon separate from the `id` primary key,
-- suggesting it's likely already unique-constrained — this is a no-op
-- if so (IF NOT EXISTS), and adds real protection if it somehow isn't.
--   NOTIFY pgrst, 'reload schema';
-- =====================================================================

create unique index if not exists parts_mpn_unique_ci
  on parts (lower(mpn));

-- If this fails with "could not create unique index — duplicate keys",
-- duplicate MPNs already exist in your parts table today; find them:
--   select lower(mpn), count(*) from parts group by 1 having count(*) > 1;
