"""Basic pipeline integration test."""

from graph.pipeline_graph import build_pipeline_graph, create_initial_state
from models.schemas import RawArticle


def test_pipeline_dry_run():
    graph = build_pipeline_graph()
    state = create_initial_state(
        raw_articles=[
            RawArticle(provider="test", title="Stub event", body="Semiconductor supply disruption")
        ]
    )
    result = graph.invoke(state)
    assert result["run_id"]
    assert len(result["audit_log"]) == 12
    assert len(result["risk_events"]) == 1
    event = result["risk_events"][0]
    assert event.title == "Stub event"
    assert event.event_category.value in {"other", "factory_shutdown", "logistics_disruption"}
    assert event.provenance_information.pipeline_version
    stages = [audit.stage for audit in result["audit_log"]]
    assert "risk_analysis" in stages
    assert "impact_prediction" in stages
