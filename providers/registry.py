"""Provider registry and parallel ingestion orchestration."""

from __future__ import annotations

import asyncio
from typing import Any
from config.settings import settings
from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.gdacs_provider import GdacsProvider
from providers.gdelt_provider import GdeltProvider
from providers.gnews_provider import GNewsProvider
from providers.marketaux_provider import MarketauxProvider
from providers.newsdata_provider import NewsDataProvider

PROVIDER_REGISTRY: dict[str, type[BaseNewsProvider]] = {
    "gdacs": GdacsProvider,
    "gdelt": GdeltProvider,
    "marketaux": MarketauxProvider,
    "gnews": GNewsProvider,
    "newsdata": NewsDataProvider,
}


def get_provider(name: str) -> BaseNewsProvider:
    key = name.lower().strip()
    if key not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider: {name}")
    return PROVIDER_REGISTRY[key]()


def get_enabled_providers() -> list[BaseNewsProvider]:
    return [get_provider(name) for name in settings.enabled_providers if name in PROVIDER_REGISTRY]


async def _fetch_provider(
    provider: BaseNewsProvider,
    **kwargs: Any,
) -> tuple[str, list[RawArticle], str | None]:
    try:
        articles = await provider.fetch(**kwargs)
        return provider.provider_name, articles, None
    except Exception as exc:  # noqa: BLE001 — collect per-provider failures for audit
        return provider.provider_name, [], str(exc)


async def ingest_all_providers(**kwargs: Any) -> tuple[list[RawArticle], dict[str, Any]]:
    """Fetch from all enabled providers in parallel.

    Returns normalized articles and an ingestion report with per-provider counts/errors.
    """
    providers = get_enabled_providers()
    if not providers:
        return [], {"providers": {}, "total_articles": 0}

    results = await asyncio.gather(*[_fetch_provider(provider, **kwargs) for provider in providers])

    articles: list[RawArticle] = []
    report: dict[str, Any] = {"providers": {}, "total_articles": 0}

    for provider_name, provider_articles, error in results:
        articles.extend(provider_articles)
        report["providers"][provider_name] = {
            "count": len(provider_articles),
            "error": error,
        }

    report["total_articles"] = len(articles)
    return articles, report
