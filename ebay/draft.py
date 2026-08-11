"""Build reviewable eBay drafts from downloaded Poshmark listings."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ebay.category_mapping import suggest_ebay_category


EBAY_TITLE_LIMIT = 80
EBAY_DESCRIPTION_LIMIT = 4000


@dataclass(frozen=True)
class EbayDraft:
    source_listing_id: str
    sku: str
    title: str
    description: str
    price: str
    quantity: int
    condition: str | None
    aspects: dict[str, list[str]]
    image_paths: list[str]
    image_urls: list[str]
    marketplace_id: str = "EBAY_US"
    category_id: str | None = None
    category_suggestion: str | None = None
    merchant_location_key: str | None = None
    payment_policy_id: str | None = None
    fulfillment_policy_id: str | None = None
    return_policy_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def ready_for_review(self) -> bool:
        return not any(
            blocker.startswith("Source data:")
            for blocker in self.blockers
        )

    @property
    def ready_to_publish(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ready_for_review"] = self.ready_for_review
        payload["ready_to_publish"] = self.ready_to_publish
        return payload


class EbayDraftBuilder:
    """Create an offline eBay draft without performing network actions."""

    APPAREL_CATEGORY_IDS = {
        "3009", "11484", "11514", "11554", "155183", "155226",
        "169001", "260011", "45279", "53159", "63855", "63861",
        "63862", "63863", "63866", "63867",
    }
    SHOE_CATEGORY_IDS = {
        "11498", "11504", "11505", "11632", "155202", "24087",
        "45333", "53120", "53548", "53557", "55793", "62107",
        "95672",
    }
    ORIGINAL_PACKAGING_PATTERNS = (
        "brand new in box",
        "new in box",
        "new with box",
        "original box",
        "factory sealed",
        "sealed package",
        "unopened",
        "bnib",
        "nib",
    )

    CONDITION_MAP = {
        "new with tags": "NEW",
        "new without tags": "NEW_OTHER",
        "new": "NEW_OTHER",
        "good used condition": "USED_EXCELLENT",
        "good": "USED_EXCELLENT",
        "used": "USED_EXCELLENT",
        "like new": "PRE_OWNED_EXCELLENT",
    }

    def build(
        self,
        listing: dict[str, Any],
        listing_dir: Path,
        *,
        category_id: str | None = None,
        merchant_location_key: str | None = None,
        payment_policy_id: str | None = None,
        fulfillment_policy_id: str | None = None,
        return_policy_id: str | None = None,
        condition_override: str | None = None,
    ) -> EbayDraft:
        blockers: list[str] = []
        warnings: list[str] = []

        listing_id = str(listing.get("listing_id", "")).strip()
        if not listing_id:
            blockers.append("Source data: listing_id is required.")

        title = self._clean_text(listing.get("title"))
        if not title:
            blockers.append("Source data: title is required.")
        elif len(title) > EBAY_TITLE_LIMIT:
            blockers.append(
                f"Source data: title exceeds eBay's {EBAY_TITLE_LIMIT}-character limit."
            )

        description = self._clean_text(listing.get("description"), multiline=True)
        if not description:
            blockers.append("Source data: description is required.")
        elif len(description) > EBAY_DESCRIPTION_LIMIT:
            blockers.append(
                "Source data: description exceeds eBay's "
                f"{EBAY_DESCRIPTION_LIMIT}-character limit."
            )

        price = self._parse_price(listing.get("price"))
        if price is None:
            blockers.append("Source data: price must be a positive amount.")
            price_text = ""
        else:
            price_text = f"{price:.2f}"

        condition_text = self._clean_text(listing.get("condition")).casefold()
        condition = self._optional_text(condition_override) or self._map_condition(
            condition_text,
            category_id=category_id,
            title=title,
            description=description,
        )
        if condition is None:
            blockers.append(
                "Configuration: condition requires an explicit eBay mapping."
            )
        elif condition.startswith("USED"):
            warnings.append(
                "Confirm the used-condition value against the selected eBay category."
            )

        image_paths = self._image_paths(listing_dir)
        if not image_paths:
            blockers.append("Source data: at least one local image is required.")
        image_urls = self._image_urls(listing.get("image_urls"))

        aspects = self._aspects(listing)
        category_suggestion = suggest_ebay_category(
            str(listing.get("category", ""))
        )
        if category_suggestion is None:
            warnings.append(
                "No eBay category suggestion is available for the source category."
            )

        required_configuration = (
            (category_id, "eBay category ID"),
            (merchant_location_key, "merchant location key"),
            (payment_policy_id, "payment policy ID"),
            (fulfillment_policy_id, "fulfillment policy ID"),
            (return_policy_id, "return policy ID"),
        )
        for value, label in required_configuration:
            if not str(value or "").strip():
                blockers.append(f"Configuration: {label} is required.")

        if self._looks_mojibake(title) or self._looks_mojibake(description):
            warnings.append(
                "Source text may contain encoding artifacts and should be reviewed."
            )

        return EbayDraft(
            source_listing_id=listing_id,
            sku=f"POSH-{listing_id}" if listing_id else "",
            title=title,
            description=description,
            price=price_text,
            quantity=1,
            condition=condition,
            aspects=aspects,
            image_paths=image_paths,
            image_urls=image_urls,
            category_id=self._optional_text(category_id),
            category_suggestion=category_suggestion,
            merchant_location_key=self._optional_text(merchant_location_key),
            payment_policy_id=self._optional_text(payment_policy_id),
            fulfillment_policy_id=self._optional_text(fulfillment_policy_id),
            return_policy_id=self._optional_text(return_policy_id),
            warnings=warnings,
            blockers=blockers,
        )

    @classmethod
    def _map_condition(
        cls,
        condition_text: str,
        *,
        category_id: str | None,
        title: str,
        description: str,
    ) -> str | None:
        mapped = cls.CONDITION_MAP.get(condition_text)
        if condition_text != "new with tags" or mapped is None:
            return mapped

        category = str(category_id or "").strip()
        if not category or category in cls.APPAREL_CATEGORY_IDS:
            return mapped

        evidence = f" {title} {description} ".casefold()
        has_original_packaging = any(
            pattern in evidence
            for pattern in cls.ORIGINAL_PACKAGING_PATTERNS
        )
        if category in cls.SHOE_CATEGORY_IDS or category:
            return "NEW" if has_original_packaging else "NEW_OTHER"
        return mapped

    @staticmethod
    def _clean_text(value: Any, *, multiline: bool = False) -> str:
        text = str(value or "").replace("\u205f", " ").replace("\u00a0", " ")
        if multiline:
            return "\n".join(
                re.sub(r"[ \t]+", " ", line).strip()
                for line in text.splitlines()
            ).strip()
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _parse_price(value: Any) -> Decimal | None:
        cleaned = re.sub(r"[^0-9.]", "", str(value or ""))
        try:
            price = Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
        return price if price > 0 else None

    @staticmethod
    def _image_paths(listing_dir: Path) -> list[str]:
        paths: list[Path] = []
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            paths.extend(listing_dir.glob(pattern))
        return [str(path.resolve()) for path in sorted(set(paths))]

    @staticmethod
    def _image_urls(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            text
            for item in value
            if (text := str(item or "").strip()).startswith("https://")
        ]

    @classmethod
    def _aspects(cls, listing: dict[str, Any]) -> dict[str, list[str]]:
        aspects: dict[str, list[str]] = {}
        for source_key, aspect_name in (
            ("brand", "Brand"),
            ("size", "Size"),
            ("color", "Color"),
        ):
            value = cls._clean_text(listing.get(source_key))
            if value:
                aspects[aspect_name] = [value]

        colors = listing.get("colors")
        if isinstance(colors, list):
            cleaned = [cls._clean_text(value) for value in colors]
            cleaned = [value for value in cleaned if value]
            if cleaned:
                aspects["Color"] = cleaned
        return aspects

    @staticmethod
    def _looks_mojibake(value: str) -> bool:
        return any(marker in value for marker in ("Â", "â", "Ã", "�"))
