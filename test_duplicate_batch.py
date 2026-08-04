from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from login import (
    DESTINATION_STATE_FILE,
    open_logged_in_browser,
)
from uploader.duplicate_detector import (
    collect_destination_listing_urls,
    find_existing_duplicate,
)
from uploader.listing_loader import (
    find_next_uncopied_listing_file,
    load_listing,
)


DESTINATION_CLOSET_URL = (
    "https://poshmark.com/closet/dveshop"
)


def collect_uncopied_listing_files(
    maximum_count: int,
) -> list[Path]:
    """
    Repeatedly ask the existing listing loader for the next uncopied file.

    The loader may return the same file repeatedly because this dry run does
    not mark anything copied, so we track files already selected and temporarily
    search all listing.json files when needed.
    """
    if maximum_count < 1:
        raise ValueError(
            "maximum_count must be at least 1."
        )

    project_dir = Path(__file__).resolve().parent
    downloads_dir = project_dir / "downloads"

    listing_files = sorted(
        downloads_dir.rglob("listing.json")
    )

    selected: list[Path] = []

    for listing_file in listing_files:
        try:
            listing = load_listing(
                listing_file
            )
        except Exception:
            continue

        copied = bool(
            listing.get("copied")
            or listing.get("is_copied")
            or listing.get("uploaded")
        )

        if copied:
            continue

        selected.append(
            listing_file
        )

        if len(selected) >= maximum_count:
            break

    return selected


def run_dry_check(
    count: int,
) -> None:
    listing_files = collect_uncopied_listing_files(
        count
    )

    if not listing_files:
        print(
            "No uncopied saved listings were found."
        )
        return

    print(
        f"Listings selected for dry run: "
        f"{len(listing_files)}"
    )

    duplicate_count = 0
    would_upload_count = 0
    failed_count = 0

    with sync_playwright() as playwright:
        browser, context, page = (
            open_logged_in_browser(
                playwright,
                DESTINATION_STATE_FILE,
            )
        )

        try:
            destination_urls = (
                collect_destination_listing_urls(
                    page,
                    DESTINATION_CLOSET_URL,
                )
            )

            print()
            print(
                "Dry run only: no listings will "
                "be published or marked copied."
            )

            for index, listing_file in enumerate(
                listing_files,
                start=1,
            ):
                print()
                print("=" * 70)
                print(
                    f"CHECK {index}/"
                    f"{len(listing_files)}"
                )

                try:
                    listing = load_listing(
                        listing_file
                    )

                    print(
                        "Listing file:",
                        listing_file,
                    )
                    print(
                        "Listing ID:",
                        listing.get("listing_id"),
                    )
                    print(
                        "Title:",
                        listing.get("title"),
                    )
                    print(
                        "Price:",
                        listing.get("price"),
                    )
                    print(
                        "Brand:",
                        listing.get("brand"),
                    )
                    print(
                        "Size:",
                        listing.get("size"),
                    )

                    existing_url = (
                        find_existing_duplicate(
                            page,
                            listing,
                            destination_urls,
                        )
                    )

                    if existing_url:
                        duplicate_count += 1

                        print()
                        print(
                            "RESULT: DUPLICATE FOUND"
                        )
                        print(
                            "Existing destination:",
                            existing_url,
                        )

                    else:
                        would_upload_count += 1

                        print()
                        print(
                            "RESULT: WOULD UPLOAD"
                        )

                except Exception as error:
                    failed_count += 1

                    print()
                    print(
                        "RESULT: CHECK FAILED"
                    )
                    print(
                        "Reason:",
                        error,
                    )

            print()
            print("=" * 70)
            print("DRY RUN COMPLETE")
            print("=" * 70)
            print(
                "Duplicates found:",
                duplicate_count,
            )
            print(
                "Would upload:",
                would_upload_count,
            )
            print(
                "Checks failed:",
                failed_count,
            )
            print()
            print(
                "No listings were published."
            )
            print(
                "No listings were marked copied."
            )

            input(
                "\nPress ENTER to close "
                "the browser..."
            )

        finally:
            context.close()
            browser.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check saved listings against dveshop "
            "without publishing anything."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help=(
            "Number of uncopied saved listings "
            "to check."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run_dry_check(
        args.count
    )


if __name__ == "__main__":
    main()
