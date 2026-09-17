"""Persistence backend selection — Supabase REST (HTTPS) or direct Postgres."""

from __future__ import annotations

from config.settings import settings
from db.postgres import postgres_available


def supabase_rest_available() -> bool:
    """True when Supabase REST credentials are configured."""
    return bool(settings.supabase_url and settings.supabase_key)


def persistence_available() -> bool:
    """True when any persistence backend is configured."""
    return supabase_rest_available() or postgres_available()


def preferred_persistence_backend() -> str:
    """Return ``supabase_rest`` or ``postgres`` based on configuration."""
    if supabase_rest_available():
        return "supabase_rest"
    if postgres_available():
        return "postgres"
    return "none"
