from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StatusEvent:
    key: str
    value: str


def parse_status_line(
    line: str,
) -> StatusEvent | None:
    """
    Parse lines emitted by run_pipeline.py.

    Expected format:
        STATUS:KEY=VALUE
    """
    stripped = line.strip()

    if not stripped.startswith(
        "STATUS:"
    ):
        return None

    payload = stripped.removeprefix(
        "STATUS:"
    )

    if "=" not in payload:
        return None

    key, value = payload.split(
        "=",
        1,
    )

    key = key.strip().upper()
    value = value.strip()

    if not key:
        return None

    return StatusEvent(
        key=key,
        value=value,
    )


def parse_percent(
    value: str,
) -> float | None:
    try:
        percent = float(
            value.strip()
        )
    except ValueError:
        return None

    return max(
        0.0,
        min(
            percent,
            100.0,
        ),
    )
