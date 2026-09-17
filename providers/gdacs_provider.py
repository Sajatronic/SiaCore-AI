"""GDACS disaster event provider — public API, tier 1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from models.schemas import RawArticle
from providers.base import BaseNewsProvider
from providers.http_client import fetch_json
from services.news_summary import build_gdacs_description


class GdacsProvider(BaseNewsProvider):
    provider_name = "gdacs"
    reliability_tier = 1
    base_url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

    async def fetch(self, **kwargs) -> list[RawArticle]:
        limit: int = kwargs.get("limit", 50)
        event_types: str = kwargs.get("event_types", "EQ;FL;TC")
        alert_levels: str = kwargs.get("alert_levels", "green;orange;red")
        days_back: int = kwargs.get("days_back", 7)

        to_date = datetime.now(timezone.utc).date()
        from_date = to_date - timedelta(days=days_back)
        params = {
            "eventlist": event_types,
            "alertlevel": alert_levels,
            "fromdate": from_date.isoformat(),
            "todate": to_date.isoformat(),
        }

        timeout = kwargs.get("timeout", 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = await fetch_json(
                client,
                provider=self.provider_name,
                url=self.base_url,
                params=params,
            )

        features = payload.get("features", []) if isinstance(payload, dict) else []
        articles: list[RawArticle] = []
        for feature in features[:limit]:
            article = self._normalize_feature(feature)
            if article is not None:
                articles.append(article)
        return articles

    def _normalize_feature(self, feature: dict[str, Any]) -> RawArticle | None:
        props = feature.get("properties") or {}
        event_id = props.get("eventid")
        if event_id is None:
            return None

        name = str(props.get("name") or "GDACS event")
        event_type = str(props.get("eventtype") or "UNKNOWN")
        alert_level = str(props.get("alertlevel") or "")
        country = str(props.get("country") or "")
        severity_data = props.get("severitydata") or {}
        severity_text = str(
            severity_data.get("severitytext") or severity_data.get("severity") or ""
        )

        url_obj = props.get("url") or {}
        report_url = url_obj.get("report") if isinstance(url_obj, dict) else None

        published_at = self._parse_datetime(props.get("fromdate") or props.get("todate"))

        body = build_gdacs_description(
            event_type=event_type,
            alert_level=alert_level,
            country=country,
            severity_text=severity_text,
        )

        return RawArticle(
            provider=self.provider_name,
            title=name,
            body=body,
            published_at=published_at,
            url=str(report_url) if report_url else None,
            reliability_tier=self.reliability_tier,
            provider_metadata={
                "event_id": event_id,
                "episode_id": props.get("episodeid"),
                "event_type": event_type,
                "alert_level": alert_level,
                "alert_score": props.get("alertscore"),
                "country": country,
                "iso3": props.get("iso3"),
                "severity_data": severity_data,
                "affected_countries": props.get("affectedcountries"),
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
