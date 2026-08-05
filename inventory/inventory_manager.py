from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inventory.inventory_item import InventoryItem
from runtime_paths import DOWNLOADS_DIR


class InventoryManager:
    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
    ) -> None:
        self.downloads_dir = downloads_dir

    def load_items(
        self,
    ) -> list[InventoryItem]:
        items: list[InventoryItem] = []

        if not self.downloads_dir.exists():
            return items

        for listing_dir in sorted(
            self.downloads_dir.iterdir(),
            key=lambda path: path.name.lower(),
        ):
            if not listing_dir.is_dir():
                continue

            listing_file = listing_dir / "listing.json"

            if not listing_file.exists():
                continue

            try:
                payload = self._load_json(
                    listing_file
                )
                item = self._build_item(
                    payload,
                    listing_file,
                    listing_dir,
                )
            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ):
                continue

            items.append(item)

        return items

    def _load_json(
        self,
        listing_file: Path,
    ) -> dict[str, Any]:
        payload = json.loads(
            listing_file.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(payload, dict):
            raise TypeError(
                "Listing JSON must contain an object."
            )

        return payload

    def _build_item(
        self,
        payload: dict[str, Any],
        listing_file: Path,
        listing_dir: Path,
    ) -> InventoryItem:
        listing_id = str(
            payload.get(
                "listing_id",
                listing_dir.name,
            )
        ).strip()

        title = str(
            payload.get(
                "title",
                "",
            )
        ).strip()

        brand = str(
            payload.get(
                "brand",
                "",
            )
        ).strip()

        price = str(
            payload.get(
                "price",
                "",
            )
        ).strip()

        category = str(
            payload.get(
                "category",
                "",
            )
        ).strip()

        size = self._format_sizes(
            payload
        )

        image_path = self._find_first_image(
            listing_dir
        )

        uploaded = bool(
            payload.get(
                "copied",
                False,
            )
        )

        duplicate = bool(
            payload.get(
                "duplicate",
                False,
            )
        )

        failed = bool(
            payload.get(
                "failed",
                False,
            )
        )

        return InventoryItem(
            listing_id=listing_id,
            title=title,
            brand=brand,
            price=price,
            size=size,
            category=category,
            image_path=image_path,
            listing_path=listing_file,
            uploaded=uploaded,
            duplicate=duplicate,
            failed=failed,
        )

    def _format_sizes(
        self,
        payload: dict[str, Any],
    ) -> str:
        sizes = payload.get(
            "sizes"
        )

        if isinstance(
            sizes,
            list,
        ):
            cleaned = [
                str(value).strip()
                for value in sizes
                if str(value).strip()
            ]

            if cleaned:
                return ", ".join(
                    cleaned
                )

        return str(
            payload.get(
                "size",
                "",
            )
        ).strip()

    def _find_first_image(
        self,
        listing_dir: Path,
    ) -> Path | None:
        preferred = (
            listing_dir
            / "image_1.jpg"
        )

        if preferred.exists():
            return preferred

        candidates: list[Path] = []

        for pattern in (
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.webp",
        ):
            candidates.extend(
                listing_dir.glob(
                    pattern
                )
            )

        candidates.sort(
            key=lambda path: path.name.lower()
        )

        return (
            candidates[0]
            if candidates
            else None
        )