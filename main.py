"""CLI entry point for the News Intelligence Pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical import entity_registry
from config.logging_config import configure_logging
from config.settings import settings
from graph import pipeline_graph
from models import schemas


def _sample_articles() -> list[schemas.RawArticle]:
    """Stub sample for dry-run without live API calls."""
    return [
        schemas.RawArticle(
            provider="stub",
            title="Texas Instruments fab reports production halt in Taiwan",
            body="A manufacturing facility linked to semiconductor supply chains paused output.",
            url="https://example.com/stub-article-1",
            reliability_tier=3,
            retrieved_at=datetime.now(timezone.utc),
        )
    ]


def run_pipeline(dry_run: bool = False, ingest: bool = False) -> dict:
    graph = pipeline_graph.build_pipeline_graph()
    initial = pipeline_graph.create_initial_state(
        raw_articles=_sample_articles() if dry_run else [],
        pipeline_version=settings.pipeline_version,
        fetch_live=ingest,
    )
    return graph.invoke(initial)


def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(description="NexusFlow AI — News Intelligence Pipeline")
    parser.add_argument(
        "--build-entities",
        action="store_true",
        help="Generate canonical_entities.json from the supply chain database",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Apply PostgreSQL migrations (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline with stub sample articles (no API calls)",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Fetch live articles from enabled providers, then run pipeline",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write RiskEvent JSON output to file",
    )
    parser.add_argument(
        "--backfill-supabase",
        action="store_true",
        help="Recompute and save linked_entities + supply_chain_links for all Supabase events",
    )
    parser.add_argument(
        "--backfill-dry-run",
        action="store_true",
        help="With --backfill-supabase, report counts without writing",
    )
    args = parser.parse_args()

    if args.backfill_supabase:
        from services.event_storage import backfill_supabase_events

        summary = backfill_supabase_events(dry_run=args.backfill_dry_run)
        print(json.dumps(summary, indent=2))
        return

    if args.backfill_dry_run:
        parser.error("--backfill-dry-run requires --backfill-supabase")

    if args.build_entities:
        path = entity_registry.write_canonical_entities()
        print(json.dumps({"status": "ok", "canonical_entities_path": str(path)}, indent=2))
        return

    if args.migrate:
        from db.migrate import run_migrations

        applied = run_migrations()
        print(json.dumps(applied, indent=2))
        if applied.get("status") == "action_required":
            sys.exit(1)
        return

    if args.dry_run and args.ingest:
        parser.error("Use either --dry-run or --ingest, not both")

    result = run_pipeline(dry_run=args.dry_run, ingest=args.ingest)
    output = {
        "run_id": result["run_id"],
        "pipeline_version": result["pipeline_version"],
        "filtered_out_count": result.get("filtered_out_count", 0),
        "prefilter_drop_count": len(result.get("prefilter_drops", [])),
        "prefilter_drops": [d.model_dump(mode="json") for d in result.get("prefilter_drops", [])],
        "risk_events": [e.to_machine_output() for e in result["risk_events"]],
        "review_queue_count": len(result["review_queue"]),
        "persistence_summary": result.get("persistence_summary", {}),
        "audit_stages": [a.model_dump(mode="json") for a in result["audit_log"]],
        "errors": result["errors"],
    }

    text = json.dumps(output, indent=2, default=str)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "ok", "output": str(args.output)}, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
