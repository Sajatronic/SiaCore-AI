"""Relevance pre-filtering — Phase 4.

Entity terms (manufacturer names, aliases, category names) are now loaded
directly from the Supply Chain database via the registry cache in matchers.py.
No JSON file is read at import time.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings
from models.schemas import EnrichedArticle, PrefilterDropRecord, RawArticle


def _normalize_category(name: str) -> str:
    """Turn catalog category slugs into searchable phrases."""
    text = name.replace("__", " ").replace("_", " ").strip()
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=1)
def _load_keyword_config() -> dict[str, Any]:
    path = settings.project_root / "config" / "relevance_keywords.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_entity_terms() -> dict[str, list[str]]:
    """
    Load manufacturer names/aliases and category names from the DB-backed registry.

    Previously this read canonical_entities.json from disk.
    Now it uses the in-memory registry built from the Supply Chain DB.
    The result is still cached via lru_cache for the process lifetime.
    """
    # Import here to avoid circular imports at module load time
    from canonical.matchers import _load_registry

    registry = _load_registry()

    manufacturers: list[str] = []
    for name, record in registry.get("manufacturers", {}).items():
        manufacturers.append(name)
        manufacturers.extend(record.get("aliases", []))

    categories: set[str] = set()
    for supplier in registry.get("suppliers", {}).values():
        for category in supplier.get("categories", []):
            categories.add(_normalize_category(category))

    return {
        "manufacturers": sorted(
            {m for m in manufacturers if len(m) >= 3}, key=len, reverse=True
        ),
        "categories": sorted(categories, key=len, reverse=True),
    }


@lru_cache(maxsize=1)
def _topic_keywords() -> list[tuple[str, float, str]]:
    """Flatten topic keywords into (keyword, weight, topic) tuples."""
    config = _load_keyword_config()
    entries: list[tuple[str, float, str]] = []
    for topic, spec in config.get("topics", {}).items():
        weight = float(spec.get("weight", 0.8))
        for keyword in spec.get("keywords", []):
            entries.append((keyword.lower(), weight, topic))
    entries.sort(key=lambda item: len(item[0]), reverse=True)
    return entries


def _provider_rule(provider: str) -> dict[str, Any]:
    config = _load_keyword_config()
    rules = config.get("provider_rules", {})
    return rules.get(
        provider, {"auto_pass": False, "min_score": settings.relevance_min_score}
    )


def _negative_keywords() -> list[str]:
    return [kw.lower() for kw in _load_keyword_config().get("negative_keywords", [])]


def _has_supply_chain_context(text: str) -> bool:
    """Check if text contains strong supply-chain operational language."""
    context_keywords = {
        "supply chain", "supplier", "manufacturer", "factory", "production",
        "semiconductor", "chip", "component", "sourcing", "procurement",
        "disruption", "shortage", "backorder", "lead time",
    }
    return sum(1 for kw in context_keywords if kw in text) >= 2


def score_article_relevance(article: RawArticle) -> tuple[float, list[str], str]:
    """
    Score an article for supply-chain relevance.

    Returns (score, matched_terms, decision_reason).

    Entity terms come from the DB-backed registry (via _load_entity_terms).
    """
    rule = _provider_rule(article.provider)
    if rule.get("auto_pass"):
        return 1.0, ["provider:auto_pass"], "provider_auto_pass"

    text = f"{article.title} {article.body}".lower()
    if not text.strip():
        return 0.0, [], "empty_content"

    # Early exit on negative keywords
    for negative in _negative_keywords():
        if negative in text:
            return 0.0, [f"negative:{negative}"], "negative_keyword_match"

    matched: list[str] = []
    score = 0.0
    entity_count = 0

    # ── Topic keywords ────────────────────────────────────────────────────────
    found_core_topics: list[str] = []
    for keyword, weight, topic in _topic_keywords():
        if keyword in text:
            matched.append(f"{topic}:{keyword}")
            if topic in {"semiconductor", "supply_chain", "disruption"}:
                score += 0.25 * weight
            else:
                score += 0.20 * weight
            found_core_topics.append(topic)

    # ── Manufacturer matching (DB-sourced) ────────────────────────────────────
    entity_terms = _load_entity_terms()
    manufacturer_found = False
    for manufacturer in entity_terms["manufacturers"]:
        mfr_lower = manufacturer.lower()
        if re.search(rf"\b{re.escape(mfr_lower)}\b", text):
            matched.append(f"manufacturer:{manufacturer}")
            score += 0.35
            manufacturer_found = True
            entity_count += 1

    # ── Category matching (DB-sourced) ────────────────────────────────────────
    category_found = False
    for category in entity_terms["categories"]:
        if re.search(rf"\b{re.escape(category)}\b", text):
            matched.append(f"category:{category}")
            score += 0.20
            category_found = True
            entity_count += 1

    # ── Co-occurrence bonuses ─────────────────────────────────────────────────
    if len(found_core_topics) >= 2:
        score += 0.15
        matched.append("signal:multi_topic_cooccurrence")

    if manufacturer_found and category_found:
        score += 0.20
        matched.append("signal:manufacturer_category_cooccurrence")

    if manufacturer_found and found_core_topics:
        score += 0.10
        matched.append("signal:manufacturer_topic_cooccurrence")

    # ── GDELT metadata scoring ────────────────────────────────────────────────
    if article.provider == "gdelt" and article.provider_metadata:
        meta = json.dumps(article.provider_metadata).lower()
        for keyword, weight, topic in _topic_keywords():
            if keyword in meta and f"{topic}:{keyword}" not in matched:
                matched.append(f"metadata:{topic}:{keyword}")
                score += 0.12 * weight

        if "event_code" in article.provider_metadata:
            event_code = str(article.provider_metadata.get("event_code", "")).upper()
            if event_code in {"IN02", "IN03", "IN04", "EX01", "EX02"}:
                score += 0.15
                matched.append(f"metadata:gdelt_event_code:{event_code}")

    # ── Context quality bonus ─────────────────────────────────────────────────
    if entity_count >= 2 or (manufacturer_found and _has_supply_chain_context(text)):
        score += 0.10
        matched.append("signal:strong_context")

    score = min(1.0, score)

    if not matched:
        if _has_supply_chain_context(text):
            return 0.15, [], "has_context_no_direct_match"
        return 0.12, [], "no_keyword_or_entity_match"

    return score, matched, "keyword_entity_score"


def filter_articles(
    articles: list[RawArticle],
) -> tuple[list[EnrichedArticle], list[PrefilterDropRecord]]:
    """Apply relevance pre-filter and return kept articles plus drop audit log."""
    kept: list[EnrichedArticle] = []
    drops: list[PrefilterDropRecord] = []

    for article in articles:
        score, matched_terms, reason = score_article_relevance(article)
        rule = _provider_rule(article.provider)
        min_score = float(rule.get("min_score", settings.relevance_min_score))
        passed = score >= min_score

        if passed:
            kept.append(
                EnrichedArticle(
                    article=article,
                    is_relevant=True,
                    relevance_score=round(score, 4),
                )
            )
        else:
            drops.append(
                PrefilterDropRecord(
                    article_id=article.article_id,
                    provider=article.provider,
                    title=article.title,
                    url=article.url,
                    relevance_score=round(score, 4),
                    min_score_required=min_score,
                    matched_terms=matched_terms,
                    drop_reason=reason,
                )
            )

    return kept, drops


def write_drop_audit(
    drops: list[PrefilterDropRecord], path: Path | None = None
) -> Path | None:
    """Persist drop audit log to JSON for analyst review."""
    if not drops:
        return None
    output = path or (settings.project_root / settings.prefilter_drops_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "drop_count": len(drops),
        "drops": [record.model_dump(mode="json") for record in drops],
    }
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output
