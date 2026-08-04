from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from scraper.listing_scraper import scrape_listing
from scraper.save_listing import listing_is_saved


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DISCOVERY_FILE = (
    PROJECT_DIR
    / "downloads"
    / "discovered_listings.json"
)
DEFAULT_STATE_FILE = (
    PROJECT_DIR
    / "source_state.json"
)


def load_available_listings(
    discovery_file: Path,
) -> list[dict[str, Any]]:
    if not discovery_file.exists():
        raise FileNotFoundError(
            "Discovery file was not found: "
            f"{discovery_file.resolve()}"
        )

    try:
        payload = json.loads(
            discovery_file.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Discovery file contains invalid JSON."
        ) from error

    raw_listings = payload.get(
        "listings",
        []
    )

    if not isinstance(raw_listings, list):
        raise RuntimeError(
            "Discovery file does not contain "
            "a listings array."
        )

    available: list[dict[str, Any]] = []

    for item in raw_listings:
        if not isinstance(item, dict):
            continue

        if item.get("available") is not True:
            continue

        listing_id = str(
            item.get("listing_id", "")
        ).strip()

        url = str(
            item.get("url", "")
        ).strip()

        if not listing_id or not url:
            continue

        available.append(item)

    return available


def run_test_batch(
    *,
    count: int,
    discovery_file: Path,
    state_file: Path,
    headless: bool,
) -> None:
    if count < 1:
        raise ValueError(
            "Count must be at least 1."
        )

    if not state_file.exists():
        raise FileNotFoundError(
            "Source Playwright state was not found: "
            f"{state_file.resolve()}"
        )

    available = load_available_listings(
        discovery_file
    )

    print(
        f"Available listings in discovery file: "
        f"{len(available)}"
    )

    pending = [
        item
        for item in available
        if not listing_is_saved(
            str(item["listing_id"])
        )
    ]

    print(
        f"Already saved listings skipped: "
        f"{len(available) - len(pending)}"
    )

    selected = pending[:count]

    if not selected:
        print(
            "No unsaved available listings "
            "were found."
        )
        return

    print(
        f"Testing {len(selected)} listing(s)."
    )

    success_count = 0
    skipped_count = 0
    failed_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
        )

        context = browser.new_context(
            storage_state=str(state_file),
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = context.new_page()

        try:
            for index, item in enumerate(
                selected,
                start=1,
            ):
                listing_id = str(
                    item["listing_id"]
                )

                listing_url = str(
                    item["url"]
                )

                title = str(
                    item.get(
                        "title",
                        listing_id,
                    )
                )

                print()
                print("=" * 70)
                print(
                    f"TEST {index}/{len(selected)}"
                )
                print(
                    f"Title: {title}"
                )
                print(
                    f"Listing ID: {listing_id}"
                )
                print(
                    f"URL: {listing_url}"
                )

                try:
                    listing = scrape_listing(
                        page,
                        listing_url,
                    )

                    if not listing.get(
                        "available",
                        False,
                    ):
                        skipped_count += 1

                        print(
                            "Skipped after opened-page "
                            "availability check."
                        )
                        print(
                            "Reason: "
                            f"{listing.get('availability_reason', '')}"
                        )

                        continue

                    local_images = listing.get(
                        "local_images",
                        [],
                    )

                    success_count += 1

                    print(
                        "Saved successfully."
                    )
                    print(
                        f"Images downloaded: "
                        f"{len(local_images)}"
                    )
                    print(
                        "Listing JSON: "
                        f"{listing.get('listing_json', '')}"
                    )

                except Exception as error:
                    failed_count += 1

                    print(
                        f"FAILED: {error}"
                    )

        finally:
            context.close()
            browser.close()

    print()
    print("=" * 70)
    print("TEST BATCH COMPLETE")
    print("=" * 70)
    print(
        f"Successful: {success_count}"
    )
    print(
        f"Skipped unavailable: "
        f"{skipped_count}"
    )
    print(
        f"Failed: {failed_count}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Test the PoshCopier scraper on a "
            "small batch of available listings."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--discovery-file",
        type=Path,
        default=DEFAULT_DISCOVERY_FILE,
    )

    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_FILE,
    )

    parser.add_argument(
        "--headless",
        action="store_true",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run_test_batch(
        count=args.count,
        discovery_file=args.discovery_file,
        state_file=args.state,
        headless=args.headless,
    )


if __name__ == "__main__":
    main()
