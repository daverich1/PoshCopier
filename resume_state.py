from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_DIR / "logs"
RESUME_STATE_FILE = LOGS_DIR / "resume_state.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

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


def load_resume_state() -> dict[str, Any] | None:
    if not RESUME_STATE_FILE.exists():
        return None

    try:
        payload = json.loads(
            RESUME_STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def save_resume_state(
    *,
    mode: str,
    requested_count: int,
    processed: int,
    uploaded: int,
    existing: int,
    unavailable: int,
    failed: int,
    already_recorded: int,
    would_upload: int,
    last_listing_id: str = "",
    last_listing_title: str = "",
    started_at: str = "",
    completed_listing_ids: list[str] | None = None,
) -> Path:
    existing_state = load_resume_state() or {}

    if not started_at:
        started_at = (
            str(existing_state.get("started_at", ""))
            or utc_now()
        )

    payload: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "requested_count": int(requested_count),
        "processed": int(processed),
        "uploaded": int(uploaded),
        "existing": int(existing),
        "unavailable": int(unavailable),
        "failed": int(failed),
        "already_recorded": int(already_recorded),
        "would_upload": int(would_upload),
        "last_listing_id": last_listing_id,
        "last_listing_title": last_listing_title,
        "started_at": started_at,
        "updated_at": utc_now(),
        "completed_listing_ids": list(
            completed_listing_ids
            or existing_state.get(
                "completed_listing_ids",
                [],
            )
            or []
        ),
    }

    _atomic_write_json(
        RESUME_STATE_FILE,
        payload,
    )

    return RESUME_STATE_FILE


def add_completed_listing(
    listing_id: str,
) -> Path:
    listing_id = str(listing_id).strip()

    if not listing_id:
        raise ValueError(
            "listing_id is required."
        )

    state = load_resume_state() or {}

    completed = [
        str(item)
        for item in state.get(
            "completed_listing_ids",
            [],
        )
        if str(item).strip()
    ]

    if listing_id not in completed:
        completed.append(listing_id)

    state["completed_listing_ids"] = completed
    state["updated_at"] = utc_now()

    _atomic_write_json(
        RESUME_STATE_FILE,
        state,
    )

    return RESUME_STATE_FILE


def completed_listing_ids() -> set[str]:
    state = load_resume_state()

    if not state:
        return set()

    values = state.get(
        "completed_listing_ids",
        [],
    )

    if not isinstance(values, list):
        return set()

    return {
        str(value).strip()
        for value in values
        if str(value).strip()
    }


def clear_resume_state() -> bool:
    if not RESUME_STATE_FILE.exists():
        return False

    RESUME_STATE_FILE.unlink()
    return True
