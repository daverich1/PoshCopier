"""Run a guarded follower-sharing batch from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from sharing.share_config import ShareConfig
from sharing.share_progress import ShareProgress
from sharing.share_runner import run_follower_sharing


DESTINATION_CLOSET_URL = "https://poshmark.com/closet/dveshop"


def print_progress(progress: ShareProgress) -> None:
    """Print one concise progress line for console logs."""
    percent = (progress.current / progress.total * 100) if progress.total else 0.0
    print(
        f"SHARE_PROGRESS {percent:.0f}% "
        f"{progress.current}/{progress.total} "
        f"shared={progress.shared} skipped={progress.skipped} "
        f"failed={progress.failed} status={progress.status.value} "
        f"message={progress.message}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required acknowledgement that real follower shares will occur.",
    )
    args = parser.parse_args()

    if not args.confirm_live:
        parser.error("--confirm-live is required")
    if args.count < 1 or args.count > 500:
        parser.error("--count must be between 1 and 500")
    if args.delay < 0:
        parser.error("--delay cannot be negative")

    config = ShareConfig(
        closet_url=DESTINATION_CLOSET_URL,
        delay_seconds=args.delay,
        max_shares=args.count,
        share_to_parties=False,
        share_to_posh_shows=False,
    )
    result = run_follower_sharing(config, progress_callback=print_progress)
    print(
        f"SHARE_RESULT success={result.success} shared={result.shared} "
        f"skipped={result.skipped} failed={result.failed} "
        f"message={result.message}",
        flush=True,
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
