from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from inventory.inventory_health import InventoryHealth
from runtime_paths import DOWNLOADS_DIR


IGNORED_FOLDER_NAMES = {
    "logs",
    "errors",
    "__pycache__",
}


@dataclass(frozen=True)
class RecoveryItem:
    folder_name: str
    folder_path: Path
    listing_file: Path
    problem: str
    details: str
    image_count: int
    can_delete: bool
    source_url: str = ""


class RecoveryManager:
    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
    ) -> None:
        self.downloads_dir = downloads_dir
        self.health = InventoryHealth(
            downloads_dir
        )

    def scan_broken_folders(
        self,
    ) -> list[RecoveryItem]:
        items: list[RecoveryItem] = []

        if not self.downloads_dir.exists():
            return items

        for folder in sorted(
            self.downloads_dir.iterdir(),
            key=lambda path: path.name.lower(),
        ):
            if not folder.is_dir():
                continue

            if self._should_ignore(
                folder
            ):
                continue

            report = self.health.scan_listing(
                folder
            )

            if report.json_valid:
                continue

            items.append(
                self._build_recovery_item(
                    folder
                )
            )

        return items

    def _build_recovery_item(
        self,
        folder: Path,
    ) -> RecoveryItem:
        listing_file = folder / "listing.json"
        image_count = self._count_images(
            folder
        )

        if not listing_file.exists():
            problem = "Missing listing.json"
            details = (
                "The folder exists, but listing.json "
                "is missing."
            )
            source_url = ""
        else:
            try:
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
                        "JSON root is not an object."
                    )

                problem = "Unknown JSON problem"
                details = (
                    "The listing JSON could not be "
                    "validated."
                )
                source_url = self._source_url(
                    payload
                )

            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
            ) as error:
                problem = "Invalid listing.json"
                details = str(
                    error
                )
                source_url = ""

        can_delete = self._can_delete_folder(
            folder
        )

        return RecoveryItem(
            folder_name=folder.name,
            folder_path=folder,
            listing_file=listing_file,
            problem=problem,
            details=details,
            image_count=image_count,
            can_delete=can_delete,
            source_url=source_url,
        )

    def delete_folder(
        self,
        item: RecoveryItem,
    ) -> None:
        folder = item.folder_path.resolve()
        downloads_root = (
            self.downloads_dir.resolve()
        )

        if downloads_root not in folder.parents:
            raise RuntimeError(
                "Refusing to delete a folder outside "
                "the downloads directory."
            )

        if not folder.exists():
            return

        shutil.rmtree(
            folder
        )

    def folder_is_empty(
        self,
        folder: Path,
    ) -> bool:
        if not folder.exists():
            return True

        return not any(
            folder.iterdir()
        )

    def _can_delete_folder(
        self,
        folder: Path,
    ) -> bool:
        if self.folder_is_empty(
            folder
        ):
            return True

        allowed_names = {
            "listing.json",
        }

        files = [
            path
            for path in folder.iterdir()
            if path.is_file()
        ]

        subfolders = [
            path
            for path in folder.iterdir()
            if path.is_dir()
        ]

        if subfolders:
            return False

        return all(
            path.name in allowed_names
            for path in files
        )

    def _count_images(
        self,
        folder: Path,
    ) -> int:
        extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }

        return sum(
            1
            for path in folder.iterdir()
            if (
                path.is_file()
                and path.suffix.lower()
                in extensions
            )
        )

    def _source_url(
        self,
        payload: dict,
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

    def _should_ignore(
        self,
        folder: Path,
    ) -> bool:
        if folder.name in IGNORED_FOLDER_NAMES:
            return True

        if folder.name.endswith(
            "_backup"
        ):
            return True

        return False
