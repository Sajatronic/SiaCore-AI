"""
config.py
---------
إعدادات المشروع المركزية. كل القيم الحساسة تُقرأ من متغيرات البيئة (.env)
ولا يجب أبداً كتابتها مباشرة في الكود.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # يقرأ ملف .env الموجود في جذر المشروع


class Config:
    # ---- Supabase ----
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")  # يفضّل service_role للكتابة

    # ---- Nexar API ----
    NEXAR_CLIENT_ID: str = os.getenv("NEXAR_CLIENT_ID", "")
    NEXAR_CLIENT_SECRET: str = os.getenv("NEXAR_CLIENT_SECRET", "")
    NEXAR_TOKEN_URL: str = "https://identity.nexar.com/connect/token"
    NEXAR_GRAPHQL_URL: str = "https://api.nexar.com/graphql"

    # ---- إعدادات المطابقة (Distributor Resolver) ----
    # اللواحق/الكلمات التي تُحذف أثناء التطبيع (lowercase بالفعل)
    NAME_NOISE_WORDS = [
        "inc", "inc.", "ltd", "ltd.", "llc", "l.l.c.", "co", "co.",
        "corporation", "corp", "corp.", "electronics", "electronic",
        "technology", "technologies", "group", "pte", "limited",
        "company", "the",
    ]

    # بادئة كود الموزع الجديد التلقائي
    NEW_DISTRIBUTOR_CODE_PREFIX = "SUP"

    # القيم الافتراضية الآمنة لأي موزع جديد يُنشأ تلقائياً من الـ Agent.
    # ⚠️ كل قيمة هنا لازم تكون *حقيقية فعلاً* وليست تخميناً - مثلاً
    # total_orders_placed=0 و years_relationship=0.0 و quality_issues_l12m=0
    # كلها حقائق فعلية (لسه محصلش أي تعامل مع هذا الموزع أصلاً)، مش أرقام
    # مُختلَقة. وبالمثل relationship_tier="Not Engaged" و
    # vetting_status="Not Vetted" حالات حقيقية تصف "لسه معملناش أي تعامل/
    # تدقيق"، مش تقييم مُخترَع.
    #
    # في المقابل: أي مقياس *معدّل محسوب* من تاريخ تعاملات (زي
    # on_time_delivery_rate، relationship_risk_score) عمداً غير موجود هنا -
    # لإنه رياضياً 0/0 غير معرَّف (مفيش طلبات أصلاً يُحسب المعدّل منها)،
    # فالقيمة الحقيقية الوحيدة له عند إنشاء موزع جديد هي NULL لحد ما يحصل
    # تعامل فعلي يُبنى عليه الحساب.
    NEW_DISTRIBUTOR_DEFAULTS = {
        "D_status": "Pending Review",
        "vetting_status": "Not Vetted",
        "verification_status": "Unverified",
        "data_source": "Nexar API - Auto",
        "dealt_with": "No",
        "total_orders_placed": 0,
        "relationship_tier": "Not Engaged",
        "years_relationship": 0.0,
        "quality_issues_l12m": 0,
    }

    # ---- الجداول ----
    TABLE_DISTRIBUTOR = "distributer"
    TABLE_STOCK = "stock"
    TABLE_AGENT_LOGS = "agent_logs"

    # ---- التحكم في حجم الدفعة بسبب حد Nexar API (rate limit) ----
    # كم قطعة (MPN) يعالجها الـ Agent كحد أقصى في كل تشغيل واحد.
    MAX_PARTS_PER_RUN: int = int(os.getenv("MAX_PARTS_PER_RUN", "50"))

    # تأخير (بالثواني) بين كل طلب وطلب لـ Nexar، لتجنب تجاوز حد الطلبات
    # في الدقيقة/الثانية حسب باقتك.
    NEXAR_REQUEST_DELAY_SECONDS: float = float(
        os.getenv("NEXAR_REQUEST_DELAY_SECONDS", "1.0")
    )

    # ملف تتبّع نقطة التوقف (checkpoint) بين التشغيلات المتتالية
    CHECKPOINT_FILE: str = os.getenv("CHECKPOINT_FILE", "checkpoint.json")


config = Config()
