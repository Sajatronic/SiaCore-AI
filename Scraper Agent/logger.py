"""
logger.py
---------
مسؤول عن تسجيل كل عملية تشغيل للـ Agent في جدول public.agent_logs.

هيكل الجدول الفعلي (كما أكّده صاحب المشروع):
    id, run_timestamp (timestamptz), source_name, records_fetched,
    records_updated, status, error_message, records_skipped

بما أن الجدول مصمَّم كـ"سجل ملخّص لكل تشغيل" (صف واحد لكل run) وليس سجل
أحداث تفصيلية، فالمنطق هنا هو:
  1. عند بدء التشغيل: إنشاء صف واحد بحالة status='running'.
  2. أثناء التشغيل: كل شيء (معلومات، تحذيرات، أخطاء) يُطبع على الطرفية
     فقط، ويُجمَّع داخلياً في عدادات وقائمة رسائل.
  3. عند الانتهاء (finish): تحديث نفس الصف بالنتائج النهائية
     (records_fetched, records_updated, records_skipped, status, error_message).

هذا يعطي رؤية حتى أثناء تشغيل طويل (تقدر تشوف status='running' في القاعدة)،
مع الحفاظ على صف واحد نظيف لكل تشغيل بدل إغراق الجدول بآلاف الصفوف.
"""

import datetime as dt
import logging
from typing import Any, Optional

from supabase import Client

# لوجينج محلي على الطرفية (مفيد أثناء التطوير والتشغيل اليدوي)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
console = logging.getLogger("nexusflow")


class AgentLogger:
    def __init__(self, supabase: Client, table_name: str, run_type: str = "manual"):
        self.supabase = supabase
        self.table_name = table_name
        self.run_type = run_type  # "manual" أو "scheduled" -> يُدمج داخل source_name
        self.started_at = dt.datetime.utcnow()

        # عدادات تُجمَّع أثناء التشغيل ثم تُكتب في نهاية التشغيل
        self.summary = {
            "parts_processed": 0,       # -> records_fetched
            "stock_rows_upserted": 0,   # -> records_updated
            "distributors_created": 0,  # (تفصيلي، يُذكر في error_message عند الحاجة)
            "distributors_matched": 0,  # (تفصيلي)
            "distributors_needs_review": 0,  # -> records_skipped
            "errors": 0,
        }
        self._messages: list[str] = []  # نصوص الأخطاء/التحذيرات المهمة فقط

        self._row_id: Optional[int] = self._create_running_row()

    def _create_running_row(self) -> Optional[int]:
        try:
            resp = (
                self.supabase.table(self.table_name)
                .insert(
                    {
                        "run_timestamp": self.started_at.isoformat(),
                        "source_name": f"Nexar API ({self.run_type})",
                        "status": "running",
                        "records_fetched": 0,
                        "records_updated": 0,
                        "records_skipped": 0,
                    }
                )
                .execute()
            )
            if resp.data:
                return resp.data[0]["id"]
        except Exception as exc:
            console.warning(f"تعذّر إنشاء صف بدء التشغيل في agent_logs: {exc}")
        return None

    # -----------------------------------------------------------------
    # واجهات تسجيل بسيطة (طرفية فقط أثناء التشغيل)
    # -----------------------------------------------------------------
    def info(self, message: str, **extra: Any) -> None:
        console.info(message)

    def warning(self, message: str, **extra: Any) -> None:
        console.warning(message)
        self._messages.append(f"[WARNING] {message}")

    def error(self, message: str, **extra: Any) -> None:
        console.error(message)
        self.summary["errors"] += 1
        self._messages.append(f"[ERROR] {message}")

    def needs_review(self, distributor_name: str, reason: str) -> None:
        """يُستدعى عندما يجد الـ Resolver حالة غامضة يجب ألا يقرر فيها تلقائياً."""
        self.summary["distributors_needs_review"] += 1
        msg = f"[NEEDS_REVIEW] موزع يحتاج مراجعة يدوية: {distributor_name} ({reason})"
        console.warning(msg)
        self._messages.append(msg)

    # -----------------------------------------------------------------
    # كتابة النتيجة النهائية (تحديث نفس الصف الذي أُنشئ في البداية)
    # -----------------------------------------------------------------
    def finish(self) -> None:
        records_fetched = self.summary["parts_processed"]
        records_updated = self.summary["stock_rows_upserted"]
        records_skipped = self.summary["distributors_needs_review"]
        errors = self.summary["errors"]

        if errors == 0:
            status = "success"
        elif records_updated > 0:
            status = "partial_success"
        else:
            status = "failed"

        # نلخّص أيضاً إحصائيات الموزعين (مُنشأ/مطابق) داخل error_message
        # كمعلومة إضافية، حتى لو لم تكن "أخطاء" بالمعنى الحرفي، لأنه
        # لا يوجد عمود مخصص لها في الجدول الحالي.
        extra_note = (
            f"موزعون جدد: {self.summary['distributors_created']} | "
            f"موزعون مطابَقون: {self.summary['distributors_matched']}"
        )
        all_messages = self._messages + [extra_note]
        error_message = " | ".join(all_messages) if all_messages else None

        duration = (dt.datetime.utcnow() - self.started_at).total_seconds()
        console.info(
            f"انتهى التشغيل ({self.run_type}) خلال {duration:.1f} ثانية. "
            f"status={status}, fetched={records_fetched}, "
            f"updated={records_updated}, skipped={records_skipped}, errors={errors}"
        )

        update_payload = {
            "records_fetched": records_fetched,
            "records_updated": records_updated,
            "records_skipped": records_skipped,
            "status": status,
            "error_message": error_message,
        }

        try:
            if self._row_id is not None:
                self.supabase.table(self.table_name).update(update_payload).eq(
                    "id", self._row_id
                ).execute()
            else:
                # لو فشل إنشاء الصف في البداية، نحاول إدراج صف نهائي كحل بديل
                update_payload["run_timestamp"] = self.started_at.isoformat()
                update_payload["source_name"] = f"Nexar API ({self.run_type})"
                self.supabase.table(self.table_name).insert(update_payload).execute()
        except Exception as exc:
            console.warning(f"تعذّر تحديث/كتابة صف النتيجة في agent_logs: {exc}")
