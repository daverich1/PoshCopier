from __future__ import annotations

import argparse
import json
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.parse import urlsplit
from resume_state import (
    add_completed_listing,
    clear_resume_state,
    completed_listing_ids,
    load_resume_state,
    save_resume_state,
)
from playwright.sync_api import Page, sync_playwright

from data.database.database import (
    initialize_database,
    listing_already_copied,
    mark_listing_copied as mark_database_copied,
)
from login import (
    DESTINATION_STATE_FILE,
    SOURCE_STATE_FILE,
    open_logged_in_browser,
)
from scraper.listing_scraper import scrape_listing
from scraper.save_listing import (
    listing_is_saved,
    mark_listing_copied as mark_local_copied,
)
from uploader.category import fill_category
from uploader.colors import fill_colors
from uploader.condition import fill_condition
from uploader.duplicate_detector import (
    add_destination_url,
    collect_destination_listing_urls,
    find_existing_duplicate,
)
from uploader.form_fields import (
    close_price_modal,
    fill_brand,
    fill_description,
    fill_price,
    fill_title,
)
from uploader.image_uploader import upload_images
from uploader.listing_loader import (
    get_image_paths,
    load_listing,
)
from uploader.publisher import publish_listing
from uploader.size import fill_size

from uploader.multi_size import fill_multi_size_inventory


PROJECT_DIR = Path(__file__).resolve().parent
DISCOVERY_FILE = PROJECT_DIR / "downloads" / "discovered_listings.json"
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
LOGS_DIR = PROJECT_DIR / "logs"
ERRORS_DIR = LOGS_DIR / "errors"

SELL_URL = "https://poshmark.com/create-listing"
DESTINATION_CLOSET_URL = "https://poshmark.com/closet/dveshop"

T = TypeVar("T")


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return cleaned.strip("_")[:80] or "unknown"


def save_error_artifacts(
    page: Page | None,
    *,
    stage: str,
    listing_id: str,
    error: Exception,
) -> None:
    ERRORS_DIR.mkdir(parents=True, exist_ok=True)

    stem = (
        f"{timestamp()}_"
        f"{sanitize_filename(stage)}_"
        f"{sanitize_filename(listing_id)}"
    )

    text_path = ERRORS_DIR / f"{stem}.txt"

    details = [
        f"Stage: {stage}",
        f"Listing ID: {listing_id}",
        f"Error: {error}",
        "",
        traceback.format_exc(),
    ]

    text_path.write_text(
        "\n".join(details),
        encoding="utf-8",
    )

    if page is not None:
        try:
            screenshot_path = ERRORS_DIR / f"{stem}.png"
            page.screenshot(
                path=str(screenshot_path),
                full_page=True,
            )
            print("Error screenshot:", screenshot_path)
        except Exception as screenshot_error:
            print("Could not save screenshot:", screenshot_error)

    print("Error details:", text_path)


def retry_operation(
    operation: Callable[[], T],
    *,
    attempts: int,
    delay_seconds: float,
    page: Page | None,
    stage: str,
    listing_id: str,
) -> T:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                print(
                    f"Retrying {stage}: "
                    f"attempt {attempt}/{attempts}"
                )

            return operation()

        except Exception as error:
            last_error = error

            print(
                f"{stage} failed "
                f"(attempt {attempt}/{attempts}):"
            )
            print(error)

            if attempt < attempts:
                time.sleep(delay_seconds)

    assert last_error is not None

    save_error_artifacts(
        page,
        stage=stage,
        listing_id=listing_id,
        error=last_error,
    )

    raise last_error


def load_available_discovery(
    discovery_file: Path,
) -> list[dict[str, Any]]:
    if not discovery_file.exists():
        raise FileNotFoundError(
            "Discovery file was not found: "
            f"{discovery_file.resolve()}"
        )

    try:
        payload = json.loads(
            discovery_file.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Discovery file contains invalid JSON."
        ) from error

    listings = payload.get("listings", [])

    if not isinstance(listings, list):
        raise RuntimeError(
            "Discovery file does not contain a listings array."
        )

    available: list[dict[str, Any]] = []

    for item in listings:
        if not isinstance(item, dict):
            continue

        if item.get("available") is not True:
            continue

        listing_id = str(item.get("listing_id", "")).strip()
        url = str(item.get("url", "")).strip()

        if listing_id and url:
            available.append(item)

    return available


def extract_listing_id_from_url(listing_url: str) -> str:
    path = urlsplit(listing_url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]

    match = re.search(
        r"(?:-|^)([a-fA-F0-9]{24})$",
        slug,
    )

    return match.group(1).lower() if match else ""


def get_listing_json_path(listing_id: str) -> Path:
    return DOWNLOADS_DIR / listing_id / "listing.json"


def select_source_candidates(
    available: list[dict[str, Any]],
    count: int,
    completed_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    completed_ids = completed_ids or set()

    for item in available:
        listing_id = str(
            item["listing_id"]
        )

        if listing_id in completed_ids:
            continue

        if listing_already_copied(
            listing_id
        ):
            continue

        selected.append(item)

        if len(selected) >= count:
            break

    return selected

    for item in available:
        listing_id = str(item["listing_id"])

        if listing_already_copied(listing_id):
            continue

        selected.append(item)

        if len(selected) >= count:
            break

    return selected


def ensure_listing_saved(
    page: Page,
    discovered: dict[str, Any],
) -> Path | None:
    listing_id = str(discovered["listing_id"])

    if listing_already_copied(listing_id):
        print("Already copied according to the database.")
        return None

    if listing_is_saved(listing_id):
        path = get_listing_json_path(listing_id)
        print("Listing is already saved locally:")
        print(path)
        return path

    listing = scrape_listing(
        page,
        str(discovered["url"]),
    )

    if not listing.get("available", False):
        print(
            "Listing failed the opened-page "
            "availability check."
        )
        print(
            "Reason:",
            listing.get("availability_reason", ""),
        )
        return None

    path_value = str(
        listing.get("listing_json", "")
    ).strip()

    if not path_value:
        raise RuntimeError(
            "The scraper did not return a listing_json path."
        )

    return Path(path_value)


def validate_listing(
    listing: dict[str, Any],
    image_paths: list[str],
) -> None:
    required_fields = (
        "listing_id",
        "title",
        "description",
        "price",
        "brand",
        "category",
        "size",
        "condition",
    )

    missing = [
        field
        for field in required_fields
        if not listing.get(field)
    ]

    if missing:
        raise RuntimeError(
            "Listing is missing required fields: "
            + ", ".join(missing)
        )

    if not image_paths:
        raise RuntimeError(
            "Listing has no local images."
        )


def fill_listing_form(
    page: Page,
    listing: dict[str, Any],
    image_paths: list[str],
) -> None:
    page.goto(
        SELL_URL,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    page.wait_for_timeout(5000)

    print("Create Listing page opened.")

    upload_images(page, image_paths)
    fill_title(page, listing["title"])
    fill_description(page, listing["description"])
    fill_price(page, listing["price"])
    close_price_modal(page)
    fill_brand(page, listing["brand"])
    fill_category(page, listing["category"])
    if listing.get("is_multi_size"):
        fill_multi_size_inventory(
            page,
            listing,
        )
    else:
        fill_size(
            page,
            listing["size"],
        )
    fill_condition(page, listing["condition"])
    fill_colors(page, listing.get("colors", []))

    print("All listing fields completed.")


def record_completion(
    listing: dict[str, Any],
    destination_url: str,
) -> None:
    listing_id = str(listing["listing_id"])
    destination_id = extract_listing_id_from_url(
        destination_url
    )

    mark_database_copied(
        listing_id,
        destination_id or None,
        str(listing.get("title", "")),
    )

    mark_local_copied(
        listing_id,
        destination_url,
    )


def process_destination_listing(
    page: Page,
    listing_file: Path,
    destination_urls: list[str],
    *,
    publish: bool,
) -> str:
    listing = load_listing(listing_file)
    listing_id = str(
        listing.get("listing_id", "")
    )

    if not listing_id:
        raise RuntimeError(
            "Saved listing has no listing_id."
        )

    if listing_already_copied(listing_id):
        print("Already copied according to the database.")
        return "already_recorded"

    image_paths = get_image_paths(listing)
    validate_listing(listing, image_paths)

    print("Checking dveshop for a duplicate...")

    existing_url = find_existing_duplicate(
        page,
        listing,
        destination_urls,
    )

    if existing_url:
        record_completion(
            listing,
            existing_url,
        )

        print(
            "Duplicate confirmed. "
            "No new listing was created."
        )
        print("Existing destination:", existing_url)

        return "already_exists"

    if not publish:
        print("DRY RUN: no duplicate found.")
        print("This listing would be uploaded.")
        return "would_upload"

    fill_listing_form(
        page,
        listing,
        image_paths,
    )

    destination_url = publish_listing(
        page,
        str(listing["title"]),
    )

    record_completion(
        listing,
        destination_url,
    )

    add_destination_url(
        destination_urls,
        destination_url,
    )

    print("Published destination:", destination_url)

    return "uploaded"


def print_progress(
    *,
    processed: int,
    total: int,
    uploaded: int,
    existing: int,
    would_upload: int,
    failed: int,
    started_at: float,
) -> None:
    elapsed = max(
        time.time() - started_at,
        0.001,
    )

    rate = processed / elapsed
    remaining = total - processed
    eta_seconds = (
        int(remaining / rate)
        if rate > 0
        else 0
    )

    eta_minutes, eta_seconds = divmod(
        eta_seconds,
        60,
    )

    percent = (
        (processed / total) * 100
        if total
        else 100.0
    )

    print()
    print("=" * 72)
    print(
        f"PROGRESS: {processed}/{total} "
        f"({percent:.1f}%)"
    )
    print("Uploaded:", uploaded)
    print("Already existed:", existing)
    print("Would upload:", would_upload)
    print("Failed:", failed)
    print(
        f"Estimated time remaining: "
        f"{eta_minutes}m {eta_seconds}s"
    )
    print("=" * 72)


def run_pipeline(
    *,
    count: int,
    publish: bool,
    discovery_file: Path,
    retries: int,
    retry_delay: float,
) -> None:
    if count < 1:
        raise ValueError(
            "Count must be at least 1."
        )

    if retries < 1:
        raise ValueError(
            "Retries must be at least 1."
        )

    initialize_database()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    available = load_available_discovery(
        discovery_file
    )

    state = load_resume_state()
    completed_ids = completed_listing_ids()

    if state:
        print()
        print("Resume checkpoint found.")
        print(
            "Previously processed:",
            state.get("processed", 0),
        )
        print(
            "Last listing:",
            state.get("last_listing_id", ""),
        )
        print()

    candidates = select_source_candidates(
        available,
        count,
        completed_ids,
    )

    print("=" * 72)
    print("POSHCOPIER PIPELINE")
    print("=" * 72)
    print(
        "Available discovery listings:",
        len(available),
    )
    print(
        "Selected this run:",
        len(candidates),
    )
    print(
        "Mode:",
        "LIVE PUBLISH"
        if publish
        else "DRY RUN",
    )
    print("Retries per operation:", retries)
    print("=" * 72)

    if not candidates:
        print("No eligible listings were found.")
        return

    scraped_files: list[Path] = []
    scrape_failed = 0
    unavailable = 0

    with sync_playwright() as playwright:
        source_browser, source_context, source_page = (
            open_logged_in_browser(
                playwright,
                SOURCE_STATE_FILE,
            )
        )

        try:
            for index, discovered in enumerate(
                candidates,
                start=1,
            ):
                listing_id = str(
                    discovered["listing_id"]
                )

                print()
                print("-" * 72)
                print(
                    f"SOURCE {index}/"
                    f"{len(candidates)}"
                )
                print(
                    "Title:",
                    discovered.get("title", ""),
                )
                print("Listing ID:", listing_id)

                try:
                    saved_path = retry_operation(
                        lambda discovered=discovered: (
                            ensure_listing_saved(
                                source_page,
                                discovered,
                            )
                        ),
                        attempts=retries,
                        delay_seconds=retry_delay,
                        page=source_page,
                        stage="source_scrape",
                        listing_id=listing_id,
                    )

                    if saved_path is None:
                        unavailable += 1
                        continue

                    scraped_files.append(saved_path)

                except Exception:
                    scrape_failed += 1

        finally:
            source_context.close()
            source_browser.close()

        if not scraped_files:
            print()
            print(
                "No saved listings are ready "
                "for destination processing."
            )
            return

        destination_browser, destination_context, destination_page = (
            open_logged_in_browser(
                playwright,
                DESTINATION_STATE_FILE,
            )
        )

        uploaded = 0
        existing = 0
        would_upload = 0
        already_recorded = 0
        upload_failed = 0
        started_at = time.time()

        try:
            destination_urls = (
                collect_destination_listing_urls(
                    destination_page,
                    DESTINATION_CLOSET_URL,
                )
            )

            total = len(scraped_files)

            for index, listing_file in enumerate(
                scraped_files,
                start=1,
            ):
                listing = load_listing(
                    listing_file
                )

                listing_id = str(
                    listing.get(
                        "listing_id",
                        "unknown",
                    )
                )

                print()
                print("-" * 72)
                print(
                    f"DESTINATION {index}/{total}"
                )
                print("Listing file:", listing_file)

                try:
                    result = retry_operation(
                        lambda listing_file=listing_file: (
                            process_destination_listing(
                                destination_page,
                                listing_file,
                                destination_urls,
                                publish=publish,
                            )
                        ),
                        attempts=retries,
                        delay_seconds=retry_delay,
                        page=destination_page,
                        stage=(
                            "destination_publish"
                            if publish
                            else "destination_dry_run"
                        ),
                        listing_id=listing_id,
                    )

                    if result == "uploaded":
                        uploaded += 1
                    elif result == "already_exists":
                        existing += 1
                    elif result == "would_upload":
                        would_upload += 1
                    elif result == "already_recorded":
                        already_recorded += 1

                except Exception:
                    upload_failed += 1

                    add_completed_listing(
                        listing_id
                    )

                    save_resume_state(
                        mode=(
                            "live_publish"
                            if publish
                            else "dry_run"
                        ),
                        requested_count=count,
                        processed=index,
                        uploaded=uploaded,
                        existing=existing,
                        unavailable=unavailable,
                        failed=upload_failed,
                        already_recorded=already_recorded,
                        would_upload=would_upload,
                        last_listing_id=listing_id,
                        last_listing_title=str(
                            listing.get(
                                "title",
                                "",
                            )
                        ),
                    )

                print_progress(
                    processed=index,
                    total=total,
                    uploaded=uploaded,
                    existing=existing,
                    would_upload=would_upload,
                    failed=upload_failed,
                    started_at=started_at,
                )

        finally:
            destination_context.close()
            destination_browser.close()

    print()
    print("=" * 72)
    print("PIPELINE COMPLETE")
    print("=" * 72)
    print("Source scrape failures:", scrape_failed)
    print("Unavailable after opening:", unavailable)
    print("Uploaded:", uploaded)
    print("Already existed in dveshop:", existing)
    print(
        "Would upload in live mode:",
        would_upload,
    )
    print(
        "Already recorded copied:",
        already_recorded,
    )
    print(
        "Destination failures:",
        upload_failed,
    )
    print(
        "Error artifacts directory:",
        ERRORS_DIR,
    )
    print("=" * 72)
    if clear_resume_state():
        print(
            "Resume checkpoint cleared "
            "because the run completed normally."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the hardened PoshCopier "
            "source-to-destination pipeline."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help=(
            "Maximum number of source "
            "listings to process."
        ),
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help=(
            "Actually publish listings. "
            "Without this flag, the pipeline "
            "is a dry run."
        ),
    )

    parser.add_argument(
        "--discovery-file",
        type=Path,
        default=DISCOVERY_FILE,
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help=(
            "Attempts per scrape or destination "
            "operation."
        ),
    )

    parser.add_argument(
        "--retry-delay",
        type=float,
        default=3.0,
        help=(
            "Seconds to wait between retries."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    run_pipeline(
        count=args.count,
        publish=args.publish,
        discovery_file=args.discovery_file,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )


if __name__ == "__main__":
    main()
