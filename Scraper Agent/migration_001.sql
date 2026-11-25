-- ============================================================================
-- migration_001.sql
-- NexusFlow Data Agent — تعديلات قاعدة البيانات
-- ============================================================================
-- نفّذ هذا الملف كاملاً دفعة واحدة في Supabase SQL Editor.
-- ملاحظة: نفّذه على بيئة staging/نسخة تجريبية أولاً لو ممكن، خصوصاً بند (أ)
-- لأنه قد يفشل لو كان فيه صفوف مكررة بالفعل في stock (راجع الملاحظة أسفله).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- أ) منع التكرار الهائل: قيد فريد على المفاتيح المنطقية لصفوف stock
-- ----------------------------------------------------------------------------
-- ⚠️ تنبيه مهم: لو كان في stock حالياً صفوف مكررة فعلياً (نفس mpn +
-- distributer_code + Supplier_SKU + Price_Break_Qty)، هذا الأمر سيفشل.
-- نظّف التكرارات أولاً بالاستعلام التالي (اختياري، شغّله يدوياً وتأكد من
-- النتيجة قبل أي حذف):
--
--   SELECT mpn, distributer_code, "Supplier_SKU", "Price_Break_Qty", COUNT(*)
--   FROM stock
--   GROUP BY mpn, distributer_code, "Supplier_SKU", "Price_Break_Qty"
--   HAVING COUNT(*) > 1;
--
ALTER TABLE stock
ADD CONSTRAINT stock_unique_offer
UNIQUE (mpn, distributer_code, "Supplier_SKU", "Price_Break_Qty");

-- ----------------------------------------------------------------------------
-- ب) حل مشكلة دورة الحياة: عمود جديد دقيق لنظام المخاطر
-- ----------------------------------------------------------------------------
-- العمود القديم Lifecycle_Status يبقى كما هو دون تعديل أو حذف، لحين إعادة
-- المسح الشامل (Re-Scan All) والتأكد من امتلاء العمود الجديد بشكل كامل.
ALTER TABLE stock ADD COLUMN "Manufacturer_Lifecycle_Status" TEXT;

-- ----------------------------------------------------------------------------
-- ج) الأمان الحرج: تفعيل Row Level Security
-- ----------------------------------------------------------------------------
-- ملاحظة تشغيلية: الـ Agent يتصل بـ Supabase عبر SUPABASE_SERVICE_KEY
-- (service_role)، والذي يتجاوز RLS تلقائياً بحكم صلاحياته — فلن يتأثر
-- الـ Agent إطلاقاً بهذا التفعيل. الفائدة هنا هي منع أي وصول عام غير
-- مقصود عبر anon key (مثلاً لو استُخدم لاحقاً في واجهة أمامية).
ALTER TABLE stock ENABLE ROW LEVEL SECURITY;
ALTER TABLE distributer ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable all for authenticated users" ON stock
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "Enable all for authenticated users" ON distributer
    FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ============================================================================
-- نهاية migration_001.sql
-- ============================================================================
