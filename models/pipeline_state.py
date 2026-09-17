import operator
from typing import Annotated, TypedDict

from  models import schemas


class PipelineState(TypedDict):
    """LangGraph state for the News Intelligence Pipeline."""

    # Run metadata
    run_id: str
    pipeline_version: str

    # Stage 1: ingestion
    raw_articles: list[schemas.RawArticle]
    fetch_live: bool

    # Stage 2–7: enriched articles flowing through pipeline
    enriched_articles: list[schemas.EnrichedArticle]
    filtered_out_count: int
    prefilter_drops: list[schemas.PrefilterDropRecord]

    # Stage 7: clustering
    cluster_map: dict[str, list[str]]  # cluster_id -> article_ids

    # Stage 8–10: final output
    risk_events: list[schemas.RiskEvent]
    review_queue: list[schemas.RiskEvent]
    persistence_summary: dict

    # Audit trail
    audit_log: Annotated[list[schemas.ProcessingStageAudit], operator.add]

    # Error tracking
    errors: list[str]
