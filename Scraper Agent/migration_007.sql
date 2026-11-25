-- ============================================================================
-- migration_007.sql
-- NexusFlow Data Agent — إعادة تصفير company_founded_year للموزعين اللي
-- فشل استخراج سنة تأسيسهم بسبب باج حقيقي في الكود (D_website بدون
-- http://‏ أو https:// كان يفشل الطلب تماماً قبل حتى محاولة فحص الصفحة)،
-- مش لأن الموقع فعلاً مالوش المعلومة. الباج اتصلّح في backfill_distributors.py
-- (_ensure_url_scheme) - هذا الملف بس يصفّر الصفوف المتأثرة عشان تتحاول تاني.
-- ============================================================================
-- شوف الصفوف المتأثرة أولاً (قراءة فقط، آمن):
--
--   SELECT D_code, D_Name, D_website, company_founded_year
--   FROM distributer
--   WHERE company_founded_year = 'Not found'
--     AND D_website IS NOT NULL
--     AND D_website NOT ILIKE 'http%';
-- ============================================================================

UPDATE distributer
SET company_founded_year = NULL
WHERE company_founded_year = 'Not found'
  AND D_website IS NOT NULL
  AND D_website NOT ILIKE 'http%';

-- ============================================================================
-- بعد التنفيذ: أعيدي تشغيل الاستخراج (الكود المصحَّح هيتعامل صح مع الروابط
-- الناقصة الـ scheme دلوقتي):
--   python backfill_distributors.py --apply --scrape-founded-year
-- ============================================================================
