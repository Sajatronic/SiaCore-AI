"""Provider unit tests with mocked HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import RawArticle
from providers.gdacs_provider import GdacsProvider
from providers.gdelt_provider import GdeltProvider
from providers.gnews_provider import GNewsProvider
from providers.marketaux_provider import MarketauxProvider
from providers.newsdata_provider import NewsDataProvider
from providers.registry import ingest_all_providers


GDACS_FIXTURE = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {
                "eventid": 123,
                "episodeid": 456,
                "eventtype": "EQ",
                "name": "Earthquake in Taiwan",
                "alertlevel": "Orange",
                "country": "Taiwan",
                "fromdate": "2026-06-25T10:00:00Z",
                "severitydata": {"severity": 6.2, "severitytext": "Magnitude 6.2"},
                "url": {"report": "https://www.gdacs.org/report.aspx?eventid=123"},
            }
        }
    ],
}

GDELT_FIXTURE = {
    "data": [
        {
            "title": "Protest near semiconductor plant",
            "description": "Workers strike at chip facility",
            "url": "https://example.com/gdelt-1",
            "published_at": "2026-06-25T12:00:00Z",
        }
    ]
}

MARKETAUX_FIXTURE = {
    "data": [
        {
            "uuid": "abc",
            "title": "Supplier bankruptcy filing",
            "description": "Electronics supplier faces liquidity crisis",
            "url": "https://example.com/marketaux-1",
            "published_at": "2026-06-25T08:00:00Z",
            "entities": [{"sentiment_score": -0.4}],
        }
    ]
}

GNEWS_FIXTURE = {
    "articles": [
        {
            "title": "Port closure disrupts chip shipments",
            "description": "Major port halted operations",
            "url": "https://example.com/gnews-1",
            "publishedAt": "2026-06-25T09:00:00Z",
            "source": {"name": "Example News"},
        }
    ]
}

NEWSDATA_FIXTURE = {
    "results": [
        {
            "title": "Export controls on semiconductor equipment",
            "description": "New trade restrictions announced",
            "link": "https://example.com/newsdata-1",
            "pubDate": "2026-06-25T07:00:00Z",
            "language": "english",
        }
    ]
}


@pytest.mark.asyncio
async def test_gdacs_normalization():
    provider = GdacsProvider()
    with patch(
        "providers.gdacs_provider.fetch_json",
        new=AsyncMock(return_value=GDACS_FIXTURE),
    ):
        articles = await provider.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].provider == "gdacs"
    assert articles[0].reliability_tier == 1
    assert "Taiwan" in articles[0].title
    assert articles[0].provider_metadata["event_type"] == "EQ"
    assert "Event type:" not in articles[0].body
    assert "earthquake" in articles[0].body.lower()
    assert "Orange alert" in articles[0].body


@pytest.mark.asyncio
async def test_gdelt_requires_api_key():
    provider = GdeltProvider()
    with patch("providers.gdelt_provider.settings.gdelt_api_key", ""):
        articles = await provider.fetch()
    assert articles == []


@pytest.mark.asyncio
async def test_gdelt_normalization():
    provider = GdeltProvider()
    with (
        patch("providers.gdelt_provider.settings.gdelt_api_key", "test-key"),
        patch(
            "providers.gdelt_provider.fetch_json",
            new=AsyncMock(return_value=GDELT_FIXTURE),
        ),
    ):
        articles = await provider.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].reliability_tier == 1
    assert "semiconductor" in articles[0].title.lower()


@pytest.mark.asyncio
async def test_marketaux_normalization():
    provider = MarketauxProvider()
    with (
        patch("providers.marketaux_provider.settings.marketaux_api_token", "token"),
        patch(
            "providers.marketaux_provider.fetch_json",
            new=AsyncMock(return_value=MARKETAUX_FIXTURE),
        ),
    ):
        articles = await provider.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].reliability_tier == 2


@pytest.mark.asyncio
async def test_gnews_normalization():
    provider = GNewsProvider()
    with (
        patch("providers.gnews_provider.settings.gnews_api_token", "token"),
        patch(
            "providers.gnews_provider.fetch_json",
            new=AsyncMock(return_value=GNEWS_FIXTURE),
        ),
    ):
        articles = await provider.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].reliability_tier == 3


@pytest.mark.asyncio
async def test_newsdata_normalization():
    provider = NewsDataProvider()
    with (
        patch("providers.newsdata_provider.settings.newsdata_api_key", "token"),
        patch(
            "providers.newsdata_provider.fetch_json",
            new=AsyncMock(return_value=NEWSDATA_FIXTURE),
        ),
    ):
        articles = await provider.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].reliability_tier == 3


@pytest.mark.asyncio
async def test_ingest_all_providers_parallel():
    gdacs_article = RawArticle(provider="gdacs", title="EQ event", body="test")
    gnews_article = RawArticle(provider="gnews", title="Port news", body="test")

    with patch(
        "providers.registry.get_enabled_providers",
        return_value=[GdacsProvider(), GNewsProvider()],
    ):
        with (
            patch.object(GdacsProvider, "fetch", new=AsyncMock(return_value=[gdacs_article])),
            patch.object(GNewsProvider, "fetch", new=AsyncMock(return_value=[gnews_article])),
        ):
            articles, report = await ingest_all_providers(limit=5)

    assert len(articles) == 2
    assert report["total_articles"] == 2
    assert report["providers"]["gdacs"]["count"] == 1
    assert report["providers"]["gnews"]["count"] == 1
