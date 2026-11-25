"""
scheduler.py
-------------
تشغيل دوري للـ Agent (يدعم الجدولة الاحتياطية بجانب التشغيل اليدوي).
يعتمد على APScheduler حتى يعمل كعملية طويلة الأمد (long-running process)
بديلاً عن الاعتماد على cron الخاص بنظام التشغيل - أسهل في النشر
(Docker / Railway / Render) وأسهل في المراقبة.

للتشغيل:
    python scheduler.py
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import run_batch_with_checkpoint


def scheduled_job() -> None:
    # أرقام القطع تُقرأ تلقائياً من جدول parts في Supabase (راجع
    # get_all_mpns_from_parts_table في main.py) - لا حاجة لأي ملف محلي.
    run_batch_with_checkpoint(run_type="scheduled")


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="UTC")

    # مثال: تشغيل كل ساعة (بما أن كل تشغيل يعالج دفعة محدودة فقط عبر
    # checkpoint.json، التشغيل المتكرر هو الطريقة الصحيحة لتغطية كل
    # القطع تدريجياً دون تجاوز حد Nexar API). عدّلها حسب باقتك.
    scheduler.add_job(scheduled_job, CronTrigger(minute=0))  # كل ساعة تماماً

    print("⏰ NexusFlow Scheduler يعمل الآن... (Ctrl+C للإيقاف)")
    scheduler.start()