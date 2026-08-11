"""Application-level runner for safe follower-sharing batches."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from scraper.availability import verify_listing_availability
from scraper.discover import _apply_available_items_filter
from sharing.share_config import ShareConfig
from sharing.share_engine import PoshmarkShareEngine, ShareableListing
from sharing.share_progress import ShareProgress, ShareResult


LISTING_ID_PATTERN = re.compile(r"([0-9a-f]{24})$", re.IGNORECASE)
POSHMARK_HOSTS = {"poshmark.com", "www.poshmark.com"}


def listing_id_from_url(url: str) -> str:
    """Extract a Poshmark listing ID from a listing URL."""
    path = url.rstrip("/").split("?", 1)[0]
    match = LISTING_ID_PATTERN.search(path)
    return match.group(1) if match else ""


def closet_name_from_url(url: str) -> str:
    """Return a normalized username for a valid Poshmark closet URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in POSHMARK_HOSTS:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0].lower() != "closet":
        return ""
    return parts[1].lower()


def collect_shareable_listings(
    page: Page,
    closet_url: str,
    limit: int,
) -> list[ShareableListing]:
    """Collect unique listing cards across the closet's lazy-loaded pages."""
    if limit < 1:
        return []
    page.goto(closet_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    if not _apply_available_items_filter(page):
        raise RuntimeError(
            "Could not verify Poshmark's Available Items and Active Items filters; "
            "sharing discovery stopped."
        )

    candidates: list[ShareableListing] = []
    seen_ids: set[str] = set()
    unchanged_passes = 0

    for _ in range(60):
        count_before = len(candidates)
        for link in page.locator("a.tile__covershot").all():
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
            candidates.append(ShareableListing(
                listing_id=listing_id,
                url=href,
                title=title.strip() or f"Listing {listing_id}",
                available=False,
                active=None,
            ))

        if len(candidates) == count_before:
            unchanged_passes += 1
        else:
            unchanged_passes = 0
        if unchanged_passes >= 3:
            break

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)

    listings: list[ShareableListing] = []
    for candidate in candidates:
        try:
            page.goto(
                candidate.url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(1000)
            availability = verify_listing_availability(page)
        except Exception:
            continue
        if not availability.available:
            continue
        candidate.available = True
        candidate.active = True
        listings.append(candidate)
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


def run_community_sharing(
    config: ShareConfig,
    own_closet_url: str,
    *,
    perform_share: bool = False,
    progress_callback: Callable[[ShareProgress], None] | None = None,
    engine_callback: Callable[[PoshmarkShareEngine], None] | None = None,
) -> ShareResult:
    """Validate or share a finite batch from a different seller's closet."""
    source_name = closet_name_from_url(config.closet_url)
    own_name = closet_name_from_url(own_closet_url)
    if not source_name:
        raise ValueError("Enter a valid https://poshmark.com/closet/USERNAME URL")
    if not own_name:
        raise ValueError("The configured destination closet URL is invalid")
    if source_name == own_name:
        raise ValueError("Community sharing requires a closet other than your own")
    if config.community_share_limit is None:
        raise ValueError("Community sharing requires a finite share limit")
    if perform_share and not config.share_community_listings:
        raise ValueError("Community sharing is disabled")
    if not DESTINATION_STATE_FILE.exists():
        raise FileNotFoundError(
            f"{DESTINATION_STATE_FILE.name} was not found. Save the destination login first."
        )

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            engine = PoshmarkShareEngine(page, config, progress_callback)
            if engine_callback is not None:
                engine_callback(engine)
            listings = collect_shareable_listings(
                page,
                config.closet_url,
                config.community_share_limit,
            )
            if not listings:
                return ShareResult(
                    success=False,
                    failed=1,
                    message="No shareable listings found in the community closet",
                )
            if not perform_share:
                return ShareResult(
                    success=True,
                    skipped=len(listings),
                    message=f"Validated {len(listings)} unique community listing(s)",
                )
            return engine.share_community_batch(listings)
        finally:
            context.close()
            browser.close()
