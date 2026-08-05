from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from runtime_paths import DOWNLOADS_DIR


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_listing_folder(listing_id: str) -> Path:
    return DOWNLOADS_DIR / listing_id


def get_listing_json_path(listing_id: str) -> Path:
    return get_listing_folder(listing_id) / "listing.json"


def load_listing(listing_id: str) -> dict[str, Any] | None:
    path = get_listing_json_path(listing_id)

    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def listing_is_saved(listing_id: str) -> bool:
    payload = load_listing(listing_id)

    if not payload:
        return False

    title = str(payload.get("title", "")).strip()
    images = payload.get("local_images", [])

    if not title:
        return False

    if not isinstance(images, list) or not images:
        return False

    valid_images = 0

    for image_path in images:
        try:
            path = Path(str(image_path))

            if path.exists() and path.stat().st_size > 0:
                valid_images += 1
        except OSError:
            continue

    return valid_images > 0


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
            )

            handle.flush()
            os.fsync(handle.fileno())

        Path(temporary_name).replace(path)

    except Exception:
        try:
            Path(temporary_name).unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise


def save_listing(
    listing: dict[str, Any],
) -> Path:
    listing_id = str(
        listing.get("listing_id", "")
    ).strip()

    if not listing_id:
        raise ValueError(
            "Listing is missing listing_id."
        )

    output_path = get_listing_json_path(
        listing_id
    )

    existing = load_listing(
        listing_id
    ) or {}

    copied = bool(
        existing.get("copied")
        or existing.get("is_copied")
        or existing.get("uploaded")
        or listing.get("copied")
        or listing.get("is_copied")
        or listing.get("uploaded")
    )

    payload = {
        **existing,
        **listing,
        "listing_id": listing_id,
        "copied": copied,
        "is_copied": copied,
        "saved_at": utc_now(),
    }

    if copied and existing.get("copied_at"):
        payload["copied_at"] = existing[
            "copied_at"
        ]

    _atomic_write_json(
        output_path,
        payload,
    )

    return output_path


def mark_listing_copied(
    listing_id: str,
    destination_url: str = "",
) -> Path:
    payload = load_listing(
        listing_id
    )

    if payload is None:
        raise FileNotFoundError(
            f"No saved listing found for {listing_id}."
        )

    payload["copied"] = True
    payload["is_copied"] = True
    payload["uploaded"] = True
    payload["copied_at"] = utc_now()

    if destination_url:
        payload["destination_url"] = (
            destination_url
        )

    output_path = get_listing_json_path(
        listing_id
    )

    _atomic_write_json(
        output_path,
        payload,
    )

    return output_path
