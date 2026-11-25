"""
backfill_distributors.py
--------------------------
سكريبت يُشغَّل مرة واحدة: يحدّث الموزعين الموجودين مسبقاً في distributer
(المُنشأين قبل تصحيحات D_country / D_authorized / D_Type، أو حتى بدون أي
حقول أساسية خالص) بقيم حقيقية.

مصدرين للبيانات، حسب الخيار المستخدَم:

1) الوضع الافتراضي (بدون --refetch-from-nexar): بدون أي طلب جديد لـ Nexar،
   كل القيم مشتقة من بيانات موجودة بالفعل في Supabase:
     - D_country: تحويل كود الدولة المخزَّن (مثلاً "HK") لاسمه الكامل.
     - D_authorized / D_Type: من Authorized_Dist الحقيقي في stock (نفس
       distributer_code) - أصلاً جاي من isAuthorized وقت المزامنة.
     - total_orders_placed: 0 لو NULL (حقيقة فعلية: صفر طلبات لحد الآن).
     - أي حقل تشغيلي أساسي فاضي تماماً (D_status, vetting_status,
       verification_status, data_source, dealt_with): يُملأ بنفس
       NEW_DISTRIBUTOR_DEFAULTS المستخدمة عادةً عند إنشاء موزع جديد -
       لأن موزع بلا أي حالة مسجَّلة أصلاً محتاج نفس معاملة "Pending Review".

2) الوضع الموسَّع (--refetch-from-nexar): لو D_website أو D_country لسه
   فاضيين بعد الخطوة أعلاه (مفيش لهم مصدر داخل Supabase أصلاً)، يسأل Nexar
   عن قطعة واحدة ممثِّلة (mpn) من stock الموزع، يدوّر عن seller بنفس الاسم
   المطبَّع، ويسحب D_website/D_country الحقيقيين منه فقط لو لقى تطابق.

⚠️ لا يكتب فوق أي قيمة موجودة بالفعل تبدو "محدَّثة" (مش افتراضي قديم) -
راجع الشروط داخل الكود لكل حقل.

الاستخدام:
    # عرض التغييرات المقترحة فقط بدون كتابة أي شيء (آمن 100%)
    python backfill_distributors.py

    # التنفيذ الفعلي بعد ما تراجع المخرجات وتتأكد
    python backfill_distributors.py --apply

    # + محاولة استرجاع D_website/D_country من Nexar للموزعين الفاضيين تماماً
    python backfill_distributors.py --apply --refetch-from-nexar

    # + محاولة استخراج المقر وسنة التأسيس مع بعض من نفس زيارة الموقع
    #   (D_headquarters -> مرشّح في research_notes للمراجعة،
    #    company_founded_year -> كتابة مباشرة)
    python backfill_distributors.py --apply --scrape-headquarters --scrape-founded-year
"""

import argparse
import datetime as dt
import json
import re
import time

import requests
from bs4 import BeautifulSoup
from supabase import Client, create_client

from config import config
from distributor_resolver import country_code_to_full_name, normalize_name
from nexar_client import NexarClient

# كود دولة ISO بحرفين فقط (مثلاً "HK", "CN") - لو القيمة الحالية مطابقة
# لهذا الشكل، نعتبرها "لم تُحوَّل بعد" ونحاول تحويلها.
_ISO_CODE_PATTERN = re.compile(r"^[A-Za-z]{2}$")

# حقول تشغيلية أساسية يُفترض دايماً توفّرها لأي موزع (جديد أو قديم) - لو
# فاضية تماماً، نطبّق عليها نفس افتراضيات config.NEW_DISTRIBUTOR_DEFAULTS
# باستثناء total_orders_placed اللي بنعالجه بمنطق منفصل أوضح.
_OPERATIONAL_DEFAULT_KEYS = [
    k for k in config.NEW_DISTRIBUTOR_DEFAULTS if k != "total_orders_placed"
]


def get_supabase_client() -> Client:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        raise RuntimeError(
            "متغيرات SUPABASE_URL / SUPABASE_SERVICE_KEY غير موجودة في .env"
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def derive_authorized_and_type(supabase: Client, d_code: str) -> tuple[str | None, str | None]:
    """
    يبحث في stock عن صفوف مرتبطة بهذا الموزع، ويشتق D_authorized/D_Type
    من قيمة Authorized_Dist الحقيقية المخزَّنة هناك (أصلاً جاية من Nexar).
    يرجّع (None, None) لو مفيش أي صف stock مرتبط - لا يوجد مصدر حقيقي.
    """
    response = (
        supabase.table(config.TABLE_STOCK)
        .select("Authorized_Dist")
        .eq("distributer_code", d_code)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None, None

    statuses = {row.get("Authorized_Dist") for row in rows if row.get("Authorized_Dist")}

    if "Yes" in statuses:
        if len(statuses) > 1:
            print(f"  ⚠️ ملاحظة: {d_code} عنده قيم Authorized_Dist مختلطة {statuses} - "
                  f"تم اختيار 'Yes' كالأرجح.")
        return "Yes", "Authorized Distributor"

    if statuses == {"No"}:
        return "No", "Independent Distributor"

    return None, None


def get_representative_mpn(supabase: Client, d_code: str) -> str | None:
    """يرجّع أي mpn واحد مرتبط بهذا الموزع في stock، لاستخدامه كنقطة انطلاق لسؤال Nexar."""
    response = (
        supabase.table(config.TABLE_STOCK)
        .select("mpn")
        .eq("distributer_code", d_code)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0]["mpn"] if rows else None


def refetch_website_and_country_from_nexar(
    nexar: NexarClient, mpn: str, target_normalized_name: str
) -> tuple[str | None, str | None]:
    """
    يسأل Nexar عن mpn معيّن، يدوّر بين كل الأجزاء (parts) والموزعين عن
    seller اسمه المطبَّع يطابق target_normalized_name، ويرجّع
    (homepageUrl, country_full_name) لو لقى تطابق، وإلا (None, None).
    """
    try:
        data = nexar.search_part(mpn)
    except Exception as exc:
        print(f"    ⚠️ فشل سؤال Nexar عن {mpn}: {exc}")
        return None, None

    results = data.get("supSearchMpn", {}).get("results", [])
    for result in results:
        part = result.get("part", {})
        for seller in part.get("sellers", []):
            company = seller.get("company", {})
            if normalize_name(company.get("name", "")) == target_normalized_name:
                website = company.get("homepageUrl")
                country = country_code_to_full_name(seller.get("country"))
                return website, country

    return None, None


def _ensure_url_scheme(url: str) -> str:
    """
    بعض قيم D_website المخزَّنة في distributer محفوظة بدون scheme واضح
    (مثلاً "tomark.co.uk" بدل "https://tomark.co.uk") - مكتبة requests
    مش قادرة تفتح رابط زي ده وتفشل بخطأ "No scheme supplied". هذا تطبيع
    حتمي بسيط (مش تخمين محتوى): لو الرابط ما بيبدأش بـ "http://" أو
    "https://"، نضيف "https://" تلقائياً قبل المحاولة.
    """
    url = (url or "").strip()
    if url and not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    return url


def _format_jsonld_address(addr) -> str | None:
    """يحوّل حقل address من JSON-LD (نص أو dict أو list) لسطر عنوان واحد مقروء."""
    if isinstance(addr, str):
        return addr.strip() or None
    if isinstance(addr, dict):
        parts = [
            addr.get("streetAddress"),
            addr.get("addressLocality"),
            addr.get("addressRegion"),
            addr.get("postalCode"),
            addr.get("addressCountry"),
        ]
        parts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        return ", ".join(parts) if parts else None
    if isinstance(addr, list):
        for item in addr:
            formatted = _format_jsonld_address(item)
            if formatted:
                return formatted
    return None


def _fetch_soup(url: str, timeout: int = 15) -> BeautifulSoup | None:
    """
    يجلب الصفحة الرئيسية لموقع الموزع مرة واحدة (بعد تطبيع الرابط)، ويرجّع
    BeautifulSoup جاهز للاستخدام. يُستخدم هذا الجلب الواحد لاستخراج أكتر
    من حقل (المقر + سنة التأسيس) بدل عمل طلب شبكة منفصل لكل حقل.
    """
    try:
        resp = requests.get(
            _ensure_url_scheme(url),
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NexusFlowDataAgent/1.0)"},
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        print(f"    ⚠️ فشل جلب {url}: {exc}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


def _extract_headquarters_from_soup(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """
    يحاول استخراج عنوان مقر الشركة من صفحة مُحمَّلة مسبقاً (soup).
    يرجّع (العنوان_المُستخرج, اسم_الطريقة) أو (None, None) لو مفيش.

    ⭐ عمداً: الطريقة الوحيدة المستخدَمة هي بيانات JSON-LD منظَّمة
    (schema.org Organization/Corporation/LocalBusiness) - بيانات structured
    حقيقية، مش تخمين نصي. لا يوجد أي بحث بكلمات مفتاحية في نص حر (زي "Address:")
    لأن ده تخمين غير موثوق يتعارض مع فلسفة "لا تخمين" المتّبعة في كل
    المشروع. لو الموقع مالوش JSON-LD منظَّم، نرجّع None بدل تخمين.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            types_to_check = item_type if isinstance(item_type, list) else [item_type]
            is_org = any(
                t in ("Organization", "Corporation", "LocalBusiness") for t in types_to_check
            )
            if is_org and "address" in item:
                formatted = _format_jsonld_address(item["address"])
                if formatted:
                    return formatted, "JSON-LD schema.org"

    return None, None


def _extract_jsonld_founding_year(soup: BeautifulSoup) -> str | None:
    """يبحث في بيانات JSON-LD المنظَّمة (schema.org) عن foundingDate صريح."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            types_to_check = item_type if isinstance(item_type, list) else [item_type]
            is_org = any(
                t in ("Organization", "Corporation", "LocalBusiness") for t in types_to_check
            )
            founding_date = item.get("foundingDate")
            if is_org and founding_date:
                # foundingDate ممكن تيجي "1995" أو "1995-06-01" - نستخرج
                # أول 4 أرقام متتالية بس (السنة).
                match = re.match(r"^\s*((?:19|20)\d{2})", str(founding_date))
                if match:
                    return match.group(1)
    return None


# أنماط نصية حرة تدل على سنة التأسيس - تُستخدم فقط كـ fallback لو مفيش
# JSON-LD منظَّم. كل نمط لازم يحتوي على كلمة مفتاحية صريحة (Founded/
# Established/Since/Est.) ملتصقة مباشرة بسنة رباعية الأرقام - مفيش أي بحث
# عن سنة لوحدها بدون سياق واضح (زي "© 2024" لوحدها)، تجنباً لالتقاط سنوات
# غير متعلقة بالتأسيس أصلاً (حقوق نشر، شراكات، إلخ).
_FOUNDING_YEAR_PATTERNS = [
    re.compile(r"\b(?:Founded|Established)\s*(?:in|since|:)?\s*((?:19|20)\d{2})\b", re.IGNORECASE),
    re.compile(r"\bSince\s+((?:19|20)\d{2})\b", re.IGNORECASE),
    re.compile(r"\bEst(?:d|ablished)?\.?\s*((?:19|20)\d{2})\b", re.IGNORECASE),
]


def _extract_text_founding_year(page_text: str) -> tuple[str | None, str | None]:
    """
    يبحث في النص المرئي للصفحة عن سنة تأسيس مرتبطة بكلمة مفتاحية صريحة.
    يرجّع (السنة، الاقتباس_السياقي) أو (None, None).
    """
    normalized = re.sub(r"\s+", " ", page_text)
    current_year = dt.datetime.now().year

    for pattern in _FOUNDING_YEAR_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        year = int(match.group(1))
        # فحص منطقي بسيط (مش تخمين) لاستبعاد نتائج مستحيلة: شركة "تأسست"
        # في المستقبل، أو قبل 1900 بشكل غير معقول لموزع إلكترونيات حديث.
        if not (1900 <= year <= current_year):
            continue
        start = max(0, match.start() - 30)
        end = min(len(normalized), match.end() + 30)
        snippet = normalized[start:end].strip()
        return str(year), snippet

    return None, None


def _extract_founded_year_from_soup(soup: BeautifulSoup) -> tuple[str | None, str | None, str | None]:
    """
    يحاول استخراج سنة تأسيس الموزع من صفحة مُحمَّلة مسبقاً (soup).
    يرجّع (السنة, اسم_الطريقة, الاقتباس_الداعم) أو (None, None, None).

    الأولوية: JSON-LD schema.org (foundingDate) أولاً - بيانات مُهيكَلة
    يعلنها الموقع صراحةً، مفيش لبس. لو مش موجودة، fallback لبحث نصي بكلمات
    مفتاحية صريحة (Founded/Established/Since/Est.) ملتصقة بسنة رباعية -
    وده أقل موثوقية من JSON-LD، فلازم يُعامَل كـ"مرشّح غير مؤكد" فقط
    (النتيجة بتتكتب في research_notes مع الاقتباس الداعم، مش مباشرة في
    company_founded_year، لحد ما تُراجَع بشرياً - نفس معيار D_headquarters).
    """
    jsonld_year = _extract_jsonld_founding_year(soup)
    if jsonld_year:
        return jsonld_year, "JSON-LD schema.org (foundingDate)", None

    page_text = soup.get_text(separator=" ")
    text_year, snippet = _extract_text_founding_year(page_text)
    if text_year:
        return text_year, "بحث نصي بكلمة مفتاحية (Founded/Established/Since/Est.)", snippet

    return None, None, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="تحديث القيم الحقيقية للموزعين الموجودين مسبقاً"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="تنفيذ التحديثات فعلياً في Supabase. بدون هذا الخيار: عرض فقط (dry-run).",
    )
    parser.add_argument(
        "--refetch-from-nexar", action="store_true",
        help="لو D_website/D_country لسه فاضيين بعد الخطوات المحلية، حاول "
        "استرجاعهم بسؤال Nexar عن قطعة ممثِّلة من stock الموزع (طلبات "
        "شبكة إضافية، فيها تأخير بين كل موزع لتجنب rate limit).",
    )
    parser.add_argument(
        "--scrape-headquarters", action="store_true",
        help="حاول استخراج عنوان المقر من D_website (بيانات JSON-LD منظَّمة "
        "فقط - بدون تخمين نصي). النتيجة تُكتب في research_notes كـ'مرشّح "
        "غير مؤكد' مع مصدره، وليس مباشرة في D_headquarters، لحد ما تُراجَع "
        "بشرياً.",
    )
    parser.add_argument(
        "--scrape-founded-year", action="store_true",
        help="حاول استخراج سنة التأسيس من D_website: أولوية لـ JSON-LD "
        "(foundingDate)، ثم بحث نصي بكلمات مفتاحية صريحة (Founded/"
        "Established/Since/Est.) كـ fallback. النتيجة تُكتب مباشرة في "
        "company_founded_year (بقرار صريح من صاحب المشروع)، مع سطر توثيق "
        "للمصدر/الاقتباس في research_notes للمراجعة لاحقاً عند الحاجة.",
    )
    args = parser.parse_args()

    supabase = get_supabase_client()
    nexar = NexarClient() if args.refetch_from_nexar else None

    response = (
        supabase.table(config.TABLE_DISTRIBUTOR)
        .select(
            "D_code, D_Name, D_country, D_authorized, D_Type, D_website, "
            "D_headquarters, research_notes, total_orders_placed, D_status, "
            "vetting_status, verification_status, data_source, dealt_with, "
            "company_founded_year"
        )
        .execute()
    )
    distributors = response.data or []

    print(f"عدد الموزعين الكلي في distributer: {len(distributors)}\n")

    updates_planned = 0

    for dist in distributors:
        d_code = dist["D_code"]
        d_name = dist.get("D_Name", "")
        changes: dict = {}

        # 1) D_country: تحويل كود لاسم كامل، فقط لو الشكل الحالي كود بحرفين
        current_country = dist.get("D_country")
        if current_country and _ISO_CODE_PATTERN.match(current_country.strip()):
            full_name = country_code_to_full_name(current_country)
            if full_name and full_name != current_country:
                changes["D_country"] = full_name

        # 2) D_authorized / D_Type: مشتقة من stock الحقيقي، فقط لو الحقل
        #    فاضي أو لسه على القيمة الافتراضية القديمة "No" الثابتة
        needs_auth_backfill = (
            dist.get("D_authorized") is None
            or dist.get("D_Type") is None
            or dist.get("D_authorized") == "No"
        )
        if needs_auth_backfill:
            derived_auth, derived_type = derive_authorized_and_type(supabase, d_code)
            if derived_auth is not None:
                if dist.get("D_authorized") != derived_auth:
                    changes["D_authorized"] = derived_auth
                if dist.get("D_Type") != derived_type:
                    changes["D_Type"] = derived_type

        # 3) total_orders_placed: 0 لو NULL فقط
        if dist.get("total_orders_placed") is None:
            changes["total_orders_placed"] = 0

        # 4) حقول تشغيلية أساسية فاضية تماماً -> نفس افتراضيات الموزع الجديد
        for key in _OPERATIONAL_DEFAULT_KEYS:
            if dist.get(key) is None:
                changes[key] = config.NEW_DISTRIBUTOR_DEFAULTS[key]

        # 5) (اختياري) استرجاع D_website/D_country من Nexar لو لسه فاضيين
        still_missing_website = dist.get("D_website") is None
        still_missing_country = (
            dist.get("D_country") is None and "D_country" not in changes
        )
        if args.refetch_from_nexar and (still_missing_website or still_missing_country):
            mpn = get_representative_mpn(supabase, d_code)
            if mpn:
                print(f"  🔎 [{d_code}] سؤال Nexar عن {mpn} لاسترجاع بيانات الموزع...")
                website, country = refetch_website_and_country_from_nexar(
                    nexar, mpn, normalize_name(d_name)
                )
                if website and still_missing_website:
                    changes["D_website"] = website
                if country and still_missing_country:
                    changes["D_country"] = country
                if not website and not country:
                    print(f"    ⚠️ لم يُعثر على تطابق اسم لـ '{d_name}' في نتائج {mpn}.")
                if config.NEXAR_REQUEST_DELAY_SECONDS > 0:
                    time.sleep(config.NEXAR_REQUEST_DELAY_SECONDS)
            else:
                print(f"  ⚠️ [{d_code}] مفيش أي mpn في stock لهذا الموزع - "
                      f"مش قادرين نسأل Nexar بدون نقطة انطلاق.")

        # 6) (اختياري) زيارة واحدة للموقع الرسمي لاستخراج المقر وسنة
        #    التأسيس مع بعض - بدل عمل طلب شبكة منفصل لكل حقل. يتفعّل لو
        #    أي من الحقلين المطلوبين لسه فاضي والـ flag المقابل له مفعّل.
        needs_hq = args.scrape_headquarters and dist.get("D_headquarters") is None
        needs_founded_year = (
            args.scrape_founded_year and dist.get("company_founded_year") is None
        )

        if needs_hq or needs_founded_year:
            website = dist.get("D_website") or changes.get("D_website")
            if website:
                print(f"  🔎 [{d_code}] زيارة {website} لاستخراج "
                      f"{'المقر' if needs_hq else ''}"
                      f"{' و' if needs_hq and needs_founded_year else ''}"
                      f"{'سنة التأسيس' if needs_founded_year else ''} ...")
                soup = _fetch_soup(website)

                if soup is None:
                    if needs_founded_year:
                        changes["company_founded_year"] = "Not found"
                        print("    ⚠️ فشل جلب الصفحة - تم تسجيل 'Not found' لسنة التأسيس.")
                else:
                    if needs_hq:
                        hq_candidate, method = _extract_headquarters_from_soup(soup)
                        if hq_candidate:
                            note = (
                                f"Candidate HQ (unverified, via {method} from {website}): "
                                f"{hq_candidate}"
                            )
                            existing_notes = dist.get("research_notes") or changes.get("research_notes") or ""
                            changes["research_notes"] = (
                                f"{existing_notes} | {note}" if existing_notes else note
                            )
                            print(
                                f"    ✅ لقينا مرشّح مقر: {hq_candidate} (عبر {method}) - "
                                f"تم وضعه في research_notes للمراجعة البشرية، "
                                f"وليس D_headquarters مباشرة."
                            )
                        else:
                            print("    ⚠️ لم يُعثر على JSON-LD منظَّم بالعنوان في الصفحة.")

                    if needs_founded_year:
                        year, method, snippet = _extract_founded_year_from_soup(soup)
                        if year:
                            changes["company_founded_year"] = year
                            note = f"company_founded_year={year} (via {method} from {website})"
                            if snippet:
                                note += f" | الاقتباس: \"{snippet}\""
                            existing_notes = dist.get("research_notes") or changes.get("research_notes") or ""
                            changes["research_notes"] = (
                                f"{existing_notes} | {note}" if existing_notes else note
                            )
                            print(f"    ✅ سنة التأسيس: {year} (عبر {method})")
                        else:
                            # ⭐ بقرار صريح من صاحب المشروع: نكتب "Not found"
                            # حرفياً بدل ما نسيب الحقل من غير تغيير - عشان
                            # يتوافق مع شكل البيانات الموجود بالفعل في
                            # الجدول. ملحوظة: "Not found" مش NULL، فالشرط
                            # "is None" هنا لن يعتبر هذا الصف مؤهلاً لإعادة
                            # المحاولة في أي تشغيلة قادمة - لازم إعادة
                            # تصفيره يدوياً لـ NULL أولاً لو حابين نحاول
                            # تاني لاحقاً.
                            changes["company_founded_year"] = "Not found"
                            print("    ⚠️ لم يُعثر على سنة تأسيس واضحة - تم تسجيل 'Not found'.")
            else:
                if needs_founded_year:
                    changes["company_founded_year"] = "Not found"
                print(f"  ⚠️ [{d_code}] مفيش D_website متاح - مش قادرين نحاول.")

        if not changes:
            print(f"[{d_code}] {d_name}: لا يوجد تحديث مطلوب.")
            continue

        updates_planned += 1
        print(f"[{d_code}] {d_name}: {changes}")

        if args.apply:
            supabase.table(config.TABLE_DISTRIBUTOR).update(changes).eq(
                "D_code", d_code
            ).execute()

    print(f"\n{'تم تطبيق' if args.apply else 'تحديثات مقترحة (dry-run)'}: {updates_planned} موزع.")
    if not args.apply and updates_planned > 0:
        print("راجع القائمة أعلاه، وشغّل بنفس الأمر + --apply لتنفيذها فعلياً.")


if __name__ == "__main__":
    main()