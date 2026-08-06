from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from runtime_paths import DOWNLOADS_DIR


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

REQUIRED_FIELDS = (
    "title",
    "description",
    "brand",
    "price",
    "category",
    "condition",
    "source_url",
)


@dataclass(frozen=True)
class ListingHealth:
    listing_id: str
    listing_dir: Path
    listing_file: Path

    json_valid: bool
    image_count: int

    missing_fields: tuple[str, ...] = field(
        default_factory=tuple
    )
    problems: tuple[str, ...] = field(
        default_factory=tuple
    )

    title: str = ""
    source_url: str = ""

    @property
    def has_images(self) -> bool:
        return self.image_count > 0

    @property
    def ready_for_upload(self) -> bool:
        return (
            self.json_valid
            and self.has_images
            and not self.missing_fields
            and not self.problems
        )

    @property
    def status(self) -> str:
        if not self.json_valid:
            return "Broken"

        if self.ready_for_upload:
            return "Ready"

        return "Needs Attention"


@dataclass(frozen=True)
class InventoryHealthSummary:
    total: int
    ready: int
    needs_attention: int
    broken: int

    missing_images: int
    missing_category: int
    missing_condition: int
    missing_source_url: int
    invalid_json: int

    reports: tuple[ListingHealth, ...]

    @property
    def healthy_percentage(self) -> float:
        if self.total == 0:
            return 0.0

        return round(
            (self.ready / self.total) * 100,
            1,
        )


class InventoryHealth:
    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
    ) -> None:
        self.downloads_dir = downloads_dir

    def scan_listing(
        self,
        listing_dir: Path,
    ) -> ListingHealth:
        listing_dir = listing_dir.resolve()
        listing_file = listing_dir / "listing.json"

        listing_id = listing_dir.name
        problems: list[str] = []
        missing_fields: list[str] = []

        image_count = self._count_images(
            listing_dir
        )

        if not listing_file.is_file():
            return ListingHealth(
                listing_id=listing_id,
                listing_dir=listing_dir,
                listing_file=listing_file,
                json_valid=False,
                image_count=image_count,
                missing_fields=(),
                problems=("missing_listing_json",),
            )

        try:
            payload = self._load_json(
                listing_file
            )
        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
        ):
            return ListingHealth(
                listing_id=listing_id,
                listing_dir=listing_dir,
                listing_file=listing_file,
                json_valid=False,
                image_count=image_count,
                missing_fields=(),
                problems=("invalid_json",),
            )

        payload_listing_id = str(
            payload.get(
                "listing_id",
                listing_id,
            )
        ).strip()

        if payload_listing_id:
            listing_id = payload_listing_id

        title = str(
            payload.get(
                "title",
                "",
            )
        ).strip()

        source_url = self._source_url(
            payload
        )

        for field_name in REQUIRED_FIELDS:
            if field_name == "source_url":
                value = source_url
            else:
                value = payload.get(
                    field_name
                )

            if self._is_missing(
                value
            ):
                missing_fields.append(
                    field_name
                )

        if not self._has_size(
            payload
        ):
            missing_fields.append(
                "size"
            )

        if image_count == 0:
            problems.append(
                "missing_images"
            )

        return ListingHealth(
            listing_id=listing_id,
            listing_dir=listing_dir,
            listing_file=listing_file,
            json_valid=True,
            image_count=image_count,
            missing_fields=tuple(
                sorted(
                    set(
                        missing_fields
                    )
                )
            ),
            problems=tuple(
                sorted(
                    set(
                        problems
                    )
                )
            ),
            title=title,
            source_url=source_url,
        )

    def scan_inventory(
        self,
    ) -> InventoryHealthSummary:
        reports: list[ListingHealth] = []

        if not self.downloads_dir.exists():
            return InventoryHealthSummary(
                total=0,
                ready=0,
                needs_attention=0,
                broken=0,
                missing_images=0,
                missing_category=0,
                missing_condition=0,
                missing_source_url=0,
                invalid_json=0,
                reports=(),
            )

        for listing_dir in sorted(
            self.downloads_dir.iterdir(),
            key=lambda path: path.name.lower(),
        ):
            if not listing_dir.is_dir():
                continue

            if listing_dir.name in {
                "logs",
                "errors",
                "__pycache__",
            }:
                continue

            if listing_dir.name.endswith(
                "_backup"
            ):
                continue

            reports.append(
                self.scan_listing(
                    listing_dir
                )
            )

        ready = sum(
            report.ready_for_upload
            for report in reports
        )

        broken = sum(
            not report.json_valid
            for report in reports
        )

        needs_attention = (
            len(reports)
            - ready
            - broken
        )

        missing_images = sum(
            "missing_images"
            in report.problems
            for report in reports
        )

        missing_category = sum(
            "category"
            in report.missing_fields
            for report in reports
        )

        missing_condition = sum(
            "condition"
            in report.missing_fields
            for report in reports
        )

        missing_source_url = sum(
            "source_url"
            in report.missing_fields
            for report in reports
        )

        invalid_json = sum(
            (
                "invalid_json"
                in report.problems
            )
            or not report.json_valid
            for report in reports
        )

        return InventoryHealthSummary(
            total=len(reports),
            ready=ready,
            needs_attention=needs_attention,
            broken=broken,
            missing_images=missing_images,
            missing_category=missing_category,
            missing_condition=missing_condition,
            missing_source_url=missing_source_url,
            invalid_json=invalid_json,
            reports=tuple(
                reports
            ),
        )

    def validate_for_upload(
        self,
        listing_dir: Path,
    ) -> ListingHealth:
        return self.scan_listing(
            listing_dir
        )

    def problem_messages(
        self,
        report: ListingHealth,
    ) -> tuple[str, ...]:
        messages: list[str] = []

        if not report.json_valid:
            messages.append(
                "Listing JSON is missing or invalid."
            )

        if (
            "missing_images"
            in report.problems
        ):
            messages.append(
                "No local listing images were found."
            )

        if report.missing_fields:
            messages.append(
                "Missing required fields: "
                + ", ".join(
                    report.missing_fields
                )
                + "."
            )

        return tuple(
            messages
        )

    def _load_json(
        self,
        listing_file: Path,
    ) -> dict[str, Any]:
        payload = json.loads(
            listing_file.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Listing JSON must contain an object."
            )

        return payload

    def _count_images(
        self,
        listing_dir: Path,
    ) -> int:
        if not listing_dir.exists():
            return 0

        return sum(
            1
            for path in listing_dir.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in IMAGE_EXTENSIONS
            )
        )

    def _source_url(
        self,
        payload: dict[str, Any],
    ) -> str:
        for key in (
            "source_url",
            "listing_url",
            "url",
        ):
            value = str(
                payload.get(
                    key,
                    "",
                )
            ).strip()

            if value:
                return value

        return ""

    def _has_size(
        self,
        payload: dict[str, Any],
    ) -> bool:
        sizes = payload.get(
            "sizes"
        )

        if isinstance(
            sizes,
            Iterable,
        ) and not isinstance(
            sizes,
            (
                str,
                bytes,
                dict,
            ),
        ):
            if any(
                str(value).strip()
                for value in sizes
            ):
                return True

        return bool(
            str(
                payload.get(
                    "size",
                    "",
                )
            ).strip()
        )

    def _is_missing(
        self,
        value: Any,
    ) -> bool:
        if value is None:
            return True

        if isinstance(
            value,
            str,
        ):
            return not value.strip()

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
                dict,
            ),
        ):
            return len(value) == 0

        return False
