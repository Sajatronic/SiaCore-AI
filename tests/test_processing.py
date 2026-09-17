"""Tests for rule-based processing helpers."""

from models.schemas import EnrichedArticle, RawArticle
from nodes.prefilter import score_article_relevance
from nodes.processing import classify_article


def test_gdacs_earthquake_classification():
    item = EnrichedArticle(
        article=RawArticle(
            provider="gdacs",
            title="Earthquake in Taiwan",
            body="Magnitude 6.2 earthquake",
            provider_metadata={"event_type": "EQ", "alert_level": "Orange"},
        )
    )
    result = classify_article(item)
    assert result.event_category.value == "natural_disaster"
    assert result.event_type == "earthquake"
    assert result.confidence >= 0.9


def test_supply_chain_keyword_relevance():
    from models.schemas import RawArticle

    article = RawArticle(
        provider="gnews",
        title="Semiconductor factory shutdown in Taiwan",
        body="",
    )
    score, _, _ = score_article_relevance(article)
    assert score >= 0.45
