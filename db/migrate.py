"""Schema setup — direct Postgres migrations or Supabase REST verification."""

from __future__ import annotations

import logging
from pathlib import Path

from db.persistence_backend import postgres_available, supabase_rest_available
from db.postgres import get_connection

logger = logging.getLogger("news_agent.db.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_FILE = MIGRATIONS_DIR / "001_risk_intelligence_schema.sql"


def _ensure_migrations_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def _applied_versions(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _run_postgres_migrations(migrations_dir: Path | None = None) -> list[str]:
    directory = migrations_dir or MIGRATIONS_DIR
    files = sorted(directory.glob("*.sql"))
    applied: list[str] = []

    with get_connection() as conn:
        _ensure_migrations_table(conn)
        done = _applied_versions(conn)

        for path in files:
            version = path.name
            if version in done:
                logger.info("Skipping already applied migration: %s", version)
                continue

            sql = path.read_text(encoding="utf-8")
            logger.info("Applying migration: %s", version)
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            applied.append(version)

    return applied


def run_migrations(migrations_dir: Path | None = None) -> dict:
    """
    Apply or verify intelligence schema.

    - Direct Postgres (DATABASE_URL): runs SQL migration files.
    - Supabase REST only: verifies tables exist; DDL must be run once in
      Supabase SQL Editor (HTTPS — no Postgres port required).
    """
    if postgres_available():
        try:
            applied = _run_postgres_migrations(migrations_dir)
            return {
                "status": "ok",
                "backend": "postgres",
                "applied_migrations": applied,
            }
        except Exception as exc:
            logger.warning("Direct Postgres migration failed: %s", exc)
            if not supabase_rest_available():
                raise

    if supabase_rest_available():
        from services.event_persistence_supabase import verify_intelligence_schema

        schema = verify_intelligence_schema()
        if schema.get("schema_ready"):
            return {
                "status": "ok",
                "backend": "supabase_rest",
                "schema_ready": True,
                "message": "Intelligence tables verified via Supabase REST.",
            }

        migration_file = schema.get("migration_file", "001_risk_intelligence_schema.sql")
        sql_path = str((MIGRATIONS_DIR / migration_file).resolve())
        return {
            "status": "action_required",
            "backend": "supabase_rest",
            "schema_ready": False,
            "missing_tables": schema.get("missing_tables", []),
            "message": schema.get("message"),
            "migration_sql_path": sql_path,
            "instructions": [
                "Open Supabase Dashboard -> SQL Editor",
                f"Paste and run the contents of: {sql_path}",
                "Then re-run: python main.py --migrate",
            ],
        }

    raise RuntimeError(
        "No database backend configured. Set SUPABASE_URL + SUPABASE_KEY "
        "or DATABASE_URL in .env"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_migrations())
