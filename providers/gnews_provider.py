"""GNews provider — general news aggregator, tier 3."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config.settings import settings
from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.http_client import fetch_json


class GNewsProvider(BaseNewsProvider):
    provider_name = "gnews"
    reliability_tier = 3
    base_url = "https://gnews.io/api/v4/search"

    async def fetch(self, **kwargs) -> list[RawArticle]:
        api_token = settings.gnews_api_token
        if not api_token:
            return []

        limit: int = kwargs.get("limit", 25)
        params: dict[str, Any] = {
            "apikey": api_token,
            "q": kwargs.get("search", settings.supply_chain_search_query),
            "lang": kwargs.get("language", "en"),
            "max": min(limit, 100),
            "sortby": "publishedAt",
        }

        timeout = kwargs.get("timeout", 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await fetch_json(
                client,
                provider=self.provider_name,
                url=self.base_url,
                params=params,
            )

        records = payload.get("articles", []) if isinstance(payload, dict) else []
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
        url = record.get("url")
        published_at = self._parse_datetime(record.get("publishedAt"))

        source = record.get("source") or {}
        source_name = source.get("name") if isinstance(source, dict) else None

        return RawArticle(
            provider=self.provider_name,
            title=str(title),
            body=body,
            published_at=published_at,
            url=str(url) if url else None,
            reliability_tier=self.reliability_tier,
            provider_metadata={
                "source_name": source_name,
                "image": record.get("image"),
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
