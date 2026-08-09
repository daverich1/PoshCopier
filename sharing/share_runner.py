"""Application-level runner for safe follower-sharing batches."""

from __future__ import annotations

import re
from collections.abc import Callable

from playwright.sync_api import Page, sync_playwright

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from sharing.share_config import ShareConfig
from sharing.share_engine import PoshmarkShareEngine, ShareableListing
from sharing.share_progress import ShareProgress, ShareResult


LISTING_ID_PATTERN = re.compile(r"([0-9a-f]{24})$", re.IGNORECASE)


def listing_id_from_url(url: str) -> str:
    """Extract a Poshmark listing ID from a listing URL."""
    path = url.rstrip("/").split("?", 1)[0]
    match = LISTING_ID_PATTERN.search(path)
    return match.group(1) if match else ""


def collect_shareable_listings(
    page: Page,
    closet_url: str,
    limit: int,
) -> list[ShareableListing]:
    """Collect unique visible listing cards from a destination closet."""
    page.goto(closet_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    listings: list[ShareableListing] = []
    seen_ids: set[str] = set()
    links = page.locator("a.tile__covershot").all()

    for link in links:
        href = link.get_attribute("href") or ""
        if href.startswith("/"):
            href = f"https://poshmark.com{href}"

        listing_id = listing_id_from_url(href)
        if not listing_id or listing_id in seen_ids:
            continue

        title = link.get_attribute("title") or ""
        if not title:
            try:
                title = link.locator("img").first.get_attribute("alt") or ""
            except Exception:
                title = ""

        seen_ids.add(listing_id)
        listings.append(ShareableListing(
            listing_id=listing_id,
            url=href,
            title=title.strip() or f"Listing {listing_id}",
            available=True,
        ))

        if len(listings) >= limit:
            break

    return listings


def run_follower_sharing(
    config: ShareConfig,
    progress_callback: Callable[[ShareProgress], None] | None = None,
    engine_callback: Callable[[PoshmarkShareEngine], None] | None = None,
) -> ShareResult:
    """Open the destination session, collect listings, and share a batch."""
    if not DESTINATION_STATE_FILE.exists():
        raise FileNotFoundError(
            f"{DESTINATION_STATE_FILE.name} was not found. Save the destination login first."
        )

    limit = config.max_shares
    if limit is None:
        raise ValueError("Dashboard follower sharing requires a finite max_shares")

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            engine = PoshmarkShareEngine(page, config, progress_callback)
            if engine_callback is not None:
                engine_callback(engine)

            listings = collect_shareable_listings(page, config.closet_url, limit)
            if not listings:
                return ShareResult(
                    success=False,
                    failed=1,
                    message="No shareable listings found in the closet",
                )

            return engine.share_batch(listings)
        finally:
            context.close()
            browser.close()
