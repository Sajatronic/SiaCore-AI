"""Canonical entity registry loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import settings


class EntityRegistry:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.suppliers = data.get("suppliers", {})
        self.manufacturers = data.get("manufacturers", {})
        self.components = data.get("components", {})
        self.regions = data.get("regions", [])

    @classmethod
    def load(cls, path: Path | None = None) -> EntityRegistry:
        registry_path = path or (settings.project_root / settings.canonical_entities_path)
        if not registry_path.exists():
            raise FileNotFoundError(
                f"Canonical entities not found at {registry_path}. "
                "Run: python -m news_agent.canonical.entity_registry"
            )
        return cls(json.loads(registry_path.read_text(encoding="utf-8")))
