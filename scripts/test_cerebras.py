"""Quick Cerebras connectivity check."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from services.llm_client import chat_completion, chat_completion_json

if __name__ == "__main__":
    print(f"provider={settings.llm_provider} model={settings.cerebras_model}")
    print(
        "text:",
        chat_completion(
            messages=[{"role": "user", "content": "Why is fast inference important?"}],
            max_tokens=256,
            temperature=0.2,
        ),
    )
    print(
        "json:",
        chat_completion_json(
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Respond with {"status": "ok"}'},
            ],
            max_tokens=100,
            temperature=0.1,
        ),
    )
