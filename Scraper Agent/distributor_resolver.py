"""
distributor_resolver.py
------------------------
⭐ القاعدة الذهبية للمشروع: منع تكرار الموزعين.

المنطق (حسب توجيه صاحب المشروع، بالترتيب):
 1. تطبيع اسم الموزع القادم من Nexar (lowercase, إزالة كلمات ضوضاء، إزالة رموز).
 2. تطبيع كل الأسماء الموجودة مسبقاً في distributer بنفس الطريقة.
 3. مقارنة حتمية (exact match) بين الاسمين المطبَّعين.
    - تطابق تام → استخدام D_code الموجود (لا إنشاء جديد أبداً).
    - عدم تطابق تام → إنشاء موزع جديد بكود جديد وقيم افتراضية آمنة.

هذا نهج حتمي (deterministic) وليس احتمالياً (fuzzy)، بقرار واضح من صاحب المشروع،
لضمان أن تصرفات الـ Agent قابلة للتنبؤ والتدقيق دائماً.
"""

import re
from dataclasses import dataclass
from typing import Optional

import pycountry
from supabase import Client

from config import config
from logger import AgentLogger


def country_code_to_full_name(code: Optional[str]) -> Optional[str]:
    """
    يحوّل كود دولة ISO 3166-1 alpha-2 (زي 'HK', 'CN') لاسمها الكامل
    ('Hong Kong', 'China') باستخدام مكتبة pycountry (بيانات ISO رسمية،
    وليست تخميناً). لو الكود غير معروف أو فاضي، نرجّع القيمة الأصلية كما
    هي بدل ما نخترع اسم دولة - أفضل من فقدان المعلومة بالكامل.
    """
    if not code:
        return None
    country = pycountry.countries.get(alpha_2=code.strip().upper())
    return country.name if country else code


@dataclass
class DistributorMatch:
    d_code: str
    d_name: str
    was_created: bool  # True لو تم إنشاء سجل جديد الآن
    # ⭐ القيمة الحقيقية لعمود dealt_with في distributer وقت هذا الـ resolve
    # ("Yes" / "No" / None لو غير معروف بعد - سجل قديم لسه مالوش قيمة).
    # يُستخدم في stock_sync.py لاشتقاق Is_Preferred_Supplier في stock بدون
    # أي تخمين: dealt_with معروف -> True/False حقيقي، dealt_with مجهول ->
    # نسيب Is_Preferred_Supplier فارغ (NULL) بدل افتراض False.
    dealt_with: Optional[str] = None


def normalize_name(raw_name: str) -> str:
    """
    يحوّل اسم الموزع إلى صيغة قياسية للمقارنة:
      "Digi-Key Electronics, Inc." -> "digikey"
      "DigiKey"                    -> "digikey"
    """
    if not raw_name:
        return ""

    name = raw_name.lower()

    # إزالة كل ما ليس حرفاً أو رقماً أو مسافة (يزيل -, ., ,, & ... إلخ)
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # تقسيم لكلمات وإزالة كلمات الضوضاء (Inc, Ltd, Electronics ...)
    words = [w for w in name.split() if w not in config.NAME_NOISE_WORDS]

    # لصق الكلمات المتبقية بدون مسافات (يوحّد "Digi Key" مع "DigiKey")
    normalized = "".join(words)

    return normalized


class DistributorResolver:
    def __init__(self, supabase: Client, logger: AgentLogger):
        self.supabase = supabase
        self.logger = logger
        self._cache: dict[str, DistributorMatch] = {}
        self._load_existing_distributors()

    def _load_existing_distributors(self) -> None:
        """يحمّل كل الموزعين الموجودين مرة واحدة، ويبني خريطة (اسم مطبّع -> D_code)."""
        response = (
            self.supabase.table(config.TABLE_DISTRIBUTOR)
            .select("D_code, D_Name, dealt_with")
            .execute()
        )
        rows = response.data or []

        self._normalized_index: dict[str, DistributorMatch] = {}
        for row in rows:
            norm = normalize_name(row["D_Name"])
            if norm:
                self._normalized_index[norm] = DistributorMatch(
                    d_code=row["D_code"],
                    d_name=row["D_Name"],
                    was_created=False,
                    dealt_with=row.get("dealt_with"),
                )

        self.logger.info(
            f"تم تحميل {len(self._normalized_index)} موزع موجود مسبقاً للمطابقة."
        )

    def _generate_next_code(self) -> str:
        """يولّد كود موزع جديد تسلسلي مثل SUP029."""
        response = (
            self.supabase.table(config.TABLE_DISTRIBUTOR)
            .select("D_code")
            .execute()
        )
        existing_codes = [row["D_code"] for row in (response.data or [])]

        max_num = 0
        prefix = config.NEW_DISTRIBUTOR_CODE_PREFIX
        for code in existing_codes:
            if code and code.startswith(prefix):
                digits = re.sub(r"\D", "", code[len(prefix):])
                if digits.isdigit():
                    max_num = max(max_num, int(digits))

        next_num = max_num + 1
        return f"{prefix}{next_num:03d}"

    def resolve(
        self,
        raw_name: str,
        extra_fields: Optional[dict] = None,
        is_authorized: Optional[bool] = None,
    ) -> DistributorMatch:
        """
        نقطة الدخول الرئيسية: تعطيه اسم موزع خام من Nexar، يرجّع لك D_code
        الصحيح - سواء كان موجوداً مسبقاً أو تم إنشاؤه للتو.

        is_authorized: حالة `isAuthorized` كما رجعها Nexar لهذا العرض تحديداً
        (إشارة حقيقية موجودة أصلاً في الاستجابة، مش تخميناً) - تُستخدم عند
        إنشاء موزع جديد فقط لاشتقاق D_authorized و D_Type بقيم حقيقية.
        """
        norm = normalize_name(raw_name)

        # تطابق تام حتمي
        if norm in self._normalized_index:
            match = self._normalized_index[norm]
            self.logger.info(
                f"مطابقة موزع: '{raw_name}' -> موجود مسبقاً كـ '{match.d_name}' ({match.d_code})"
            )
            return match

        # لا يوجد تطابق -> إنشاء موزع جديد
        #
        # ملاحظة تصميم مهمة: تم النظر في خيار "قراءة أعمدة الجدول ديناميكياً
        # من information_schema وملء أي عمود غير معروف بالنص 'Unknown'"،
        # لكن تم رفضه عمداً: لو كان العمود من نوع boolean أو integer أو
        # date/timestamp، كتابة نص 'Unknown' فيه سيفشل بخطأ type mismatch
        # ويوقف إنشاء الموزع بالكامل - أي أن الحل المفترض "يحمي" البيانات
        # سيكسرها فعلياً. بدلاً من ذلك: union بين extra_fields (من Nexar،
        # بعد إزالة القيم None حتى لا نكتب NULL فوق افتراضي DB أفضل) و
        # NEW_DISTRIBUTOR_DEFAULTS (المُتحكَّم في أنواع بياناته من config.py).
        # أي عمود جديد يُضاف للجدول مستقبلاً يُفعَّل بإضافته صراحة إلى
        # NEW_DISTRIBUTOR_DEFAULTS في config.py، وليس بتخمين تلقائي.
        new_code = self._generate_next_code()
        clean_extra_fields = {
            k: v for k, v in (extra_fields or {}).items() if v is not None
        }

        # ⭐ تحويل كود الدولة لاسم كامل (بيانات ISO حقيقية، مش تخمين)
        if clean_extra_fields.get("D_country"):
            clean_extra_fields["D_country"] = country_code_to_full_name(
                clean_extra_fields["D_country"]
            )

        # ⭐ D_authorized و D_Type: نشتقهم من isAuthorized الحقيقي القادم من
        # Nexar لهذا العرض، بدل قيمة افتراضية ثابتة كانت تكتب "No" دايماً
        # بغض النظر عن الواقع. لو is_authorized=None (غير معروف)، نسيبهم
        # يعتمدوا على NEW_DISTRIBUTOR_DEFAULTS/NULL بدل تخمين.
        if is_authorized is not None:
            clean_extra_fields["D_authorized"] = "Yes" if is_authorized else "No"
            clean_extra_fields["D_Type"] = (
                "Authorized Distributor" if is_authorized else "Independent Distributor"
            )

        new_row = {
            "D_code": new_code,
            "D_Name": raw_name.strip(),
            **config.NEW_DISTRIBUTOR_DEFAULTS,
            **clean_extra_fields,
        }

        self.supabase.table(config.TABLE_DISTRIBUTOR).insert(new_row).execute()

        match = DistributorMatch(
            d_code=new_code,
            d_name=raw_name,
            was_created=True,
            dealt_with=new_row.get("dealt_with"),
        )
        self._normalized_index[norm] = match  # تحديث الكاش لتفادي إنشاء مكرر بنفس الدفعة

        self.logger.warning(
            f"موزع جديد تم إنشاؤه تلقائياً: '{raw_name}' -> {new_code} "
            f"(الحالة: Pending Review، يحتاج تدقيق بشري)"
        )

        return match
