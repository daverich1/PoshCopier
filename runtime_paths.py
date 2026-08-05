from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


APP_DIR = app_dir()

DOWNLOADS_DIR = APP_DIR / "downloads"
LOGS_DIR = APP_DIR / "logs"
ERRORS_DIR = LOGS_DIR / "errors"

SOURCE_STATE_FILE = APP_DIR / "source_state.json"
DESTINATION_STATE_FILE = APP_DIR / "destination_state.json"

DISCOVERY_FILE = DOWNLOADS_DIR / "discovered_listings.json"
DATABASE_FILE = APP_DIR / "poshcopier.db"

PLAYWRIGHT_BROWSERS_DIR = APP_DIR / "pw-browsers"

PIPELINE_SCRIPT = APP_DIR / "run_pipeline.py"
PIPELINE_EXE = (
    APP_DIR
    / "PoshCopierPipeline"
    / "PoshCopierPipeline.exe"
)

def configure_playwright_browsers() -> None:
    if PLAYWRIGHT_BROWSERS_DIR.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(
            PLAYWRIGHT_BROWSERS_DIR
        )


def ensure_runtime_directories() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)
