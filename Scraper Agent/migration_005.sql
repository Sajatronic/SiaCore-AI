-- ============================================================================
-- migration_005.sql
-- NexusFlow Data Agent — إصلاح عمود id في جدول parts (كان NOT NULL بدون
-- قيمة افتراضية تلقائية، فأي INSERT جديد من الكود كان يفشل لأن الكود لا
-- ولا يجب أن يحدد id يدوياً - المفروض تتولد تلقائياً من قاعدة البيانات).
-- ============================================================================
-- ⚠️ تم التأكد فعلياً (عبر information_schema.columns): نوع العمود هو
-- double precision (مش integer/bigint العادي لعمود id)، وis_identity=NO،
-- column_default=NULL. لذلك الحل هنا عبارة عن sequence عادي (integer)
-- يتحول تلقائياً لـ double precision عند التعبئة - بدون تغيير نوع العمود
-- نفسه أو لمس أي صف موجود حالياً، تجنباً لأي مخاطرة غير ضرورية.
-- ============================================================================

-- 1) إنشاء sequence جديد مخصص لهذا العمود
CREATE SEQUENCE IF NOT EXISTS parts_id_seq;

-- 2) ضبط نقطة البداية عشان يكمل من أكبر id موجود حالياً + 1 (يتجنب أي
--    تصادم مع الـ ids الموجودة فعلاً، بما فيها id=169 اللي شفناه في الصورة)
SELECT setval(
    'parts_id_seq',
    COALESCE((SELECT MAX(id) FROM parts), 0)::bigint + 1,
    false
);

-- 3) ربط الـ sequence كقيمة افتراضية للعمود (nextval يرجع bigint، يتحول
--    تلقائياً لـ double precision عند التخزين لأن هذا نوع العمود الفعلي)
ALTER TABLE parts
ALTER COLUMN id SET DEFAULT nextval('parts_id_seq');

-- 4) (اختياري لكن أفضل ممارسة) ربط ملكية الـ sequence بالعمود، عشان لو
--    العمود اتحذف يوماً ما، الـ sequence يتحذف معاه تلقائياً بدل ما يفضل
--    "يتيم" في قاعدة البيانات
ALTER SEQUENCE parts_id_seq OWNED BY parts.id;

