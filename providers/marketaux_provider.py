"""Marketaux financial news provider — tier 2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config.settings import settings
from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.http_client import fetch_json


class MarketauxProvider(BaseNewsProvider):
    provider_name = "marketaux"
    reliability_tier = 2
    base_url = "https://api.marketaux.com/v1/news/all"

    async def fetch(self, **kwargs) -> list[RawArticle]:
        api_token = settings.marketaux_api_token
        if not api_token:
            return []

        limit: int = kwargs.get("limit", 25)
        params: dict[str, Any] = {
            "api_token": api_token,
            "language": kwargs.get("language", "en"),
            "limit": limit,
            "filter_entities": "true",
            "search": kwargs.get("search", settings.supply_chain_search_query),
        }
        if kwargs.get("industries"):
            params["industries"] = kwargs["industries"]

        timeout = kwargs.get("timeout", 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await fetch_json(
                client,
                provider=self.provider_name,
                url=self.base_url,
                params=params,
            )

        records = payload.get("data", []) if isinstance(payload, dict) else []
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

        body = str(record.get("description") or record.get("snippet") or "")
        url = record.get("url")
        published_at = self._parse_datetime(record.get("published_at"))

        return RawArticle(
            provider=self.provider_name,
            title=str(title),
            body=body,
            published_at=published_at,
            url=str(url) if url else None,
            reliability_tier=self.reliability_tier,
            provider_metadata={
                "uuid": record.get("uuid"),
                "entities": record.get("entities"),
                "keywords": record.get("keywords"),
                "sentiment": self._extract_sentiment(record),
            },
        )

    @staticmethod
    def _extract_sentiment(record: dict[str, Any]) -> Any:
        entities = record.get("entities") or []
        if not entities:
            return record.get("sentiment")
        scores = [entity.get("sentiment_score") for entity in entities if entity.get("sentiment_score") is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
