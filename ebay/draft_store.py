"""Persist per-listing eBay review choices separately from source data."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime_paths import APP_DIR


DEFAULT_DRAFTS_DIR = APP_DIR / "ebay_drafts"


@dataclass(frozen=True)
class EbayDraftReview:
    source_listing_id: str
    category_id: str = ""
    condition: str = ""


class EbayDraftReviewStore:
    def __init__(self, drafts_dir: Path = DEFAULT_DRAFTS_DIR) -> None:
        self.drafts_dir = drafts_dir

    def path_for(self, listing_id: str) -> Path:
        safe_id = "".join(
            character
            for character in str(listing_id)
            if character.isalnum() or character in ("-", "_")
        )
        if not safe_id:
            raise ValueError("A valid source listing ID is required.")
        return self.drafts_dir / f"{safe_id}.json"

    def load(self, listing_id: str) -> EbayDraftReview:
        path = self.path_for(listing_id)
        if not path.exists():
            return EbayDraftReview(source_listing_id=listing_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return EbayDraftReview(source_listing_id=listing_id)
        if not isinstance(payload, dict):
            return EbayDraftReview(source_listing_id=listing_id)
        return EbayDraftReview(
            source_listing_id=listing_id,
            category_id=str(payload.get("category_id", "")).strip(),
            condition=str(payload.get("condition", "")).strip(),
        )

    def save(self, review: EbayDraftReview) -> Path:
        path = self.path_for(review.source_listing_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(asdict(review), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
        return path
