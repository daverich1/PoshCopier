"""Run verified direct-uploader batches for a bounded overnight window."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
DATABASE_FILE = PROJECT_ROOT / "poshcopier.db"
LOGS_DIR = PROJECT_ROOT / "logs"
STOP_FILE = LOGS_DIR / "STOP_OVERNIGHT_TRANSFER"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def transfer_counts() -> tuple[int, int, int]:
    listing_ids: set[str] = set()
    for listing_file in DOWNLOADS_DIR.glob("*/listing.json"):
        try:
            payload = json.loads(listing_file.read_text(encoding="utf-8"))
            listing_id = str(payload.get("listing_id", "")).strip()
            if listing_id:
                listing_ids.add(listing_id)
        except (OSError, json.JSONDecodeError, TypeError):
            continue

    with sqlite3.connect(DATABASE_FILE) as connection:
        copied_ids = {
            str(row[0])
            for row in connection.execute(
                "SELECT source_listing_id FROM copied_listings"
            )
        }

    complete = len(listing_ids & copied_ids)
    return len(listing_ids), complete, len(listing_ids) - complete


def run_batch(batch_number: int) -> tuple[int, Path]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"overnight_batch_{batch_number:02d}_{timestamp()}.log"
    command = [sys.executable, "-u", str(PROJECT_ROOT / "uploader.py")]
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
        return process.wait(), log_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=7.0)
    parser.add_argument("--cooldown-seconds", type=int, default=120)
    parser.add_argument("--max-batches", type=int, default=8)
    args = parser.parse_args()

    if args.hours <= 0 or args.cooldown_seconds < 0 or args.max_batches < 1:
        raise ValueError("Invalid overnight transfer limits")

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    deadline = datetime.now() + timedelta(hours=args.hours)
    summary_path = LOGS_DIR / f"overnight_transfer_{timestamp()}.log"

    with summary_path.open("w", encoding="utf-8") as summary:
        summary.write(f"Started: {datetime.now().isoformat()}\n")
        summary.write(f"Deadline: {deadline.isoformat()}\n")
        summary.write(f"Max batches: {args.max_batches}\n")
        summary.flush()

        for batch_number in range(1, args.max_batches + 1):
            total, complete, pending = transfer_counts()
            summary.write(
                f"Before batch {batch_number}: total={total} "
                f"complete={complete} pending={pending}\n"
            )
            summary.flush()

            if pending == 0:
                summary.write("All downloaded listings are complete.\n")
                return 0
            if STOP_FILE.exists():
                summary.write(f"Stopped by marker: {STOP_FILE}\n")
                return 0
            if datetime.now() >= deadline:
                summary.write("Overnight deadline reached before next batch.\n")
                return 0

            return_code, batch_log = run_batch(batch_number)
            summary.write(
                f"Batch {batch_number} exit={return_code} log={batch_log}\n"
            )
            summary.flush()
            if return_code != 0:
                summary.write("Stopping immediately after batch failure.\n")
                return return_code

            if batch_number < args.max_batches:
                remaining = (deadline - datetime.now()).total_seconds()
                if remaining <= args.cooldown_seconds:
                    summary.write("Deadline too close for another batch.\n")
                    return 0
                time.sleep(args.cooldown_seconds)

        summary.write("Maximum overnight batch count reached.\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
