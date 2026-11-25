"""
main.py
--------
نقطة الدخول الرئيسية لـ NexusFlow Data Agent.

الاستخدام:
  تشغيل يدوي لقطعة واحدة:
      python main.py --mpn LM358 --type manual

  تشغيل يدوي لدفعة (يقرأ كل أرقام القطع مباشرة من جدول parts في Supabase):
      python main.py --batch --type manual

  تشغيل مجدول (يُستدعى من scheduler.py أو من cron):
      python main.py --batch --type scheduled
"""

import argparse
import sys
import time

from supabase import Client, create_client

from checkpoint import Checkpoint, CheckpointManager
from config import config
from distributor_resolver import DistributorResolver
from logger import AgentLogger
from nexar_client import NexarClient
from parts_resolver import TABLE_PARTS, PartsResolver
from stock_sync import StockSync


def get_supabase_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError(
            "متغيرات SUPABASE_URL / SUPABASE_SERVICE_KEY غير موجودة في .env"
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def get_all_mpns_from_parts_table(supabase: Client) -> list[str]:
    """
    يقرأ كل أرقام القطع (mpn) مباشرة من جدول parts في Supabase - هذا هو
    مصدر القطع الوحيد للدفعات الآن (بعد إلغاء الاعتماد على ملف parts.txt
    المحلي). الترتيب حسب id تصاعدياً لضمان أن checkpoint.json (الذي يحفظ
    مجرد رقم index في القائمة) يشير لنفس الموضع النسبي عبر التشغيلات
    المتتالية بأقصى قدر من الثبات.
    """
    response = (
        supabase.table(TABLE_PARTS)
        .select("mpn")
        .order("id")
        .execute()
    )
    return [row["mpn"] for row in (response.data or []) if row.get("mpn")]


def run(mpns: list[str], run_type: str) -> None:
    supabase = get_supabase_client()
    logger = AgentLogger(supabase, config.TABLE_AGENT_LOGS, run_type=run_type)
    logger.info(
        f"بدء تشغيل NexusFlow Agent ({run_type}) لعدد {len(mpns)} قطعة "
        f"(تأخير {config.NEXAR_REQUEST_DELAY_SECONDS}s بين كل طلب لـ Nexar)."
    )

    try:
        nexar = NexarClient()
        resolver = DistributorResolver(supabase, logger)
        parts_resolver = PartsResolver(supabase, logger)
        syncer = StockSync(supabase, resolver, parts_resolver, logger)

        for i, mpn in enumerate(mpns):
            try:
                data = nexar.search_part(mpn)
                syncer.sync_part(mpn, data)
            except Exception as exc:
                logger.error(f"فشل معالجة القطعة {mpn}: {exc}")

            # تأخير بين الطلبات لتجنب تجاوز حد Nexar API، إلا بعد آخر قطعة
            if i < len(mpns) - 1 and config.NEXAR_REQUEST_DELAY_SECONDS > 0:
                time.sleep(config.NEXAR_REQUEST_DELAY_SECONDS)

    finally:
        logger.finish()


def run_batch_with_checkpoint(run_type: str, limit: int | None = None) -> None:
    """
    يُستخدم عند --batch: يقرأ كل أرقام القطع من جدول parts في Supabase،
    لكن يعالج فقط دفعة محدودة (config.MAX_PARTS_PER_RUN أو --limit) بناءً
    على آخر نقطة توقف محفوظة، ثم يحفظ نقطة التوقف الجديدة بعد انتهاء التشغيل.
    """
    supabase = get_supabase_client()
    all_parts = get_all_mpns_from_parts_table(supabase)

    if not all_parts:
        print("خطأ: جدول parts فارغ - لا توجد أي أرقام قطع لمعالجتها.")
        sys.exit(1)

    batch_size = limit or config.MAX_PARTS_PER_RUN
    checkpoint_mgr = CheckpointManager(config.CHECKPOINT_FILE)
    batch, new_cp = checkpoint_mgr.get_next_batch(all_parts, batch_size)

    print(
        f"📦 معالجة دفعة من {len(batch)} قطعة من أصل {len(all_parts)} "
        f"(المصدر: جدول parts، الموضع: {new_cp.last_index}, "
        f"دورات مكتملة سابقاً: {new_cp.completed_cycles})"
    )

    run(batch, run_type=run_type)

    # نحفظ نقطة التوقف بعد انتهاء التشغيل (الأخطاء الجزئية بقطع معينة
    # مسجَّلة أصلاً في agent_logs، فلا داعي لإعادة نفس الدفعة بسببها)
    checkpoint_mgr.save(new_cp)


def main() -> None:
    parser = argparse.ArgumentParser(description="NexusFlow Data Agent")
    parser.add_argument("--mpn", help="رقم قطعة واحد لجلب بياناته (بدون checkpoint)")
    parser.add_argument(
        "--batch", action="store_true",
        help="عالج دفعة من القطع (يُقرأ كل أرقام القطع تلقائياً من جدول "
        "parts في Supabase، ويُعالَج جزء منها فقط حسب checkpoint.json "
        "لتفادي حد Nexar API)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="تجاوز MAX_PARTS_PER_RUN لهذا التشغيل فقط (عدد أقصى للقطع)",
    )
    parser.add_argument(
        "--reset-checkpoint", action="store_true",
        help="تصفير نقطة التوقف والبدء من أول القائمة من جديد",
    )
    parser.add_argument(
        "--type", choices=["manual", "scheduled"], default="manual",
        help="نوع التشغيل (يُسجَّل في agent_logs)",
    )
    args = parser.parse_args()

    if args.reset_checkpoint:
        CheckpointManager(config.CHECKPOINT_FILE).save(Checkpoint())
        print("✅ تم تصفير checkpoint.json")
        if not args.mpn and not args.batch:
            return

    if args.mpn:
        # قطعة واحدة يدوياً: لا داعي لمنطق checkpoint/الدفعات هنا
        run([args.mpn.strip()], run_type=args.type)
        return

    if args.batch:
        run_batch_with_checkpoint(run_type=args.type, limit=args.limit)
        return

    print("خطأ: يجب تحديد --mpn أو --batch")
    sys.exit(1)


if __name__ == "__main__":
    main()