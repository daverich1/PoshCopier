"""Persistence for non-secret eBay crosslisting settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime_paths import APP_DIR


DEFAULT_SETTINGS_PATH = APP_DIR / "ebay_settings.json"


@dataclass(frozen=True)
class EbaySettings:
    marketplace_id: str = "EBAY_US"
    api_environment: str = "sandbox"
    merchant_location_key: str = ""
    payment_policy_id: str = ""
    fulfillment_policy_id: str = ""
    return_policy_id: str = ""

    def missing_fields(self) -> list[str]:
        fields = (
            (self.merchant_location_key, "Merchant location key"),
            (self.payment_policy_id, "Payment policy ID"),
            (self.fulfillment_policy_id, "Fulfillment policy ID"),
            (self.return_policy_id, "Return policy ID"),
        )
        return [label for value, label in fields if not value.strip()]


class EbaySettingsStore:
    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.path = path

    def load(self) -> EbaySettings:
        if not self.path.exists():
            return EbaySettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return EbaySettings()
        if not isinstance(payload, dict):
            return EbaySettings()
        return EbaySettings(
            marketplace_id=str(payload.get("marketplace_id", "EBAY_US")).strip()
            or "EBAY_US",
            api_environment=(
                str(payload.get("api_environment", "sandbox")).strip()
                if str(payload.get("api_environment", "sandbox")).strip()
                in ("sandbox", "production")
                else "sandbox"
            ),
            merchant_location_key=str(
                payload.get("merchant_location_key", "")
            ).strip(),
            payment_policy_id=str(payload.get("payment_policy_id", "")).strip(),
            fulfillment_policy_id=str(
                payload.get("fulfillment_policy_id", "")
            ).strip(),
            return_policy_id=str(payload.get("return_policy_id", "")).strip(),
        )

    def save(self, settings: EbaySettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(asdict(settings), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
