"""NewsData.io provider — general news aggregator, tier 3."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config.settings import settings
from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.http_client import fetch_json


class NewsDataProvider(BaseNewsProvider):
    provider_name = "newsdata"
    reliability_tier = 3
    base_url = "https://newsdata.io/api/1/latest"

    async def fetch(self, **kwargs) -> list[RawArticle]:
        api_key = settings.newsdata_api_key
        if not api_key:
            return []

        limit: int = kwargs.get("limit", 25)
        params: dict[str, Any] = {
            "apikey": api_key,
            "q": kwargs.get("search", settings.supply_chain_search_query),
            "language": kwargs.get("language", "en"),
        }

        timeout = kwargs.get("timeout", 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await fetch_json(
                client,
                provider=self.provider_name,
                url=self.base_url,
                params=params,
            )

        records = payload.get("results", []) if isinstance(payload, dict) else []
        articles: list[RawArticle] = []
        for record in records[:limit]:
            article = self._normalize_article(record)
            if article is not None:
                articles.append(article)
        return articles

    def _normalize_article(self, record: dict[str, Any]) -> RawArticle | None:
        title = record.get("title")
        if not title:
            return None

        body = str(record.get("description") or record.get("content") or "")
        url = record.get("link") or record.get("source_url")
        published_at = self._parse_datetime(record.get("pubDate") or record.get("published_at"))

        return RawArticle(
            provider=self.provider_name,
            title=str(title),
            body=body,
            published_at=published_at,
            url=str(url) if url else None,
            language=str(record.get("language") or "en"),
            reliability_tier=self.reliability_tier,
            provider_metadata={
                "source_id": record.get("source_id"),
                "source_name": record.get("source_name"),
                "category": record.get("category"),
                "country": record.get("country"),
            },
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
