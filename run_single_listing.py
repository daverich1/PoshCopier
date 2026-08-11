from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from data.database.database import initialize_database
from login import (
    DESTINATION_STATE_FILE,
    open_logged_in_browser,
)
from pipeline_control import initialize_control_state
from run_pipeline import (
    DESTINATION_CLOSET_URL,
    configure_output_encoding,
    emit_status,
    print_progress,
    process_destination_listing,
    retry_operation,
)
from runtime_paths import (
    configure_playwright_browsers,
    ensure_runtime_directories,
)
from uploader.destination_cache import (
    get_or_refresh_destination_urls,
    save_cache,
)
from uploader.duplicate_detector import (
    collect_destination_listing_urls,
)
from uploader.listing_loader import load_listing
from uploader.size_strategy import SIZE_MODE_COMBINED, validate_size_mode


def run_single_listing(
    listing_file: Path,
    *,
    publish: bool,
    retries: int,
    retry_delay: float,
    size_mode: str = SIZE_MODE_COMBINED,
) -> None:
    listing_file = listing_file.resolve()

    if not listing_file.is_file():
        raise FileNotFoundError(
            f"Listing file was not found:\n{listing_file}"
        )

    if retries < 1:
        raise ValueError(
            "Retries must be at least 1."
        )

    size_mode = validate_size_mode(size_mode)

    configure_playwright_browsers()
    ensure_runtime_directories()
    initialize_database()
    initialize_control_state()

    listing = load_listing(
        listing_file
    )

    listing_id = str(
        listing.get(
            "listing_id",
            "",
        )
    ).strip()

    if not listing_id:
        raise RuntimeError(
            "The selected listing has no listing_id."
        )

    title = str(
        listing.get(
            "title",
            "",
        )
    ).strip()

    sizes = listing.get(
        "sizes"
    ) or [
        listing.get(
            "size",
            "",
        )
    ]

    size_text = ", ".join(
        str(value).strip()
        for value in sizes
        if str(value).strip()
    )

    print("=" * 72)
    print("POSHCOPIER — SELECTED LISTING")
    print("=" * 72)
    print("Listing file:", listing_file)
    print("Title:", title)
    print(
        "Mode:",
        "LIVE PUBLISH"
        if publish
        else "DRY RUN",
    )
    print("=" * 72)

    emit_status(
        "MODE",
        "LIVE PUBLISH"
        if publish
        else "DRY RUN",
    )
    emit_status(
        "TITLE",
        title,
    )
    emit_status(
        "LISTING_ID",
        listing_id,
    )
    emit_status(
        "PRICE",
        str(
            listing.get(
                "price",
                "",
            )
        ),
    )
    emit_status(
        "SIZES",
        size_text,
    )
    emit_status(
        "TOTAL",
        "1",
    )
    emit_status(
        "STEP",
        "Opening Destination Browser",
    )

    uploaded = 0
    existing = 0
    would_upload = 0
    already_recorded = 0
    publish_unverified = 0
    failed = 0
    started_at = time.time()

    with sync_playwright() as playwright:
        browser, context, page = (
            open_logged_in_browser(
                playwright,
                DESTINATION_STATE_FILE,
            )
        )

        try:
            emit_status(
                "STEP",
                "Scanning Destination Closet",
            )

            destination_urls = (
                get_or_refresh_destination_urls(
                    page,
                    DESTINATION_CLOSET_URL,
                )
            )

            emit_status(
                "STEP",
                "Processing Selected Listing",
            )

            try:
                result = retry_operation(
                    lambda: process_destination_listing(
                        page,
                        listing_file,
                        destination_urls,
                        publish=publish,
                        size_mode=size_mode,
                    ),
                    attempts=retries,
                    delay_seconds=retry_delay,
                    page=page,
                    stage=(
                        "selected_listing_publish"
                        if publish
                        else "selected_listing_dry_run"
                    ),
                    listing_id=listing_id,
                )

                if result == "uploaded":
                    uploaded = 1
                elif result == "already_exists":
                    existing = 1
                elif result == "would_upload":
                    would_upload = 1
                elif result == "already_recorded":
                    already_recorded = 1
                elif result == "publish_unverified":
                    publish_unverified = 1

            except Exception:
                failed = 1
                emit_status(
                    "STEP",
                    "Selected Listing Failed",
                )
                raise

            print_progress(
                processed=1,
                total=1,
                uploaded=uploaded,
                existing=existing,
                would_upload=would_upload,
                failed=failed,
                started_at=started_at,
            )

        finally:
            context.close()
            browser.close()

    emit_status(
        "STEP",
        "Selected Listing Complete",
    )
    emit_status(
        "UPLOADED",
        str(uploaded),
    )
    emit_status(
        "EXISTING",
        str(existing),
    )
    emit_status(
        "PUBLISH_UNVERIFIED",
        str(publish_unverified),
    )
    emit_status(
        "FAILED",
        str(failed),
    )
    emit_status(
        "PERCENT",
        "100.0",
    )

    print()
    print("=" * 72)
    print("SELECTED LISTING COMPLETE")
    print("=" * 72)
    print("Uploaded:", uploaded)
    print("Already existed:", existing)
    print("Would upload:", would_upload)
    print("Already recorded copied:", already_recorded)
    print("Publish unverified:", publish_unverified)
    print("Failed:", failed)
    print("=" * 72)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process one selected PoshCopier listing."
        )
    )

    parser.add_argument(
        "--listing-file",
        type=Path,
        required=True,
        help=(
            "Path to the selected listing.json file."
        ),
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help=(
            "Publish the selected listing. "
            "Without this option, the command "
            "performs a dry run."
        ),
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--retry-delay",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--size-mode",
        choices=("combined", "separate"),
        default="combined",
    )

    return parser


def main() -> None:
    configure_output_encoding()

    parser = build_parser()
    args = parser.parse_args()

    run_single_listing(
        args.listing_file,
        publish=args.publish,
        retries=args.retries,
        retry_delay=args.retry_delay,
        size_mode=args.size_mode,
    )


if __name__ == "__main__":
    main()
