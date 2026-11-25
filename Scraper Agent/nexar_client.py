"""
nexar_client.py
-----------------
عميل بسيط للاتصال بـ Nexar API (OAuth2 client_credentials + GraphQL).

ملاحظة مهمة: استعلام GraphQL أدناه (SUPPLY_PART_QUERY) مبني على الحقول
الشائعة والموثّقة في Nexar Supply API (supSearchMpn / supPart). يُفضّل
التحقق منه بعد ربط المفتاح الحقيقي عبر Nexar GraphQL Explorer، لأن بعض
الحقول قد تختلف حسب باقة الاشتراك.
"""

import logging
import time
from typing import Any, Optional

import requests

from config import config

console = logging.getLogger("nexusflow.nexar")

# ---------------------------------------------------------------------------
# إعدادات إعادة المحاولة (Retry) لـ search_part
# ---------------------------------------------------------------------------
# نعيد المحاولة فقط عند أخطاء *مؤقتة* الطبيعة: تجاوز حد الطلبات (429)،
# أخطاء الخادم (5xx)، أو مشاكل شبكة/timeout. لا نعيد المحاولة أبداً عند
# أخطاء منطقية دائمة (401 توكن غلط، 400 query غلط، أو أخطاء GraphQL) لأن
# إعادة المحاولة فيها مضيعة وقت مضمونة الفشل بنفس الطريقة في كل مرة.
NEXAR_MAX_ATTEMPTS = 3
NEXAR_RETRY_BACKOFF_SECONDS = 1  # يتضاعف: 1s, 2s, 4s
NEXAR_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class NexarAuthError(Exception):
    pass


class NexarRetryExhaustedError(Exception):
    """تُرفع بعد فشل كل محاولات إعادة الاتصال لسبب مؤقت."""
    pass


class NexarClient:
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ---------------------------------------------------------------
    # المصادقة (OAuth2 Client Credentials)
    # ---------------------------------------------------------------
    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token

        resp = requests.post(
            config.NEXAR_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": config.NEXAR_CLIENT_ID,
                "client_secret": config.NEXAR_CLIENT_SECRET,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            raise NexarAuthError(f"فشل الحصول على Access Token: {resp.status_code} {resp.text}")

        payload = resp.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = time.time() + payload.get("expires_in", 3600)
        return self._access_token

    # ---------------------------------------------------------------
    # GraphQL
    # ---------------------------------------------------------------
    SUPPLY_PART_QUERY = """
    query SupSearchMpn($q: String!, $limit: Int!, $country: String!, $inStockOnly: Boolean!) {
      supSearchMpn(q: $q, limit: $limit, country: $country, inStockOnly: $inStockOnly) {
        results {
          part {
            mpn
            manufacturer { name }
            shortDescription
            specs {
              attribute { name shortname }
              displayValue
            }
            sellers {
              company { name homepageUrl }
              country
              isAuthorized
              isRfq
              offers {
                sku
                inventoryLevel
                packaging
                moq
                clickUrl
                factoryLeadDays
                updated
                prices { quantity price currency }
              }
            }
          }
        }
      }
    }
    """

    def search_part(
        self,
        mpn: str,
        limit: int = 5,
        country: str = "US",
        in_stock_only: bool = False,
    ) -> dict[str, Any]:
        """
        نقطة الدخول العامة: تحاول جلب بيانات القطعة مع إعادة محاولة تلقائية
        (حتى NEXAR_MAX_ATTEMPTS مرات) عند فشل مؤقت فقط (429 / 5xx / خطأ شبكة)،
        بانتظار متزايد (Backoff) بين كل محاولة والتالية: 1s, 2s, 4s.

        country: يحدّد سياق التوفر/المخزون (Nexar يفترض "US" افتراضياً لو
        ما اتحددش - هنا بنثبته صراحة بدل الاعتماد على افتراض ضمني).
        in_stock_only: لو True، يرجّع بس عروض متوفرة فعلياً في المخزون
        (غالباً بيانات أكمل، لكن هيقلل عدد النتائج الكلي - جرّبه وشوف
        هل التريد أوف يناسبك).
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, NEXAR_MAX_ATTEMPTS + 1):
            try:
                return self._search_part_once(mpn, limit, country, in_stock_only)

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in NEXAR_RETRYABLE_STATUS_CODES:
                    # خطأ دائم (مثلاً 400 query غلط) -> لا فائدة من إعادة المحاولة
                    raise
                last_exc = exc

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                # مشاكل شبكة/timeout مؤقتة بطبيعتها -> تستحق إعادة المحاولة
                last_exc = exc

            # لو وصلنا هنا فالخطأ مؤقت (retryable) وليست آخر محاولة
            if attempt < NEXAR_MAX_ATTEMPTS:
                wait_seconds = NEXAR_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))  # 1, 2, 4
                console.warning(
                    f"محاولة {attempt}/{NEXAR_MAX_ATTEMPTS} فشلت للقطعة {mpn} "
                    f"({last_exc}). إعادة المحاولة بعد {wait_seconds}s..."
                )
                time.sleep(wait_seconds)

        # فشلت كل المحاولات -> نرفع الاستثناء الأخير بعد المحاولة الثالثة فقط
        raise NexarRetryExhaustedError(
            f"فشل جلب بيانات القطعة {mpn} من Nexar بعد {NEXAR_MAX_ATTEMPTS} محاولات: {last_exc}"
        ) from last_exc

    def _search_part_once(
        self,
        mpn: str,
        limit: int,
        country: str,
        in_stock_only: bool,
    ) -> dict[str, Any]:
        """محاولة واحدة فعلية لطلب GraphQL - بدون أي منطق retry هنا."""
        token = self._get_access_token()
        resp = requests.post(
            config.NEXAR_GRAPHQL_URL,
            json={
                "query": self.SUPPLY_PART_QUERY,
                "variables": {
                    "q": mpn,
                    "limit": limit,
                    "country": country,
                    "inStockOnly": in_stock_only,
                },
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()  # يرفع HTTPError لو 4xx/5xx (تُعالَج في search_part)
        data = resp.json()

        if "errors" in data:
            # خطأ GraphQL منطقي (query غلط، إلخ) -> ليس مؤقتاً، لا داعي لإعادة المحاولة
            raise RuntimeError(f"Nexar GraphQL error for MPN={mpn}: {data['errors']}")

        return data["data"]