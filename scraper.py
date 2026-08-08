import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from login import (
    SOURCE_STATE_FILE,
    open_logged_in_browser,
)
from scraper.discover import (
    discover_closet_listings,
    extract_listing_id,
)
from scraper.image_downloader import (
    download_listing_images,
)
from scraper.listing_scraper import (
    scrape_listing,
)


# Replace this with the closet listings come FROM.
CLOSET_URL = (
    "https://poshmark.com/closet/successboutique"
)

PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
LOGS_DIR = PROJECT_DIR / "logs"

# Keep this at 5 while testing.
# Change to None after confirming unavailable items are skipped.
MAX_NEW_LISTINGS_PER_RUN = None


def listing_folder(
    listing_id: str,
) -> Path:
    return DOWNLOADS_DIR / listing_id


def listing_file_path(
    listing_id: str,
) -> Path:
    return (
        listing_folder(listing_id)
        / "listing.json"
    )


def listing_is_downloaded(
    listing_id: str,
) -> bool:
    path = listing_file_path(
        listing_id
    )

    if not path.exists():
        return False

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

        return (
            data.get("listing_id")
            == listing_id
        )

    except Exception:
        return False


def repair_missing_listing_id(
    listing_id: str,
) -> bool:
    path = listing_file_path(
        listing_id
    )

    if not path.exists():
        return False

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

        if data.get("listing_id"):
            return False

        data["listing_id"] = listing_id

        path.write_text(
            json.dumps(
                data,
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print(
            "Repaired missing listing ID:",
            listing_id,
        )

        return True

    except Exception as error:
        print(
            "Could not repair listing file:",
            path,
        )
        print(
            "Reason:",
            error,
        )

        return False


def repair_existing_downloads() -> None:
    if not DOWNLOADS_DIR.exists():
        return

    print(
        "\nChecking old downloads for "
        "missing listing IDs..."
    )

    repaired = 0

    for folder in DOWNLOADS_DIR.iterdir():
        if not folder.is_dir():
            continue

        if repair_missing_listing_id(
            folder.name
        ):
            repaired += 1

    print(
        "Old listing files repaired:",
        repaired,
    )


def save_listing_data(
    listing: dict,
) -> str:
    folder = listing_folder(
        listing["listing_id"]
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = folder / "listing.json"

    path.write_text(
        json.dumps(
            listing,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return str(path)


def append_log_record(
    filename: str,
    lines: list[str],
) -> None:
    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = LOGS_DIR / filename

    timestamp = datetime.now().isoformat(
        timespec="seconds"
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            f"[{timestamp}]\n"
        )

        for line in lines:
            file.write(
                f"{line}\n"
            )

        file.write(
            f"{'-' * 60}\n"
        )


def log_unavailable_card(
    card,
) -> None:
    append_log_record(
        "unavailable_cards.txt",
        [
            f"URL: {card.url}",
            f"STATUS: {card.status}",
            (
                "REASON: "
                f"{card.unavailable_reason}"
            ),
        ],
    )


def log_unavailable_listing(
    listing: dict,
) -> None:
    append_log_record(
        "unavailable_listings.txt",
        [
            f"ID: {listing.get('listing_id')}",
            f"TITLE: {listing.get('title')}",
            f"URL: {listing.get('url')}",
            (
                "REASON: "
                f"{listing.get('availability_reason')}"
            ),
            (
                "SIGNAL: "
                f"{listing.get('availability_signal')}"
            ),
        ],
    )


def log_failed_listing(
    listing_url: str,
    error: Exception,
) -> None:
    append_log_record(
        "scraper_failures.txt",
        [
            f"URL: {listing_url}",
            f"ERROR: {error}",
        ],
    )


def get_pending_listing_links(
    listing_links: list[str],
) -> tuple[list[str], int]:
    pending = []
    already_downloaded = 0

    for listing_url in listing_links:
        listing_id = extract_listing_id(
            listing_url
        )

        if listing_is_downloaded(
            listing_id
        ):
            already_downloaded += 1
            continue

        pending.append(
            listing_url
        )

    if MAX_NEW_LISTINGS_PER_RUN is not None:
        pending = pending[
            :MAX_NEW_LISTINGS_PER_RUN
        ]

    return (
        pending,
        already_downloaded,
    )


def print_listing_summary(
    listing: dict,
    current_number: int,
    total_number: int,
) -> None:
    print("\n" + "=" * 60)

    print(
        f"AVAILABLE LISTING "
        f"{current_number}/{total_number}"
    )

    print("=" * 60)

    print(
        "LISTING ID:",
        listing.get("listing_id"),
    )
    print(
        "TITLE:",
        listing.get("title"),
    )
    print(
        "PRICE:",
        listing.get("price"),
    )
    print(
        "BRAND:",
        listing.get("brand"),
    )
    print(
        "SIZE:",
        listing.get("size"),
    )
    print(
        "CONDITION:",
        listing.get("condition"),
    )
    print(
        "CATEGORY:",
        listing.get("category"),
    )
    print(
        "COLORS:",
        listing.get("colors"),
    )
    print(
        "AVAILABILITY REASON:",
        listing.get(
            "availability_reason"
        ),
    )
    print(
        "IMAGES FOUND:",
        len(
            listing.get(
                "image_urls",
                [],
            )
        ),
    )
    print(
        "IMAGES DOWNLOADED:",
        len(
            listing.get(
                "downloaded_images",
                [],
            )
        ),
    )

    print("=" * 60)


def main() -> None:
    DOWNLOADS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    repair_existing_downloads()

    with sync_playwright() as playwright:
        browser, context, page = (
            open_logged_in_browser(
                playwright,
                SOURCE_STATE_FILE,
            )
        )

        downloaded = 0
        unavailable_on_page = 0
        failed = 0

        try:
            discovery = (
                discover_closet_listings(
                    page,
                    CLOSET_URL,
                )
            )

            for card in discovery.unavailable_cards:
                log_unavailable_card(
                    card
                )

            (
                pending_links,
                already_downloaded,
            ) = get_pending_listing_links(
                discovery.available_urls
            )

            print("\n" + "=" * 60)
            print(
                "Total closet cards:",
                discovery.total_cards,
            )
            print(
                "Available closet listings:",
                len(
                    discovery.available_urls
                ),
            )
            print(
                "Unavailable cards skipped:",
                len(
                    discovery.unavailable_cards
                ),
            )
            print(
                "Already downloaded:",
                already_downloaded,
            )
            print(
                "Available listings this run:",
                len(pending_links),
            )
            print("=" * 60)

            if not pending_links:
                print(
                    "\nNo new available listings "
                    "need to be scraped."
                )

            for index, listing_url in enumerate(
                pending_links,
                start=1,
            ):
                print(
                    "\nChecking available listing:",
                    listing_url,
                )

                try:
                    listing = scrape_listing(
                        page,
                        listing_url,
                    )

                    if not listing.get(
                        "listing_id"
                    ):
                        raise RuntimeError(
                            "The scraper did not produce "
                            "a listing ID."
                        )

                    if not listing.get(
                        "available",
                        False,
                    ):
                        unavailable_on_page += 1

                        print(
                            "Skipping listing after "
                            "page-level availability check:"
                        )
                        print(
                            listing.get("title")
                        )
                        print(
                            "Reason:",
                            listing.get(
                                "availability_reason"
                            ),
                        )
                        print(
                            "Signal:",
                            listing.get(
                                "availability_signal"
                            ),
                        )

                        log_unavailable_listing(
                            listing
                        )

                        continue

                    listing[
                        "downloaded_images"
                    ] = download_listing_images(
                        listing
                    )

                    listing[
                        "scraped_at"
                    ] = datetime.now().isoformat(
                        timespec="seconds"
                    )

                    listing[
                        "listing_data_file"
                    ] = save_listing_data(
                        listing
                    )

                    downloaded += 1

                    print_listing_summary(
                        listing,
                        index,
                        len(pending_links),
                    )

                except Exception as error:
                    failed += 1

                    print(
                        "\nCould not scrape listing:"
                    )
                    print(
                        listing_url
                    )
                    print(
                        "Reason:",
                        error,
                    )

                    log_failed_listing(
                        listing_url,
                        error,
                    )

                page.wait_for_timeout(
                    1200
                )

            print("\n" + "=" * 60)
            print("SCRAPER COMPLETE")
            print("=" * 60)
            print(
                "Total closet cards:",
                discovery.total_cards,
            )
            print(
                "Available discovered:",
                len(
                    discovery.available_urls
                ),
            )
            print(
                "Unavailable cards skipped:",
                len(
                    discovery.unavailable_cards
                ),
            )
            print(
                "Previously downloaded:",
                already_downloaded,
            )
            print(
                "Downloaded this run:",
                downloaded,
            )
            print(
                "Skipped after page check:",
                unavailable_on_page,
            )
            print(
                "Failed this run:",
                failed,
            )
            print("=" * 60)

            input(
                "\nPress ENTER to close "
                "the browser..."
            )

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()