"""Database access: Supabase REST (catalog + persistence) and optional direct Postgres."""

from db.persistence_backend import (
    persistence_available,
    preferred_persistence_backend,
    supabase_rest_available,
)
from db.postgres import get_connection, get_connection_string, postgres_available
from db.supabase import (
    get_client,
    get_manufacturer_aliases,
    get_session,
    query_categories,
    query_inventory_supplier_map,
    query_manufacturers,
    query_parts,
    query_suppliers,
)

__all__ = [
    "get_client",
    "get_session",
    "get_manufacturer_aliases",
    "query_suppliers",
    "query_manufacturers",
    "query_parts",
    "query_inventory_supplier_map",
    "query_categories",
    "get_connection",
    "get_connection_string",
    "postgres_available",
    "supabase_rest_available",
    "persistence_available",
    "preferred_persistence_backend",
]
