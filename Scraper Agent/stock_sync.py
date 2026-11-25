"""
stock_sync.py
--------------
يأخذ استجابة Nexar الخام لقطعة واحدة (mpn)، يمرّ على كل بائع (seller)،
يحلّ (resolve) هوية الموزع عبر DistributorResolver، ثم يعمل Upsert
لصفوف جدول stock بدون تكرار وبدون كتابة NULL فوق بيانات صحيحة قديمة.
"""

import datetime as dt
import re
from typing import Any, Optional

from supabase import Client

from config import config
from distributor_resolver import DistributorResolver
from logger import AgentLogger
from parts_resolver import PartsResolver


class StockSync:
    # ⭐ تطبيع حتمي (deterministic) لمقارنة mpn فقط - وليس للتخزين. بعض
    # المصنّعين/الموزعين (زي Microchip مع ATTINY13ASSUR) بيستخدموا "Other
    # Names" لنفس القطعة الرسمية بفروق شكلية بحتة (شرطة، مسافة، نقطة) -
    # Octopart نفسه بيوثّق ده كـ alias لنفس القطعة، مش قطعة مختلفة. بدون
    # هذا التطبيع، فحص التطابق الصارم (المطلوب لمنع حفظ بيانات قطعة خاطئة)
    # كان يرفض هذه الحالات الصحيحة بالخطأ. هذا لا يزال حتمياً 100% وليس
    # fuzzy matching: نفس الحروف والأرقام بنفس الترتيب بعد إزالة الرموز
    # الفاصلة فقط - لا تخمين ولا تقارب تقريبي. حالات فعلية مختلفة (مثل
    # لواحق التعبئة كـ "-TRAY") لا تتأثر بهذا التطبيع لأنها تضيف حروفاً
    # حقيقية إضافية، فتظل غير متطابقة كما هو مقصود (قرار سابق من صاحب
    # المشروع بعدم معاملتها كنفس القطعة).
    _MPN_NORMALIZE_PATTERN = re.compile(r"[^A-Za-z0-9]")

    @classmethod
    def _normalize_mpn(cls, mpn: str) -> str:
        return cls._MPN_NORMALIZE_PATTERN.sub("", (mpn or "")).upper()

    def __init__(
        self,
        supabase: Client,
        resolver: DistributorResolver,
        parts_resolver: PartsResolver,
        logger: AgentLogger,
    ):
        self.supabase = supabase
        self.resolver = resolver
        self.parts_resolver = parts_resolver
        self.logger = logger

    def sync_part(self, mpn: str, nexar_data: dict[str, Any]) -> None:
        results = (
            nexar_data.get("supSearchMpn", {}).get("results", [])
        )
        if not results:
            self.logger.warning(f"لا توجد نتائج من Nexar للقطعة: {mpn}")
            return

        # ⭐⭐ اكتشاف مهم (بعد فحص استجابة Nexar الخام فعلياً): Nexar لا يرجّع
        # دائماً "قطعة واحدة" في results، بل ممكن يرجّع نفس الـ mpn الحرفي
        # كـ part منفصل أكتر من مرة (على الأغلب بسبب دمج octopart لسجلات
        # بيانات متعددة لنفس رقم القطعة)، وكل نسخة منها معها مجموعة موزعين
        # (sellers) مختلفة تماماً عن الأخرى. الاعتماد على results[0] فقط
        # (كما كان الكود قبل هذا التعديل) كان يُسقط بصمت تام أي موزعين
        # ظهروا في part مطابق آخر غير الأول - حتى لو الـ mpn بتاعه مطابق
        # 100% للمطلوب (بعد التطبيع - راجع _normalize_mpn أعلاه). لذلك:
        # نجمع كل الأجزاء (parts) المطابقة، وندمج قوائم موزعيها معاً قبل
        # المعالجة.
        matching_parts = [
            r["part"] for r in results
            if self._normalize_mpn(r.get("part", {}).get("mpn") or "")
            == self._normalize_mpn(mpn)
        ]

        if not matching_parts:
            returned_mpns = sorted({
                (r.get("part", {}).get("mpn") or "?").strip() for r in results
            })
            self.logger.warning(
                f"عدم تطابق MPN (حتى بعد تجاهل الشرطات/المسافات): المطلوب "
                f"'{mpn}' لكن كل نتائج Nexar كانت لأرقام قطع مختلفة "
                f"{returned_mpns} - تم تجاهل هذه القطعة تجنباً لحفظ بيانات "
                f"قطعة خاطئة."
            )
            return

        if len(matching_parts) > 1:
            self.logger.info(
                f"القطعة {mpn}: Nexar رجّع {len(matching_parts)} نسخ منفصلة "
                f"مطابقة لنفس الـ mpn (بموزعين مختلفين في كل نسخة) - تم دمج "
                f"كل الموزعين من كل النسخ."
            )

        # ⭐ لازم القطعة تكون موجودة في parts أولاً (Foreign Key constraint).
        # نستخدم أول جزء مطابق فقط لبيانات القطعة نفسها (وصف، مصنّع).
        primary_part = matching_parts[0]
        self.parts_resolver.ensure_exists(mpn, primary_part)

        # Lifecycle Status: بما إن Nexar ممكن يرجّع نفس الـ mpn في أكتر من
        # part منفصل، وكل part ممكن يكون عنده قيمة manufacturerlifecyclestatus
        # مختلفة (بيانات متضاربة/غير متزامنة بين نُسخ Octopart)، الاعتماد على
        # "أول قيمة نلاقيها" غير موثوق: ترتيب results من Nexar مش مضمون يفضل
        # ثابت بين استدعاء وتاني، فنفس القطعة ممكن تاخد قيم مختلفة في
        # تشغيلات متتالية بدون أي تغيير حقيقي. بدلاً من ذلك: نجمع كل القيم
        # المرشَّحة من كل الأجزاء المطابقة، ونختار الأحدث فعلياً بالاعتماد
        # على "Last Updated: X ago" اللي Nexar نفسه بيوفّرها - إشارة حقيقية،
        # مش تخميناً. أي تعارض بين القيم يُسجَّل بوضوح في اللوج للمراجعة.
        lifecycle_status = self._extract_freshest_lifecycle_status(matching_parts)

        # دمج موزعي كل الأجزاء المطابقة في قائمة واحدة. لا حاجة لإزالة
        # تكرار الموزعين هنا يدوياً: DistributorResolver أصلاً يطابق بالاسم
        # المطبَّع فيرجع نفس D_code لو تكرر، وقيد stock_unique_offer الجديد
        # في قاعدة البيانات يحمي من أي تكرار على مستوى صفوف stock نفسها.
        all_sellers: list[dict[str, Any]] = []
        for p in matching_parts:
            all_sellers.extend(p.get("sellers", []) or [])

        for seller in all_sellers:
            company = seller.get("company", {})
            if not company.get("name"):
                continue

            match = self.resolver.resolve(
                raw_name=company["name"],
                extra_fields={
                    "D_website": company.get("homepageUrl"),
                    # ⚠️ ملاحظة: هذا هو بلد توفّر العرض حسب استعلام Nexar
                    # (سياق بحث)، وليس بالضرورة مقر الموزع الرئيسي (headquarters).
                    # نستخدمه فقط عند إنشاء موزع جديد كأفضل تقدير متاح.
                    "D_country": seller.get("country"),
                },
                # ⭐ إشارة حقيقية من Nexar لهذا العرض تحديداً، تُستخدم عند
                # إنشاء موزع جديد لاشتقاق D_authorized و D_Type بقيم حقيقية
                # بدل قيمة افتراضية ثابتة كانت تُكتب دايماً بغض النظر عن الواقع.
                is_authorized=seller.get("isAuthorized"),
            )

            if match.was_created:
                self.logger.summary["distributors_created"] += 1
            else:
                self.logger.summary["distributors_matched"] += 1

            is_rfq = seller.get("isRfq", False)

            for offer in seller.get("offers", []):
                self._upsert_offer(
                    mpn=mpn,
                    distributor_code=match.d_code,
                    is_authorized=seller.get("isAuthorized", False),
                    offer=offer,
                    lifecycle_status=lifecycle_status,
                    is_rfq=is_rfq,
                    dealt_with=match.dealt_with,
                )

        self.logger.summary["parts_processed"] += 1

    @classmethod
    def _extract_lifecycle_status(
        cls, part: dict[str, Any]
    ) -> tuple[Optional[str], Optional[float]]:
        """
        ⚠️ تصحيح مهم: Nexar يرجّع حقلين منفصلين تماماً داخل part['specs']،
        مش حقل واحد:
          - shortname == "lifecyclestatus"             -> تصنيف عام موحَّد
            من Octopart نفسه (قيم زي "Production", "NRND", "EOL")
          - shortname == "manufacturerlifecyclestatus"  -> القيمة الخام من
            المصنّع مباشرة، بمصطلحاته الخاصة (قيم زي "ACTIVE", "REL", "PRA")

        بما إن عمود قاعدة البيانات اسمه Manufacturer_Lifecycle_Status ووظيفته
        تحديداً تخزين تصنيف المصنّع الدقيق (وليس تصنيف Octopart العام)، لازم
        نسحب "manufacturerlifecyclestatus" حرفياً، لا "lifecyclestatus".
        (كان فيه خطأ سابق هنا يسحب الحقل العام بالغلط - تم تصحيحه).

        لا يوجد fallback على الحقل العام عمداً: لو المصنّع لم يوفّر تصنيفه
        الخاص عبر Nexar، نُرجع None (NULL) بدل خلط تصنيف عام مكان تصنيف
        دقيق - نفس فلسفة "لا تخمين" المتّبعة في كل الحقول الحساسة بالمشروع
        (lead_time_days، مطابقة الموزعين، مطابقة الـ mpn).

        مثال من Nexar: "ACTIVE (Last Updated: 5 days ago)" -> ("ACTIVE", 120.0)
        """
        for spec in part.get("specs", []) or []:
            shortname = (spec.get("attribute") or {}).get("shortname")
            if shortname == "manufacturerlifecyclestatus":
                display_value = spec.get("displayValue")
                if display_value:
                    value = display_value.split(" (Last Updated")[0].strip()
                    hours_ago = cls._parse_hours_ago(display_value)
                    return value, hours_ago
        return None, None

    # "Last Updated: 5 days ago" / "1 hour ago" / "a year ago" -> عدد الساعات
    # التقريبي المنقضي، لاستخدامه في مقارنة حداثة القيم المتضاربة.
    _LAST_UPDATED_PATTERN = re.compile(
        r"Last Updated:\s*(?:(\d+)|a|an)\s*(hour|day|week|month|year)s?\s*ago",
        re.IGNORECASE,
    )
    _UNIT_TO_HOURS = {
        "hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30, "year": 24 * 365,
    }

    @classmethod
    def _parse_hours_ago(cls, display_value: str) -> Optional[float]:
        match = cls._LAST_UPDATED_PATTERN.search(display_value or "")
        if not match:
            return None
        amount = int(match.group(1)) if match.group(1) else 1  # "a year ago" -> 1
        unit = match.group(2).lower()
        return amount * cls._UNIT_TO_HOURS.get(unit, 24)

    def _extract_freshest_lifecycle_status(
        self, matching_parts: list[dict[str, Any]]
    ) -> Optional[str]:
        """
        يجمع كل قيم manufacturerlifecyclestatus المرشَّحة من كل الأجزاء
        المطابقة، ويختار الأحدث فعلياً بناءً على "Last Updated" الحقيقي من
        Nexar - بدل الاعتماد على ترتيب results غير المضمون. لو القيم كلها
        متطابقة، القرار بديهي. لو فيه تعارض حقيقي، نسجّله بوضوح في اللوج.
        """
        candidates: list[tuple[str, Optional[float]]] = []
        for p in matching_parts:
            value, hours_ago = self._extract_lifecycle_status(p)
            if value:
                candidates.append((value, hours_ago))

        if not candidates:
            return None

        distinct_values = {v for v, _ in candidates}
        if len(distinct_values) > 1:
            self.logger.info(
                f"قيم Manufacturer_Lifecycle_Status متضاربة بين نسخ مختلفة "
                f"لنفس القطعة: {candidates} - تم اختيار الأحدث فعلياً "
                f"(حسب Last Updated من Nexar)."
            )

        # القيم اللي معاها hours_ago معروف تتصدّر (الأقل = الأحدث)، وأي قيمة
        # بدون معلومة تحديث تُعتبر أقل أولوية (تُرسل لآخر الترتيب بـ +inf)
        candidates.sort(key=lambda c: c[1] if c[1] is not None else float("inf"))
        return candidates[0][0]

    def _upsert_offer(
        self,
        mpn: str,
        distributor_code: str,
        is_authorized: bool,
        offer: dict[str, Any],
        lifecycle_status: Optional[str] = None,
        is_rfq: bool = False,
        dealt_with: Optional[str] = None,
    ) -> None:
        """
        كل سطر سعر (price break) في stock هو صف مستقل، لذلك نعمل upsert
        لكل شريحة كمية (price break) على حدة، مع مفتاح فريد منطقي:
        (mpn, distributor_code, Supplier_SKU, Price_Break_Qty).
        """
        lead_time = offer.get("factoryLeadDays")

        # تنظيف SKU أولاً (قبل أي استخدام له في رسائل اللوج أو الحفظ): strip
        # لمنع تكرار وهمي بسبب مسافات زائدة قادمة من Nexar. لو الـ SKU
        # فارغ/غير موجود، نستخدم قيمة صناعية بديلة قائمة على بيانات العرض
        # نفسه (mpn + موزع) بدل NULL - لأن NULL != NULL في SQL، فقيد UNIQUE
        # الجديد (stock_unique_offer) لن يمنع التكرار في هذه الحالة تحديداً
        # لو تُرك السطر NULL.
        raw_sku = offer.get("sku")
        sku = raw_sku.strip() if isinstance(raw_sku, str) else raw_sku
        if not sku:
            sku = f"NOSKU-{mpn}-{distributor_code}"
            self.logger.warning(
                f"العرض من الموزع {distributor_code} للقطعة {mpn} بدون SKU من "
                f"Nexar - تم استخدام قيمة بديلة ({sku}) لضمان عمل قيد التفرّد."
            )

        # ⭐ أقصى تغطية آمنة لـ lead_time_days: لو Nexar نفسه ما رجّعش قيمة،
        # وكان العرض من نوع RFQ (اطلب عرض سعر)، هذا تفسير موثّق من Nexar
        # نفسه لغياب رقم lead time ثابت - وليس نقصاً في الكود. لا نخمّن
        # رقماً بديلاً؛ نتركه NULL ونسجّل تحذيراً واضحاً في اللوج بدل ذلك،
        # لأن أي رقم مخمَّن هنا سيدخل مباشرة في معادلة Lead Time Risk في
        # محرك تسجيل المخاطر (Risk Scoring Engine) ويكسر قابلية تفسيرها.
        if lead_time is None and is_rfq:
            self.logger.warning(
                f"لا يوجد lead_time_days للقطعة {mpn} من الموزع "
                f"{distributor_code} (SKU: {sku}) لأن العرض "
                f"من نوع RFQ - الموزع لا يوفر رقماً ثابتاً، يحتاج طلب عرض سعر. "
                f"تم ترك lead_time_days فارغاً (NULL) بدل تخمين قيمة."
            )
        elif lead_time is None:
            # ⚠️ إصلاح فجوة كانت صامتة: قبل هذا التعديل، أي عرض غير RFQ
            # يرجع منه lead_time = None كان يُحفظ NULL بدون أي أثر في اللوج،
            # مما جعل تتبع أسباب غياب lead time شبه مستحيل (مثال حقيقي:
            # موزع يعرض "Lead time: 8 weeks" على موقعه مباشرة، لكن Nexar
            # API لا يرسل هذه القيمة ضمن حقل factoryLeadDays لنفس العرض -
            # فجوة معروفة في كثير من الـ distributor aggregators، وليست
            # بالضرورة خطأ في كودنا). الآن نسجّل كل حالة NULL غير RFQ
            # كمعلومة (info) حتى نستطيع تمييز "Nexar لم يرسل القيمة" عن
            # "قيمة صحيحة صفر/معروفة".
            self.logger.info(
                f"lead_time_days = NULL للقطعة {mpn} من الموزع "
                f"{distributor_code} (SKU: {sku}) رغم أن العرض ليس RFQ - "
                f"على الأرجح Nexar API لم يرسل factoryLeadDays لهذا العرض "
                f"تحديداً (حتى لو كان الموزع يعرضه على موقعه مباشرة). "
                f"لا نخمّن قيمة بديلة؛ تُترك NULL."
            )

        # ⭐ Is_Preferred_Supplier في stock يُشتق من dealt_with الحقيقي في
        # distributer (نفس الموزع نتعامل معه فعلاً = مفضّل). "Yes" -> True،
        # "No" -> False. لو dealt_with نفسه غير معروف بعد (سجل موزع قديم لسه
        # ما اتعملهاش backfill)، نسيب Is_Preferred_Supplier فارغ (None) بدل
        # افتراض False - نفس فلسفة "لا تخمين" المتّبعة في كل الحقول الحساسة.
        if dealt_with == "Yes":
            is_preferred_supplier: Optional[bool] = True
        elif dealt_with == "No":
            is_preferred_supplier = False
        else:
            is_preferred_supplier = None

        for price_break in offer.get("prices", []) or [{}]:
            qty = price_break.get("quantity")
            unit_price = price_break.get("price")

            # القاعدة: لازم يوجد سعر وكمية محددة معاً، وإلا يُتجاهل العرض
            # بالكامل - حتى لو عنده مخزون متوفر - لأنه بدون سعر أو كمية
            # واضحة لا يمكن اعتباره "شريحة سعر" صالحة للحفظ في stock.
            if qty is None or unit_price is None:
                self.logger.warning(
                    f"تم تجاهل عرض بدون سعر و/أو كمية محددة للقطعة {mpn} "
                    f"من الموزع {distributor_code} (SKU: {sku}, "
                    f"qty={qty}, price={unit_price})"
                )
                continue

            row = {
                "mpn": mpn,
                "distributer_code": distributor_code,
                "Authorized_Dist": "Yes" if is_authorized else "No",
                "Supplier_SKU": sku,
                "Current_Stock": offer.get("inventoryLevel"),
                "moq": offer.get("moq"),
                "packaging": offer.get("packaging"),
                "currency": price_break.get("currency"),
                "Price_Break_Qty": qty,
                "Unit_Price": unit_price,
                "Extended_Price": self._safe_multiply(unit_price, qty),
                "scraped_at": dt.datetime.utcnow().isoformat(),
                "Status": "In Stock" if (offer.get("inventoryLevel") or 0) > 0 else "Out of Stock",
                # العمود القديم Lifecycle_Status لا يُكتب فيه بعد الآن - يبقى
                # كما هو لحين إعادة المسح الشامل. القيمة الجديدة تُوجَّه فقط
                # للعمود الدقيق الجديد المخصص لنظام المخاطر.
                "Manufacturer_Lifecycle_Status": lifecycle_status,
                "product_url": offer.get("clickUrl"),
                "lead_time_days": lead_time,
                "original_source_name": "Nexar API",
                "is_preferred_supplier": is_preferred_supplier,
            }

            # إزالة أي مفتاح قيمته None حتى لا نكتب NULL فوق بيانات قديمة صحيحة
            # (حماية البيانات: القيم المفقودة مؤقتاً من الـ API لا تمسح بيانات
            # قديمة صحيحة كانت مخزّنة من تشغيل سابق).
            clean_row = {k: v for k, v in row.items() if v is not None}

            # Full update to prevent data drift: نعتمد الآن على upsert مباشرة
            # على قيد stock_unique_offer (mpn, distributer_code, Supplier_SKU,
            # Price_Break_Qty) بدل SELECT ثم INSERT/UPDATE يدوياً. هذا التغيير
            # ضروري بعد إضافة القيد الفريد في قاعدة البيانات: منطق
            # select-then-insert القديم كان عرضة لـ race condition بين تشغيلين
            # متزامنين (مثلاً manual + scheduled) - upsert ذرّي (atomic) على
            # مستوى قاعدة البيانات ويحل هذه المشكلة تماماً، ويضمن أيضاً أن كل
            # الحقول المتاحة (سعر، مخزون، lead time، lifecycle، رابط) تُحدَّث
            # معاً دفعة واحدة بدل تحديث جزئي.
            self.supabase.table(config.TABLE_STOCK).upsert(
                clean_row,
                on_conflict="mpn,distributer_code,Supplier_SKU,Price_Break_Qty",
            ).execute()

            self.logger.summary["stock_rows_upserted"] += 1

    @staticmethod
    def _safe_multiply(price, qty):
        try:
            if price is None or qty is None:
                return None
            return round(float(price) * float(qty), 2)
        except (TypeError, ValueError):
            return None