"""
parts_resolver.py
-------------------
جدول `stock` مربوط بعلاقة Foreign Key مع جدول `parts` عبر `mpn`
(القيد fk_stock_parts). لذلك قبل أي إدراج في stock، لازم نتأكد إن
القطعة (mpn) موجودة أصلاً في parts - وإلا ننشئها أولاً بأقل بيانات
كافية من استجابة Nexar.
"""

from typing import Any, Optional

from supabase import Client

from config import config
from logger import AgentLogger

TABLE_PARTS = "parts"


class PartsResolver:
    def __init__(self, supabase: Client, logger: AgentLogger):
        self.supabase = supabase
        self.logger = logger
        self._known_mpns: set[str] = self._load_existing_mpns()

    def _load_existing_mpns(self) -> set[str]:
        response = self.supabase.table(TABLE_PARTS).select("mpn").execute()
        mpns = {row["mpn"] for row in (response.data or []) if row.get("mpn")}
        self.logger.info(f"تم تحميل {len(mpns)} قطعة موجودة مسبقاً في parts.")
        return mpns

    def ensure_exists(self, mpn: str, nexar_part: Optional[dict[str, Any]] = None) -> None:
        """
        يتأكد أن mpn موجود في جدول parts. لو غير موجود، ينشئه بأقل بيانات
        كافية (mpn + وصف مختصر لو متوفر من Nexar). لا يكتب فوق أي بيانات
        موجودة مسبقاً - فقط ينشئ لو غائب تماماً.
        """
        if mpn in self._known_mpns:
            return

        row: dict[str, Any] = {"mpn": mpn}

        if nexar_part:
            description = nexar_part.get("shortDescription")
            if description:
                row["description"] = description

            manufacturer = (nexar_part.get("manufacturer") or {}).get("name")
            if manufacturer:
                # لا يوجد عمود مخصص لاسم المصنّع في هيكل parts الحالي،
                # لذلك نضيفه داخل حقل الوصف كمعلومة إضافية مفيدة إن لم
                # يوجد وصف أصلاً.
                if "description" not in row:
                    row["description"] = f"Manufacturer: {manufacturer}"

        try:
            self.supabase.table(TABLE_PARTS).insert(row).execute()
            self._known_mpns.add(mpn)
            self.logger.info(f"تم إنشاء سجل جديد في parts للقطعة: {mpn}")
        except Exception as exc:
            self.logger.error(
                f"فشل إنشاء سجل parts للقطعة {mpn}: {exc} "
                f"(قد يكون هناك عمود إلزامي (NOT NULL) غير مُعبَّأ في هذا الصف)"
            )
            raise
