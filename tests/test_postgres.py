"""Tests for PostgreSQL connection string normalization."""

from db.postgres import _normalize_connection_string


def test_strips_pgbouncer_param_without_urlparse():
    raw = (
        "postgresql://postgres.project:pa[ss]word@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        "?pgbouncer=true"
    )
    normalized = _normalize_connection_string(raw)
    assert normalized == (
        "postgresql://postgres.project:pa[ss]word@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
    )


def test_strips_surrounding_quotes():
    raw = '"postgresql://user:pass@host:5432/db"'
    assert _normalize_connection_string(raw) == "postgresql://user:pass@host:5432/db"
