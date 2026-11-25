"""
checkpoint.py
--------------
حل بسيط لمشكلة "حد الـ API" (rate limit):
بدل معالجة كل القطع في ملف parts.txt دفعة واحدة، الـ Agent يعالج فقط
`config.MAX_PARTS_PER_RUN` قطعة في كل تشغيل، ويحفظ محلياً (في ملف JSON)
آخر نقطة توقف. في التشغيل التالي يكمل من حيث وقف، ولما يوصل لآخر القائمة
يرجع للبداية تلقائياً (دورة كاملة - round robin).

هذا يعني: لو عندك 500 قطعة و MAX_PARTS_PER_RUN=50، تحتاج 10 تشغيلات
(مثلاً 10 مرات يومياً عبر الجدولة) لتغطية كل القطع مرة واحدة، وبعدها
يبدأ الدور من جديد.
"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class Checkpoint:
    last_index: int = 0       # آخر موضع توقفنا عنده في القائمة الكاملة
    total_parts: int = 0      # آخر عدد معروف لإجمالي القطع في الملف
    completed_cycles: int = 0  # كم مرة أكملنا دورة كاملة على كل القطع


class CheckpointManager:
    def __init__(self, checkpoint_file: str):
        self.checkpoint_file = checkpoint_file

    def load(self) -> Checkpoint:
        if not os.path.exists(self.checkpoint_file):
            return Checkpoint()
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Checkpoint(**data)
        except (json.JSONDecodeError, TypeError):
            # ملف تالف أو فارغ -> نبدأ من جديد بدل ما نوقف الـ Agent
            return Checkpoint()

    def save(self, checkpoint: Checkpoint) -> None:
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint.__dict__, f, ensure_ascii=False, indent=2)

    def get_next_batch(self, all_parts: list[str], batch_size: int) -> tuple[list[str], Checkpoint]:
        """
        يرجّع (القطع المطلوب معالجتها في هذا التشغيل، الـ checkpoint المحدَّث
        الذي يجب حفظه بعد نجاح التشغيل).
        """
        cp = self.load()
        total = len(all_parts)

        if total == 0:
            return [], cp

        # لو تغيّر حجم القائمة (أُضيفت/حُذفت قطع)، نحمي الـ index من الخروج
        # عن الحدود عبر modulo بدل ما نوقف الـ Agent بخطأ.
        start = cp.last_index % total
        batch_size = min(batch_size, total)  # لا فائدة من دفعة أكبر من القائمة نفسها

        # نضاعف القائمة مؤقتاً لتبسيط أخذ شريحة قد "تلف" على بداية القائمة
        doubled = all_parts + all_parts
        batch = doubled[start : start + batch_size]

        end_absolute = start + batch_size
        next_index = end_absolute % total
        cycles_completed_now = end_absolute // total  # عدد الدورات الكاملة التي عبرناها في هذا التشغيل

        new_cp = Checkpoint(
            last_index=next_index,
            total_parts=total,
            completed_cycles=cp.completed_cycles + cycles_completed_now,
        )
        return batch, new_cp
