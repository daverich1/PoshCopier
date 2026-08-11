"""Strictly revalidate and share an explicit finite URL set to one live party."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sharing.party_runner import run_party_candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--party", required=True)
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()

    shared = 0
    skipped = 0
    failed = 0

    for index, url in enumerate(args.url, 1):
        print(f"CANDIDATE {index}/{len(args.url)}: {url}")
        result = run_party_candidate(
            url,
            args.party,
            perform_share=True,
        )
        if result.success and result.shared == 1:
            shared += 1
            print("RESULT=SHARED")
        elif result.eligibility_status and result.eligibility_status != "eligible":
            skipped += 1
            print(f"RESULT=SKIPPED: {result.message}")
        else:
            failed += 1
            print(f"RESULT=FAILED: {result.message}")

        if index < len(args.url):
            time.sleep(max(args.delay, 0))

    print(f"SHARED={shared}")
    print(f"SKIPPED={skipped}")
    print(f"FAILED={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
