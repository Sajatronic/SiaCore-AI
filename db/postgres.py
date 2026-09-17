"""Direct PostgreSQL access for migrations and risk-event persistence.

Uses DATABASE_URL / DB_CONNECTION_STRING (Supabase pooler or direct Postgres).
Catalog reads continue to use Supabase REST in db.py.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Generator
from urllib.parse import parse_qs, urlencode

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

from config.settings import settings

logger = logging.getLogger("news_agent.db.postgres")

# Prisma-style pgbouncer query params break psycopg2.
_STRIP_QUERY_KEYS = {"pgbouncer", "connection_limit"}


def _normalize_connection_string(raw: str) -> str:
    """Return a psycopg2-compatible connection string.

    Avoids urlparse on the full DSN — passwords with ``@``, ``[``, ``]``, etc.
    (common when copied manually into .env) break URL parsing in Python 3.14+.
    Only the query string is parsed; the authority section is left untouched.
    """
    if not raw:
        return ""
    conn_str = raw.strip().strip('"').strip("'")
    if "?" not in conn_str:
        return conn_str

    base, query = conn_str.split("?", 1)
    params = parse_qs(query, keep_blank_values=True)
    for key in _STRIP_QUERY_KEYS:
        params.pop(key, None)
    if not params:
        return base
    new_query = urlencode({k: v[0] for k, v in params.items()}, doseq=False)
    return f"{base}?{new_query}"


@lru_cache(maxsize=1)
def get_connection_string() -> str:
    """Return normalized DATABASE_URL or empty string if unset."""
    return _normalize_connection_string(settings.db_connection_string)


def postgres_available() -> bool:
    """True when a direct Postgres connection string is configured."""
    return bool(get_connection_string())


@contextmanager
def get_connection() -> Generator[PgConnection, None, None]:
    """Open a short-lived PostgreSQL connection."""
    conn_str = get_connection_string()
    if not conn_str:
        raise RuntimeError(
            "DATABASE_URL / DB_CONNECTION_STRING is not set. "
            "Add it to .env (Supabase -> Connect -> ORM tab)."
        )
    conn = psycopg2.connect(conn_str)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    """Run a read query and return rows as dicts."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            return [dict(row) for row in cur.fetchall()]


def execute_write(sql: str, params: tuple[Any, ...] | None = None) -> None:
    """Run a write statement inside a transaction."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
