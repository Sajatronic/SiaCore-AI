"""Tests for shared LLM client and settings normalization."""

from unittest.mock import patch

from config.settings import Settings
from services.llm_client import (
    chat_completion_json,
    chat_completions_url,
    parse_retry_after_seconds,
)


def test_chat_completions_url_appends_path():
    assert (
        chat_completions_url("https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    )


def test_settings_auto_fix_model_url_to_base_url():
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_model="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    assert settings.llm_base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert settings.openrouter_model == "qwen-plus"


def test_settings_gemini_openrouter_model_id_stripped():
    settings = Settings(
        openrouter_api_key="test-key",
        openrouter_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        openrouter_model="google/gemini-2.0-flash",
    )
    assert settings.openrouter_model == "gemini-2.0-flash"
    assert settings.llm_base_url.endswith("/openai")


def test_parse_retry_after_seconds():
    body = (
        'Rate limit reached ... Please try again in 23.06s. Need more tokens?'
    )
    assert parse_retry_after_seconds(body) == 23.06


def test_chat_completion_json_parses_response():
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": '{"matches": [{"canonical_id": "m1"}]}',
                }
            }
        ]
    }

    with patch("services.llm_client.chat_completion", return_value='{"matches": []}'):
        parsed = chat_completion_json(
            messages=[{"role": "user", "content": "hello"}],
        )
    assert parsed == {"matches": []}


def test_cerebras_provider_routes_to_sdk():
    settings = Settings(
        llm_provider="cerebras",
        cerebras_api_key="test-cerebras-key",
        cerebras_model="gemma-4-31b",
    )

    class FakeMessage:
        content = "hello from cerebras"

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "gemma-4-31b"
            assert kwargs["reasoning_effort"] == "medium"
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    with patch("config.settings.settings", settings):
        with patch("cerebras.cloud.sdk.Cerebras", return_value=FakeClient()):
            from services.llm_client import chat_completion

            result = chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert result == "hello from cerebras"
