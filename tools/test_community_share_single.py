"""Validate or share one listing from another Poshmark closet."""

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

from sharing.share_config import ShareConfig
from sharing.share_runner import run_community_sharing


OWN_CLOSET_URL = "https://poshmark.com/closet/dveshop"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("closet_url")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    mode = "LIVE ONE-SHARE" if args.live else "READ-ONLY VALIDATION"
    print(f"Mode: {mode}")
    print(f"Community closet: {args.closet_url}")
    print("Maximum listings: 1")

    config = ShareConfig(
        closet_url=args.closet_url,
        delay_seconds=5.0,
        max_shares=1,
        share_community_listings=args.live,
        community_share_limit=1,
    )
    result = run_community_sharing(
        config,
        OWN_CLOSET_URL,
        perform_share=args.live,
    )
    print(f"Success: {result.success}")
    print(f"Shared: {result.shared}")
    print(f"Skipped: {result.skipped}")
    print(f"Failed: {result.failed}")
    print(f"Message: {result.message}")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
