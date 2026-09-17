"""Phase 4 relevance pre-filter tests."""

from models.schemas import RawArticle
from nodes.prefilter import filter_articles, score_article_relevance


def test_gdacs_auto_passes():
    article = RawArticle(
        provider="gdacs",
        title="Earthquake in Chile",
        body="Magnitude 5.1 earthquake reported",
    )
    score, matched, reason = score_article_relevance(article)
    assert score == 1.0
    assert reason == "provider_auto_pass"


def test_semiconductor_article_passes():
    article = RawArticle(
        provider="gnews",
        title="Semiconductor fab shutdown in Taiwan affects chip supply",
        body="Production halted at major facility",
    )
    score, matched, _ = score_article_relevance(article)
    assert score >= 0.45
    assert any("semiconductor" in term for term in matched)


def test_irrelevant_article_dropped():
    article = RawArticle(
        provider="gdelt",
        title="Celebrity football match raises charity funds",
        body="Movie premiere after the game",
    )
    kept, drops = filter_articles([article])
    assert len(kept) == 0
    assert len(drops) == 1
    assert drops[0].drop_reason == "negative_keyword_match"


def test_manufacturer_match_boosts_score():
    article = RawArticle(
        provider="newsdata",
        title="Texas Instruments warns of supply constraints",
        body="The analog chip maker cited logistics delays",
    )
    score, matched, _ = score_article_relevance(article)
    assert score >= 0.45
    assert any("manufacturer:" in term for term in matched)


def test_filter_batch_mixed():
    relevant = RawArticle(
        provider="gdelt",
        title="Port closure disrupts semiconductor shipments",
        body="Export delays at major hub",
    )
    irrelevant = RawArticle(
        provider="gdelt",
        title="Local restaurant opens new branch",
        body="Grand opening celebration this weekend",
    )
    kept, drops = filter_articles([relevant, irrelevant])
    assert len(kept) == 1
    assert len(drops) == 1
    assert kept[0].article.title.startswith("Port closure")
