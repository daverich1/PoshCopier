"""Build a non-publishing eBay Inventory API request preview."""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any

from ebay.draft import EbayDraft


@dataclass(frozen=True)
class EbayInventoryRequestPreview:
    method: str
    url: str
    headers: dict[str, str]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "headers": dict(self.headers),
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class EbayInventoryPayloadBuilder:
    """Create the exact unpublished inventory-item payload; never send it."""

    def build_payload(self, draft: EbayDraft) -> dict[str, Any]:
        missing = []
        for value, label in (
            (draft.sku, "SKU"),
            (draft.title, "title"),
            (draft.description, "description"),
            (draft.condition, "condition"),
        ):
            if not value:
                missing.append(label)
        if draft.quantity < 0:
            raise ValueError("Inventory quantity cannot be negative.")
        if not draft.image_urls:
            missing.append("at least one HTTPS image URL")
        if missing:
            raise ValueError(
                "Cannot preview eBay inventory payload; missing " + ", ".join(missing) + "."
            )
        if any(not value.startswith("https://") for value in draft.image_urls):
            raise ValueError("Every eBay inventory image URL must use HTTPS.")

        return {
            "availability": {
                "shipToLocationAvailability": {"quantity": draft.quantity}
            },
            "condition": draft.condition,
            "product": {
                "title": draft.title,
                "description": draft.description,
                "aspects": draft.aspects,
                "imageUrls": draft.image_urls,
            },
        }

    def preview(self, draft: EbayDraft, environment: str = "sandbox") -> EbayInventoryRequestPreview:
        if environment not in ("sandbox", "production"):
            raise ValueError("environment must be sandbox or production")
        root = (
            "https://api.sandbox.ebay.com"
            if environment == "sandbox"
            else "https://api.ebay.com"
        )
        sku = urllib.parse.quote(draft.sku, safe="")
        return EbayInventoryRequestPreview(
            method="PUT",
            url=f"{root}/sell/inventory/v1/inventory_item/{sku}",
            headers={
                "Authorization": "Bearer <USER_TOKEN_REDACTED>",
                "Content-Type": "application/json",
                "Content-Language": "en-US",
            },
            payload=self.build_payload(draft),
        )
