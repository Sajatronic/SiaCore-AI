-- ============================================================================
-- migration_006.sql
-- NexusFlow Data Agent — تصحيح company_founded_year: تحويل النص الحرفي
-- "Not found" (مش NULL حقيقي) إلى NULL فعلي.
-- ============================================================================
-- ⚠️ قبل التنفيذ: شوف الصفوف المتأثرة أولاً (استعلام قراءة فقط، آمن):
--
--   SELECT D_code, D_Name, company_founded_year
--   FROM distributer
--   WHERE company_founded_year = 'Not found';
-- ============================================================================

UPDATE distributer
SET company_founded_year = NULL
WHERE company_founded_year = 'Not found';

-- ============================================================================
-- بعد التنفيذ: تقدري تعيدي محاولة الاستخراج للصفوف دي (دلوقتي NULL فعلي،
-- فالسكريبت هيحاول تاني):
--   python backfill_distributors.py --apply --scrape-founded-year
-- ============================================================================
