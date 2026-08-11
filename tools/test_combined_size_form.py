"""Fill one combined-size listing form without advancing or publishing."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from run_pipeline import fill_listing_form
from runtime_paths import LOGS_DIR, configure_playwright_browsers
from uploader.listing_loader import get_image_paths, load_listing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("listing_file", type=Path)
    args = parser.parse_args()

    configure_playwright_browsers()
    listing_file = args.listing_file.resolve()
    listing = load_listing(listing_file)
    image_paths = get_image_paths(listing)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot = LOGS_DIR / f"combined_size_form_test_{stamp}.png"

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            DESTINATION_STATE_FILE,
        )
        try:
            fill_listing_form(page, listing, image_paths)
            actual_title = page.locator(
                'input[name="title"], input[id*="title" i], '
                'input[placeholder*="title" i], '
                'input[placeholder*="selling" i]'
            ).first.input_value()
            if actual_title != listing["title"]:
                raise RuntimeError(
                    "Combined-size form changed the listing title: "
                    f"expected {listing['title']!r}, found {actual_title!r}"
                )
            page.screenshot(path=str(screenshot), full_page=True)
            print("FORM_TEST=PASS")
            print("TITLE_PRESERVED=YES")
            print(f"SCREENSHOT={screenshot}")
            print("PUBLISH_CLICKED=NO")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
