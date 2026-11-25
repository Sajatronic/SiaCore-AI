"""
debug_lead_time.py
--------------------
سكريبت تشخيصي مستقل: يجيب استجابة Nexar الخام (Raw JSON) لقطعة واحدة
ويطبعها كاملة، بدون أي اتصال بـ Supabase وبدون أي كتابة.

⭐ اكتشاف مهم أثناء التشخيص الفعلي: Nexar ممكن يرجّع نفس الـ mpn الحرفي
كـ"part" منفصل أكتر من مرة في نفس الاستجابة، بموزعين مختلفين تماماً في كل
نسخة. لذلك السكريبت يعرض *كل* النتائج (parts) وليس بس أول واحدة، عشان
تقدر تشوف هل فيه موزعين بيضيعوا بسبب الاعتماد على results[0] فقط.

الاستخدام:
    python debug_lead_time.py EQCO30R5.D

    # فلترة على موزع معين بالاسم (بحث جزئي غير حساس لحالة الأحرف):
    python debug_lead_time.py EQCO30R5.D --seller Arrow

    # عرض النتائج المطابقة حرفياً للـ mpn فقط (نفس منطق sync_part الفعلي):
    python debug_lead_time.py EQCO30R5.D --exact-only
"""

import argparse
import json
import sys

from nexar_client import NexarClient


def main() -> None:
    parser = argparse.ArgumentParser(description="تشخيص lead_time لقطعة واحدة من Nexar")
    parser.add_argument("mpn", help="رقم القطعة (MPN) المراد فحصه")
    parser.add_argument(
        "--seller", default=None,
        help="فلترة العرض على اسم موزع معين (بحث جزئي غير حساس لحالة الأحرف)",
    )
    parser.add_argument(
        "--exact-only", action="store_true",
        help="اعرض فقط النتائج (parts) اللي mpn بتاعها يطابق حرفياً - "
        "بالضبط زي منطق sync_part الفعلي بعد التعديل الأخير",
    )
    args = parser.parse_args()

    client = NexarClient()

    print(f"🔎 جاري طلب بيانات القطعة: {args.mpn} ...\n")
    data = client.search_part(args.mpn)

    results = data.get("supSearchMpn", {}).get("results", [])
    if not results:
        print("⚠️ لا توجد نتائج من Nexar لهذه القطعة.")
        sys.exit(1)

    part_entries = results if not args.exact_only else [
        r for r in results
        if (r.get("part", {}).get("mpn") or "").strip() == args.mpn.strip()
    ]

    print(f"عدد النتائج (parts) الكلية المرجَّعة من Nexar: {len(results)}")
    matching_mpns = [
        (r.get("part", {}).get("mpn") or "?").strip() for r in results
    ]
    print(f"أرقام الـ mpn في كل نتيجة بالترتيب: {matching_mpns}\n")

    for idx, result in enumerate(part_entries):
        part = result["part"]
        returned_mpn = part.get("mpn")
        is_exact_match = returned_mpn == args.mpn

        print("#" * 70)
        print(f"النتيجة [{idx}] - mpn: {returned_mpn} "
              f"({'✅ مطابق تماماً' if is_exact_match else '⚠️ غير مطابق حرفياً'})")
        print("#" * 70)

        sellers = part.get("sellers", [])
        print(f"عدد الموزعين (sellers) في هذه النتيجة: {len(sellers)}\n")

        for seller in sellers:
            company_name = (seller.get("company") or {}).get("name", "")
            if args.seller and args.seller.lower() not in company_name.lower():
                continue

            print("=" * 70)
            print(f"الموزع: {company_name}")
            print(f"  isRfq: {seller.get('isRfq')}")
            print(f"  isAuthorized: {seller.get('isAuthorized')}")
            print(f"  country: {seller.get('country')}")

            for offer in seller.get("offers", []):
                print("  " + "-" * 40)
                print(f"  SKU: {offer.get('sku')}")
                print(f"  factoryLeadDays (الحقل الخام من Nexar): {offer.get('factoryLeadDays')!r}")
                print(f"  inventoryLevel: {offer.get('inventoryLevel')}")
                print(f"  moq: {offer.get('moq')}")
                print(f"  packaging: {offer.get('packaging')}")
                print(f"  clickUrl: {offer.get('clickUrl')}")
                print(f"  prices: {offer.get('prices')}")
        print()

    print("\n" + "=" * 70)
    print("📄 الاستجابة الخام كاملة (JSON) - افحصها يدوياً لو محتاج تفاصيل أكتر:\n")
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
