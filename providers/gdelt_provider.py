"""GDELT Cloud provider — geopolitical events, tier 1."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from config.settings import settings
from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.http_client import fetch_json


class GdeltProvider(BaseNewsProvider):
    provider_name = "gdelt"
    reliability_tier = 1
    base_url = "https://gdeltcloud.com/api/v2"

    async def fetch(self, **kwargs) -> list[RawArticle]:
        api_key = settings.gdelt_api_key
        if not api_key:
            return []

        limit: int = kwargs.get("limit", 25)
        search: str = kwargs.get("search", settings.supply_chain_search_query)
        params: dict[str, Any] = {"search": search, "limit": limit}
        if kwargs.get("country"):
            params["country"] = kwargs["country"]
        if kwargs.get("category"):
            params["category"] = kwargs["category"]

        timeout = kwargs.get("timeout", 30.0)
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await fetch_json(
                client,
                provider=self.provider_name,
                url=f"{self.base_url}/events",
                params=params,
                headers=headers,
            )

        records = payload.get("data", []) if isinstance(payload, dict) else []
        articles: list[RawArticle] = []
        for record in records[:limit]:
            article = self._normalize_event(record)
            if article is not None:
                articles.append(article)
        return articles

    def _normalize_event(self, record: dict[str, Any]) -> RawArticle | None:
        title = (
            record.get("title")
            or record.get("name")
            or record.get("headline")
            or record.get("summary")
        )
        if not title:
            return None

        body = str(
            record.get("description")
            or record.get("summary")
            or record.get("body")
            or record.get("text")
            or ""
        )
        url = record.get("url") or record.get("source_url") or record.get("link")
        published_at = self._parse_datetime(
            record.get("published_at") or record.get("date") or record.get("timestamp")
        )

        return RawArticle(
            provider=self.provider_name,
            title=str(title),
            body=body,
            published_at=published_at,
            url=str(url) if url else None,
            reliability_tier=self.reliability_tier,
            provider_metadata={"raw": record},
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.utcfromtimestamp(value)
            except (OSError, OverflowError, ValueError):
                return None
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
