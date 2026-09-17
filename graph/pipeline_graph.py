"""LangGraph pipeline assembly."""

from __future__ import annotations

from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from models.pipeline_state import PipelineState
from nodes import (
    dedup_clustering,
    entity_linking,
    event_classification,
    impact_prediction,
    ner_extraction,
    persist_events,
    provenance_attachment,
    relevance_prefilter,
    risk_analysis,
    risk_event_creation,
    severity_estimation,
    source_ingestion,
)


def build_pipeline_graph():
    """Build and compile the News Intelligence Pipeline graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("source_ingestion", source_ingestion)
    graph.add_node("relevance_prefilter", relevance_prefilter)
    graph.add_node("ner_extraction", ner_extraction)
    graph.add_node("entity_linking", entity_linking)
    graph.add_node("event_classification", event_classification)
    graph.add_node("severity_estimation", severity_estimation)
    graph.add_node("dedup_clustering", dedup_clustering)
    graph.add_node("provenance_attachment", provenance_attachment)
    graph.add_node("risk_event_creation", risk_event_creation)
    graph.add_node("risk_analysis", risk_analysis)
    graph.add_node("impact_prediction", impact_prediction)
    graph.add_node("persist_events", persist_events)

    graph.add_edge(START, "source_ingestion")
    graph.add_edge("source_ingestion", "relevance_prefilter")
    graph.add_edge("relevance_prefilter", "ner_extraction")
    graph.add_edge("ner_extraction", "entity_linking")
    graph.add_edge("entity_linking", "event_classification")
    graph.add_edge("event_classification", "severity_estimation")
    graph.add_edge("severity_estimation", "dedup_clustering")
    graph.add_edge("dedup_clustering", "provenance_attachment")
    graph.add_edge("provenance_attachment", "risk_event_creation")
    graph.add_edge("risk_event_creation", "risk_analysis")
    graph.add_edge("risk_analysis", "impact_prediction")
    graph.add_edge("impact_prediction", "persist_events")
    graph.add_edge("persist_events", END)

    return graph.compile()


def create_initial_state(
    raw_articles: list | None = None,
    pipeline_version: str = "0.1.0",
    fetch_live: bool = False,
) -> PipelineState:
    return PipelineState(
        run_id=str(uuid4()),
        pipeline_version=pipeline_version,
        raw_articles=raw_articles or [],
        fetch_live=fetch_live,
        enriched_articles=[],
        filtered_out_count=0,
        prefilter_drops=[],
        cluster_map={},
        risk_events=[],
        review_queue=[],
        persistence_summary={},
        audit_log=[],
        errors=[],
    )
