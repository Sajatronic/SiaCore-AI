"""Shared LLM client — OpenAI-compatible HTTP (Groq, Gemini, OpenRouter) or Cerebras SDK."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger("news_agent.services.llm_client")

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_RETRYABLE_STATUS = {429, 503, 529}
_llm_semaphore: threading.Semaphore | None = None
_last_request_at = 0.0
_request_lock = threading.Lock()


def chat_completions_url(base_url: str | None = None) -> str:
    """Build the /chat/completions endpoint from a configurable base URL."""
    base = (base_url or settings.llm_base_url).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def llm_configured() -> bool:
    if settings.uses_cerebras:
        return bool(settings.cerebras_api_key.strip())
    return bool(settings.openrouter_api_key.strip())


def llm_parallel_workers() -> int:
    """Max worker threads for pipeline stages that call the LLM."""
    return max(1, settings.llm_parallel_workers)


def parse_retry_after_seconds(body: str) -> float | None:
    """Parse provider hints like 'Please try again in 12.5s' from error bodies."""
    match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", body, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def is_rate_limit_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "429" in message or "rate_limit" in message or "rate limit" in message


def _get_semaphore() -> threading.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = threading.Semaphore(max(1, settings.llm_max_concurrent))
    return _llm_semaphore


def reset_llm_client_state() -> None:
    """Reset throttling state (used in tests)."""
    global _llm_semaphore, _last_request_at
    _llm_semaphore = None
    _last_request_at = 0.0


def _throttle_before_request() -> None:
    global _last_request_at
    min_interval = settings.llm_min_request_interval_seconds
    if min_interval <= 0:
        return
    with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_request_at = time.monotonic()


def _request_headers() -> dict[str, str]:
    api_key = settings.openrouter_api_key.strip()
    if not api_key:
        raise ValueError("LLM API key is not configured (OPENROUTER_API_KEY)")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in settings.llm_base_url:
        headers["HTTP-Referer"] = "https://github.com/NexusFlow-AI"
        headers["X-Title"] = "NexusFlow News Agent"
    return headers


def _cerebras_completion(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> str:
    from cerebras.cloud.sdk import Cerebras

    api_key = settings.cerebras_api_key.strip()
    if not api_key:
        raise ValueError("CEREBRAS_API_KEY is not configured")

    client = Cerebras(api_key=api_key)
    max_attempts = max(1, settings.llm_max_retries + 1)

    for attempt in range(1, max_attempts + 1):
        with _get_semaphore():
            _throttle_before_request()
            try:
                completion = client.chat.completions.create(
                    messages=messages,
                    model=settings.cerebras_model,
                    max_completion_tokens=max_tokens,
                    temperature=temperature,
                    top_p=settings.cerebras_top_p,
                    stream=False,
                    reasoning_effort=settings.cerebras_reasoning_effort,
                )
            except Exception as exc:
                if is_rate_limit_error(exc) and attempt < max_attempts:
                    wait_seconds = min(2.0 ** attempt, 30.0)
                    logger.warning(
                        "Cerebras rate limited, retry %d/%d in %.1fs: %s",
                        attempt,
                        settings.llm_max_retries,
                        wait_seconds,
                        exc,
                    )
                    time.sleep(wait_seconds)
                    continue
                raise

        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise ValueError(f"No choices in Cerebras response: {completion}")

        message = choices[0].message
        content = getattr(message, "content", None) or ""
        if not content:
            raise ValueError("Empty content in Cerebras response")
        return content

    raise RuntimeError("Cerebras request failed after retries")


def chat_completion(
    *,
    messages: list[dict[str, str]],
    response_format: dict[str, str] | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.1,
    timeout: float = 30.0,
) -> str:
    """Call the configured LLM provider and return assistant message content."""
    if settings.uses_cerebras:
        if response_format is not None:
            logger.debug("Cerebras SDK ignores response_format; relying on prompt JSON instructions")
        return _cerebras_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    return _openai_compatible_completion(
        messages=messages,
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )


def _openai_compatible_completion(
    *,
    messages: list[dict[str, str]],
    response_format: dict[str, str] | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.1,
    timeout: float = 30.0,
) -> str:
    """Call the configured LLM provider and return assistant message content."""
    payload: dict[str, Any] = {
        "model": settings.openrouter_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    url = chat_completions_url()
    headers = _request_headers()
    max_attempts = max(1, settings.llm_max_retries + 1)

    for attempt in range(1, max_attempts + 1):
        with _get_semaphore():
            _throttle_before_request()
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            response_data = resp.json()
            choices = response_data.get("choices")
            if not choices:
                raise ValueError(f"No choices in LLM response: {response_data}")

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("Empty content in LLM response")
            return content

        if resp.status_code in _RETRYABLE_STATUS and attempt < max_attempts:
            wait_seconds = parse_retry_after_seconds(resp.text) or min(2.0 ** attempt, 30.0)
            wait_seconds = min(wait_seconds + 0.5, 60.0)
            logger.warning(
                "LLM rate limited (%s), retry %d/%d in %.1fs",
                resp.status_code,
                attempt,
                settings.llm_max_retries,
                wait_seconds,
            )
            time.sleep(wait_seconds)
            continue

        provider = settings.llm_base_url
        raise ValueError(
            f"LLM API returned {resp.status_code} ({provider}): {resp.text}"
        )

    raise RuntimeError("LLM request failed after retries")


def chat_completion_json(
    *,
    messages: list[dict[str, str]],
    max_tokens: int = 1500,
    temperature: float = 0.1,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Request JSON output and parse the assistant message."""
    content = chat_completion(
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    return json.loads(_clean_json_response(content))


def _clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[len("```json") :]
    if text.startswith("```"):
        text = text[len("```") :]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
