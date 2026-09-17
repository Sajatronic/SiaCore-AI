"""Shared async HTTP client with retry for news providers."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class ProviderHttpError(Exception):
    """Raised when a provider HTTP request fails after retries."""

    def __init__(self, provider: str, message: str, status_code: int | None = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


async def fetch_json(
    client: httpx.AsyncClient,
    *,
    provider: str,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
) -> Any:
    """GET JSON with exponential backoff on transient failures."""
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise httpx.HTTPStatusError(
                    f"Transient HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_backoff_seconds * (2**attempt))

    status_code = getattr(getattr(last_error, "response", None), "status_code", None)
    raise ProviderHttpError(provider, str(last_error), status_code=status_code)
