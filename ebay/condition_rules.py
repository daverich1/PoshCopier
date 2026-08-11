"""Persist reviewed eBay conditions by source category and condition."""

from __future__ import annotations

import json
from pathlib import Path

from runtime_paths import APP_DIR


DEFAULT_CONDITION_RULES_PATH = APP_DIR / "ebay_condition_rules.json"
SUPPORTED_EBAY_CONDITIONS = (
    "NEW",
    "NEW_OTHER",
    "NEW_WITH_DEFECTS",
    "PRE_OWNED_EXCELLENT",
    "PRE_OWNED_FAIR",
    "USED_EXCELLENT",
    "USED_VERY_GOOD",
    "USED_GOOD",
    "USED_ACCEPTABLE",
)


def condition_rule_key(source_category: str, source_condition: str) -> str:
    return f"{str(source_category).strip()}\u001f{str(source_condition).strip()}"


class EbayConditionRuleStore:
    def __init__(self, path: Path = DEFAULT_CONDITION_RULES_PATH) -> None:
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
            str(key): str(value).strip()
            for key, value in payload.items()
            if str(value).strip() in SUPPORTED_EBAY_CONDITIONS
        }

    def get_rule(self, source_category: str, source_condition: str) -> str:
        return self.load().get(
            condition_rule_key(source_category, source_condition),
            "",
        )

    def set_rule(
        self,
        source_category: str,
        source_condition: str,
        ebay_condition: str,
    ) -> None:
        if not str(source_category).strip() or not str(source_condition).strip():
            raise ValueError("Source category and condition are required.")
        condition = str(ebay_condition).strip()
        if condition not in SUPPORTED_EBAY_CONDITIONS:
            raise ValueError("Select a supported eBay condition.")
        rules = self.load()
        rules[condition_rule_key(source_category, source_condition)] = condition
        self._save(rules)

    def _save(self, rules: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(dict(sorted(rules.items())), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
