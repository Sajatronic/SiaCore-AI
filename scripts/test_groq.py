"""Quick Groq connectivity check."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/test_groq.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.llm_client import chat_completion, chat_completion_json

if __name__ == "__main__":
    print("text:", chat_completion(messages=[{"role": "user", "content": "Hello"}], max_tokens=50))
    print(
        "json:",
        chat_completion_json(
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Respond with {"status": "ok"}'},
            ],
            max_tokens=100,
        ),
    )
