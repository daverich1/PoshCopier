"""Validate or perform exactly one guarded follow-back."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from sharing.follow_runner import run_follow_backs
from sharing.share_config import ShareConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    mode = "LIVE ONE-FOLLOW" if args.live else "READ-ONLY VALIDATION"
    print(f"Mode: {mode}")
    print("Account: dveshop")
    print("Maximum follow-backs: 1")
    config = ShareConfig(
        closet_url="https://poshmark.com/closet/dveshop",
        delay_seconds=5.0,
        follow_backs_enabled=args.live,
        follow_back_limit=1,
    )
    result = run_follow_backs(
        config,
        "dveshop",
        perform_follow=args.live,
    )
    print(f"Success: {result.success}")
    print(f"Followed: {result.shared}")
    print(f"Candidates/Skipped: {result.skipped}")
    print(f"Failed: {result.failed}")
    print(f"Message: {result.message}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
