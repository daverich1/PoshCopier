"""Validate and optionally share one exact listing to a currently live party."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from sharing.party_runner import run_party_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing-url", required=True)
    parser.add_argument("--party-name", required=True)
    parser.add_argument("--confirm-live", action="store_true")
    args = parser.parse_args()

    result = run_party_candidate(
        args.listing_url,
        args.party_name,
        perform_share=args.confirm_live,
    )
    print(
        f"PARTY_CANDIDATE_RESULT success={result.success} "
        f"shared={result.shared} failed={result.failed} "
        f"eligibility={result.eligibility_status!r} "
        f"message={result.message!r}",
        flush=True,
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
