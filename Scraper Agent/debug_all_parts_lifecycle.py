"""
debug_all_parts_lifecycle.py
------------------------------
يفحص كل نتائج Nexar لقطعة واحدة، ويطبع كل قيم lifecyclestatus/
manufacturerlifecyclestatus الموجودة في كل نتيجة (سواء مطابقة للـ mpn
حرفياً أو لأ)، بنفس منطق sync_part الفعلي بالظبط.

الاستخدام:
    python debug_all_parts_lifecycle.py MPN_HERE
"""

import sys

from nexar_client import NexarClient


def main() -> None:
    if len(sys.argv) < 2:
        print("الاستخدام: python debug_all_parts_lifecycle.py <MPN>")
        sys.exit(1)

    mpn = sys.argv[1]
    client = NexarClient()

    print(f"جاري السؤال عن: {mpn} ...\n")
    data = client.search_part(mpn)
    results = data["supSearchMpn"]["results"]
    print(f"عدد النتائج الكلي: {len(results)}\n")

    for i, r in enumerate(results):
        part = r["part"]
        returned_mpn = part.get("mpn")
        match_label = "مطابق حرفياً" if returned_mpn == mpn else "غير مطابق"
        print(f"--- نتيجة [{i}] mpn={returned_mpn} ({match_label}) ---")

        found_any = False
        for spec in part.get("specs", []) or []:
            shortname = spec["attribute"]["shortname"]
            if shortname in ("lifecyclestatus", "manufacturerlifecyclestatus"):
                print(f"  {shortname} -> {spec['displayValue']}")
                found_any = True

        if not found_any:
            print("  (لا يوجد أي من الحقلين في specs هذه النتيجة)")
        print()


if __name__ == "__main__":
    main()
