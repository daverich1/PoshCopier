"""Persist confirmed eBay category IDs by exact Poshmark source category."""

from __future__ import annotations

import json
from pathlib import Path

from runtime_paths import APP_DIR


DEFAULT_CATEGORY_RULES_PATH = APP_DIR / "ebay_category_rules.json"


class EbayCategoryRuleStore:
    def __init__(self, path: Path = DEFAULT_CATEGORY_RULES_PATH) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(source).strip(): str(category_id).strip()
            for source, category_id in payload.items()
            if str(source).strip() and str(category_id).strip().isdigit()
        }

    def save(self, rules: dict[str, str]) -> None:
        cleaned = {
            str(source).strip(): str(category_id).strip()
            for source, category_id in rules.items()
            if str(source).strip() and str(category_id).strip().isdigit()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(dict(sorted(cleaned.items())), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def set_rule(self, source_category: str, category_id: str) -> None:
        source = str(source_category).strip()
        value = str(category_id).strip()
        if not source:
            raise ValueError("A Poshmark source category is required.")
        if not value.isdigit():
            raise ValueError("The eBay category ID must contain digits only.")
        rules = self.load()
        rules[source] = value
        self.save(rules)
