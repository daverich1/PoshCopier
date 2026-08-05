from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_DIR = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_DIR / "logs"
CONTROL_FILE = LOGS_DIR / "pipeline_control.json"

DEFAULT_POLL_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class PipelineControlState:
    paused: bool = False
    stop_after_current: bool = False
    updated_at: str = ""

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> "PipelineControlState":
        return cls(
            paused=bool(
                value.get(
                    "paused",
                    False,
                )
            ),
            stop_after_current=bool(
                value.get(
                    "stop_after_current",
                    False,
                )
            ),
            updated_at=str(
                value.get(
                    "updated_at",
                    "",
                )
            ),
        )

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "paused": self.paused,
            "stop_after_current": (
                self.stop_after_current
            ),
            "updated_at": (
                self.updated_at
                or utc_now()
            ),
        }


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


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
            os.fsync(
                handle.fileno()
            )

        Path(
            temporary_name
        ).replace(
            path
        )

    except Exception:
        try:
            Path(
                temporary_name
            ).unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise


def read_control_state() -> PipelineControlState:
    if not CONTROL_FILE.exists():
        return PipelineControlState()

    try:
        payload = json.loads(
            CONTROL_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return PipelineControlState()

    if not isinstance(
        payload,
        dict,
    ):
        return PipelineControlState()

    return PipelineControlState.from_dict(
        payload
    )


def write_control_state(
    state: PipelineControlState,
) -> Path:
    payload = state.to_dict()
    payload["updated_at"] = utc_now()

    _atomic_write_json(
        CONTROL_FILE,
        payload,
    )

    return CONTROL_FILE


def clear_control_state() -> None:
    try:
        CONTROL_FILE.unlink(
            missing_ok=True
        )
    except OSError:
        pass


def initialize_control_state() -> Path:
    return write_control_state(
        PipelineControlState()
    )


def request_pause() -> Path:
    current = read_control_state()

    return write_control_state(
        PipelineControlState(
            paused=True,
            stop_after_current=(
                current.stop_after_current
            ),
        )
    )


def request_resume() -> Path:
    current = read_control_state()

    return write_control_state(
        PipelineControlState(
            paused=False,
            stop_after_current=(
                current.stop_after_current
            ),
        )
    )


def request_stop_after_current() -> Path:
    current = read_control_state()

    return write_control_state(
        PipelineControlState(
            paused=current.paused,
            stop_after_current=True,
        )
    )


def cancel_stop_after_current() -> Path:
    current = read_control_state()

    return write_control_state(
        PipelineControlState(
            paused=current.paused,
            stop_after_current=False,
        )
    )


def pause_requested() -> bool:
    return read_control_state().paused


def stop_after_current_requested() -> bool:
    return read_control_state().stop_after_current


def wait_while_paused(
    *,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    on_paused: Callable[[], None] | None = None,
    on_resumed: Callable[[], None] | None = None,
) -> None:
    announced_pause = False

    while True:
        state = read_control_state()

        if not state.paused:
            if (
                announced_pause
                and on_resumed is not None
            ):
                on_resumed()

            return

        if (
            not announced_pause
            and on_paused is not None
        ):
            on_paused()
            announced_pause = True

        time.sleep(
            max(
                poll_seconds,
                0.1,
            )
        )
