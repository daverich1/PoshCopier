from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import Page, sync_playwright

try:
    from .availability import classify_card_status
except ImportError:
    from availability import classify_card_status


# Incremental sync threshold - stop after this many consecutive known listings
DEFAULT_INCREMENTAL_THRESHOLD = 50


@dataclass(slots=True)
class DiscoveredListing:
    listing_id: str
    url: str
    title: str
    card_status: str
    available: bool
    card_text: str = ""
    matched_status_text: str = ""


# Backward-compatible result types used by the root scraper.py.
# These let the newer discovery engine work with the existing scraper
# without removing any of the current discovery functionality.
@dataclass(slots=True)
class UnavailableCard:
    url: str
    status: str
    unavailable_reason: str | None
    listing_id: str = ""
    title: str = ""


@dataclass(slots=True)
class DiscoveryResult:
    available_urls: list[str]
    unavailable_cards: list[UnavailableCard]
    total_cards: int


def canonicalize_listing_url(
    url: str,
    base_url: str = "https://poshmark.com",
) -> str:
    absolute = urljoin(base_url, url)
    parsed = urlsplit(absolute)

    return urlunsplit(
        (
            parsed.scheme or "https",
            parsed.netloc or "poshmark.com",
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def listing_id_from_url(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]

    match = re.search(r"(?:-|^)([a-fA-F0-9]{24})$", slug)

    if match:
        return match.group(1).lower()

    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]



def extract_listing_id(listing_url: str) -> str:
    """
    Backward-compatible alias used by the existing root scraper.py.
    """
    return listing_id_from_url(
        canonicalize_listing_url(listing_url)
    )


def _extract_cards_from_page(page: Page) -> list[dict[str, Any]]:
    script = r"""
    () => {
        const normalizeHref = (href) => {
            try {
                const url = new URL(href, window.location.origin);
                url.hash = "";
                url.search = "";
                return url.toString().replace(/\/$/, "");
            } catch {
                return "";
            }
        };

        const uniqueListingUrls = (node) => {
            const urls = new Set();

            if (node.matches && node.matches('a[href*="/listing/"]')) {
                const ownHref = normalizeHref(node.href);
                if (ownHref) {
                    urls.add(ownHref);
                }
            }

            for (const anchor of node.querySelectorAll('a[href*="/listing/"]')) {
                const href = normalizeHref(anchor.href);
                if (href) {
                    urls.add(href);
                }
            }

            return urls;
        };

        const statusSelectors = [
    '[data-et-name*="sold" i]',
    '[data-et-name*="availability" i]',
    '[data-et-name*="inactive" i]',
    '[data-test*="sold" i]',
    '[data-test*="availability" i]',
    '[data-test*="inactive" i]',
    '[class*="sold-out" i]',
    '[class*="sold_out" i]',
    '[class~="sold"]',
    '[class*="not-for-sale" i]',
    '[class*="not_for_sale" i]',
    '[class*="inactive" i]',
    '[class*="listing-status" i]',
    '[class*="listing_status" i]',
    '[class*="inventory-tag" i]',
    '[class*="inventory_tag" i]',
    '[class*="availability" i]',
    '[aria-label="Sold" i]',
    '[aria-label="Sold Out" i]',
    '[aria-label="Not For Sale" i]',
    '[aria-label="Inactive" i]'
];

        const getStatusLabels = (card, listingUrl) => {
            const labels = [];
            const seen = new Set();
            
            // Known Poshmark status overlay class - prioritize this
            const preferredOverlay = card.querySelector('.tile-grid-redesign__listing-status-overlay');
            
            // Valid unavailable status texts (normalized)
            const validStatuses = new Set([
                'sold',
                'sold out',
                'not for sale',
                'inactive',
                'unavailable',
                'not available'
            ]);

            for (const selector of statusSelectors) {
                for (const node of card.querySelectorAll(selector)) {
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);

                    const visible =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden";

                    if (!visible) {
                        continue;
                    }

                    const text = (node.innerText || node.textContent || "")
                        .replace(/\s+/g, " ")
                        .trim();

                    const normalized = text.toLowerCase();

                    // Skip if text is empty or already seen
                    if (!text || seen.has(normalized)) {
                        continue;
                    }
                    
                    // Only accept text that matches known unavailable statuses
                    if (!validStatuses.has(normalized)) {
                        continue;
                    }
                    
                    // Check if this status node belongs to a nested/neighboring listing
                    // by checking if it contains or is contained by a different listing link
                    const nodeListingUrls = uniqueListingUrls(node);
                    
                    // If the status node itself contains listing links, ensure they match our card
                    if (nodeListingUrls.size > 0 && !nodeListingUrls.has(listingUrl)) {
                        continue; // This status belongs to a different listing
                    }
                    
                    // Check if the status node is inside a nested listing anchor
                    let parent = node.parentElement;
                    let isNestedInDifferentListing = false;
                    
                    for (let i = 0; i < 5 && parent && parent !== card; i++) {
                        if (parent.matches && parent.matches('a[href*="/listing/"]')) {
                            const parentHref = normalizeHref(parent.href);
                            if (parentHref && parentHref !== listingUrl) {
                                isNestedInDifferentListing = true;
                                break;
                            }
                        }
                        parent = parent.parentElement;
                    }
                    
                    if (isNestedInDifferentListing) {
                        continue; // This status is inside a different listing's anchor
                    }
                    
                    // Prefer the known overlay class if it exists
                    if (preferredOverlay && !preferredOverlay.contains(node) && node !== preferredOverlay) {
                        // If we have a preferred overlay and this node isn't part of it, skip it
                        // unless we haven't found any labels yet
                        if (labels.length > 0) {
                            continue;
                        }
                    }

                    labels.push(text);
                    seen.add(normalized);
                }
            }

            return labels;
        };

        const chooseCard = (anchor, listingUrl) => {
            let node = anchor;
            let best = null;

            for (let depth = 0; depth <= 8 && node; depth += 1) {
                if (
                    node === document.body ||
                    node === document.documentElement
                ) {
                    break;
                }

                const urls = uniqueListingUrls(node);
                const text = (node.innerText || "")
                    .replace(/\s+/g, " ")
                    .trim();

                const rect = node.getBoundingClientRect();
                const area =
                    Math.max(rect.width, 1) *
                    Math.max(rect.height, 1);

                // DEFENSIVE CHECK: Reject candidates with multiple distinct listing URLs
                // This prevents selecting a parent container that includes neighboring cards
                const valid =
                    urls.has(listingUrl) &&
                    urls.size === 1 &&
                    text.length <= 1800 &&
                    rect.width >= 80 &&
                    rect.height >= 80;

                if (valid) {
                    const candidate = {
                        node,
                        depth,
                        area
                    };

                    if (
                        !best ||
                        candidate.area < best.area ||
                        (
                            candidate.area === best.area &&
                            candidate.depth > best.depth
                        )
                    ) {
                        best = candidate;
                    }
                }

                node = node.parentElement;
            }

            const chosenCard = (
                best?.node ||
                anchor.closest("article, li, [role='listitem']") ||
                anchor.parentElement ||
                anchor
            );
            
            // Final validation: ensure chosen card doesn't contain multiple listings
            const finalUrls = uniqueListingUrls(chosenCard);
            if (finalUrls.size > 1) {
                // Fall back to a more conservative choice
                return anchor.parentElement || anchor;
            }
            
            return chosenCard;
        };

        const anchors = Array.from(
            document.querySelectorAll('a[href*="/listing/"]')
        );

        const results = [];
        const seenUrls = new Set();

        for (const anchor of anchors) {
            const rawHref =
                anchor.href ||
                anchor.getAttribute("href");

            if (!rawHref) {
                continue;
            }

            const url = normalizeHref(rawHref);

            if (
                !url ||
                !/\/listing\//i.test(url) ||
                seenUrls.has(url)
            ) {
                continue;
            }

            const card = chooseCard(anchor, url);

            const cardText = (
                card.innerText ||
                card.textContent ||
                ""
            )
                .replace(/\u00a0/g, " ")
                .replace(/[ \t]+/g, " ")
                .replace(/\n{3,}/g, "\n\n")
                .trim();

            const image = card.querySelector("img");

            const titleCandidates = [
                anchor.getAttribute("aria-label"),
                anchor.getAttribute("title"),
                image?.getAttribute("alt"),
                card.querySelector(
                    '[data-et-name*="title" i], [class*="title" i]'
                )?.textContent
            ];

            const title = titleCandidates
                .map(
                    value => (value || "")
                        .replace(/\s+/g, " ")
                        .trim()
                )
                .find(Boolean) || "";

            const cardUrls = uniqueListingUrls(card);
            
            results.push({
                url,
                title,
                cardText,
                statusLabels: getStatusLabels(card, url),
                cardUrlCount: cardUrls.size
            });

            seenUrls.add(url);
        }

        return results;
    }
    """

    result = page.evaluate(script)

    if not isinstance(result, list):
        return []

    return [
        item
        for item in result
        if isinstance(item, dict)
    ]


def _count_listing_cards(page: Page) -> int:
    """
    Quickly count the number of listing cards on the page without full extraction.
    This is much faster than _extract_cards_from_page() for dynamic wait checks.
    """
    script = r"""
    () => {
        const anchors = document.querySelectorAll('a[href*="/listing/"]');
        const uniqueUrls = new Set();
        
        for (const anchor of anchors) {
            const href = anchor.href || anchor.getAttribute("href");
            if (href && /\/listing\//i.test(href)) {
                try {
                    const url = new URL(href, window.location.origin);
                    url.hash = "";
                    url.search = "";
                    const normalized = url.toString().replace(/\/$/, "");
                    uniqueUrls.add(normalized);
                } catch {
                    // Skip invalid URLs
                }
            }
        }
        
        return uniqueUrls.size;
    }
    """
    
    try:
        result = page.evaluate(script)
        return int(result) if isinstance(result, (int, float)) else 0
    except Exception:
        return 0


def _listing_exists_locally(listing_id: str, downloads_dir: Path) -> bool:
    """Check if listing already exists in downloads directory."""
    listing_file = downloads_dir / listing_id / "listing.json"
    return listing_file.exists()


def _merge_discovery(
    discovered: dict[str, DiscoveredListing],
    raw_cards: list[dict[str, Any]],
) -> tuple[int, int]:
    new_count = 0
    updated_count = 0
    
    # Diagnostic counter for first 10 cards
    diagnostic_count = 0

    for raw in raw_cards:
        url = canonicalize_listing_url(
            str(raw.get("url", ""))
        )

        if not url or "/listing/" not in url:
            continue

        listing_id = listing_id_from_url(url)
        card_text = str(raw.get("cardText", "") or "")

        raw_labels = raw.get("statusLabels", [])
        status_labels = (
            [str(value) for value in raw_labels if isinstance(value, str)]
            if isinstance(raw_labels, list)
            else []
        )

        availability = classify_card_status(
            card_text,
            status_labels,
        )

        item = DiscoveredListing(
            listing_id=listing_id,
            url=url,
            title=str(raw.get("title", "") or "").strip(),
            card_status=availability.status.value,
            available=availability.available,
            card_text=card_text[:2000],
            matched_status_text=availability.matched_text[:500],
        )
        
        # Diagnostic output for first 10 cards
        if diagnostic_count < 10:
            card_url_count = raw.get("cardUrlCount", "unknown")
            print(f"\n[DIAGNOSTIC {diagnostic_count + 1}/10]")
            print(f"  URL: {url}")
            print(f"  Card URL count: {card_url_count}")
            print(f"  Status labels: {status_labels if status_labels else '(none)'}")
            print(f"  Classification: {availability.status.value} (available={availability.available})")
            if availability.matched_text:
                print(f"  Matched text: {availability.matched_text[:100]}")
            diagnostic_count += 1

        existing = discovered.get(listing_id)

        if existing is None:
            discovered[listing_id] = item
            new_count += 1
            continue

        changed = False

        if not existing.title and item.title:
            existing.title = item.title
            changed = True

        if not existing.card_text and item.card_text:
            existing.card_text = item.card_text
            changed = True

        if existing.available and not item.available:
            existing.available = False
            existing.card_status = item.card_status
            existing.matched_status_text = item.matched_status_text
            changed = True

        if changed:
            updated_count += 1

    return new_count, updated_count


def _ensure_radio_selected(
    page: Page,
    selector: str,
    success_message: str,
) -> bool:
    """
    Reusable helper to ensure a radio button is selected.
    
    Args:
        page: Playwright page object
        selector: CSS selector for the radio input
        success_message: Message to print when filter is applied
    
    Returns:
        True if radio was successfully selected and verified, False otherwise.
    """
    try:
        # Locate the exact radio with .first
        radio = page.locator(selector).first
        
        # Check if already checked
        try:
            if radio.is_checked(timeout=1000):
                return True
        except Exception:
            pass  # Proceed to select if we can't determine state
        
        # Try to check with force=True (does not require visibility)
        try:
            radio.check(force=True)
        except Exception:
            # If check() fails, try evaluate click
            try:
                radio.evaluate("(element) => element.click()")
            except Exception as e:
                print(f"Warning: Failed to select radio {selector}: {e}")
                return False
        
        # Wait for state to settle
        page.wait_for_timeout(1500)
        
        # Verify the radio is now checked
        try:
            if radio.is_checked(timeout=1000):
                print(success_message)
                return True
            else:
                print(f"Warning: Unable to verify radio selection for {selector}")
                return False
        except Exception as e:
            print(f"Warning: Unable to verify radio selection for {selector}: {e}")
            return False
        
    except Exception as e:
        print(f"Warning: Failed to ensure radio selected for {selector}: {e}")
        return False


def _apply_available_items_filter(page: Page) -> bool:
    """
    Apply Poshmark's "Available Items" and "Active Items" filters before discovery.
    
    Returns:
        True if both filters were successfully applied, False otherwise.
    """
    try:
        # Step 1: Open the Availability filter dropdown
        try:
            availability_button = page.get_by_text("Availability", exact=False).first
            if availability_button.is_visible(timeout=5000):
                availability_button.click(timeout=5000)
                page.wait_for_timeout(1000)
            else:
                print("Warning: Availability filter button not visible")
                return False
        except Exception as e:
            print(f"Warning: Could not open Availability filter: {e}")
            return False
        
        # Step 2: Ensure availability=available is selected
        availability_selector = 'input[name="availability"][value="available"]'
        
        # Check if already selected before attempting to select
        try:
            radio = page.locator(availability_selector).first
            if radio.is_checked(timeout=1000):
                print("Available Items filter already selected.")
                availability_success = True
            else:
                availability_success = _ensure_radio_selected(
                    page,
                    availability_selector,
                    "Available Items filter applied.",
                )
        except Exception:
            availability_success = _ensure_radio_selected(
                page,
                availability_selector,
                "Available Items filter applied.",
            )
        
        if not availability_success:
            print("Warning: Could not apply Available Items filter")
            # Continue anyway, don't crash
        
        # Step 3: Ensure status=active is selected
        status_selector = 'input[name="status"][value="active"]'
        
        # Check if already selected before attempting to select
        try:
            radio = page.locator(status_selector).first
            if radio.is_checked(timeout=1000):
                print("Active Items filter already selected.")
                status_success = True
            else:
                status_success = _ensure_radio_selected(
                    page,
                    status_selector,
                    "Active Items filter applied.",
                )
        except Exception:
            status_success = _ensure_radio_selected(
                page,
                status_selector,
                "Active Items filter applied.",
            )
        
        if not status_success:
            print("Warning: Could not apply Active Items filter")
            # Continue anyway, don't crash
        
        # Return True only if both succeeded
        return availability_success and status_success
        
    except Exception as e:
        print(f"Warning: Failed to apply filters: {e}")
        return False


def discover_closet(
    page: Page,
    closet_url: str,
    *,
    max_scrolls: int = 600,
    stable_rounds_required: int = 8,
    scroll_pause_ms: int = 1200,
    progress_path: Path | None = None,
    downloads_dir: Path | None = None,
    incremental_threshold: int = DEFAULT_INCREMENTAL_THRESHOLD,
    max_new_listings: int | None = None,
) -> list[DiscoveredListing]:
    print(f"Opening source closet: {closet_url}")

    page.goto(
        closet_url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    page.wait_for_timeout(3000)

    # Apply Available Items filter before discovery
    _apply_available_items_filter(page)

    discovered: dict[str, DiscoveredListing] = {}
    stable_rounds = 0
    previous_count = 0
    previous_height = 0
    
    # Incremental sync initialization
    boundary_reached = False
    import_limit_reached = False
    stopping_reason = "End of closet"
    if downloads_dir is not None:
        print("Incremental Sync Enabled")
        processed_incremental_ids: set[str] = set()
        consecutive_existing = 0
        new_listings_count = 0
        existing_listings_count = 0

    for scroll_number in range(1, max_scrolls + 1):
        raw_cards = _extract_cards_from_page(page)
        
        # Incremental boundary check (if enabled)
        if downloads_dir is not None and not boundary_reached:
            for raw in raw_cards:
                url = canonicalize_listing_url(str(raw.get("url", "")))
                if not url or "/listing/" not in url:
                    continue
                
                listing_id = listing_id_from_url(url)
                
                if listing_id in processed_incremental_ids:
                    continue
                
                processed_incremental_ids.add(listing_id)
                
                # Check availability
                raw_labels = raw.get("statusLabels", [])
                status_labels = (
                    [str(v) for v in raw_labels if isinstance(v, str)]
                    if isinstance(raw_labels, list)
                    else []
                )
                card_text = str(raw.get("cardText", "") or "")
                availability = classify_card_status(card_text, status_labels)
                
                if not availability.available:
                    continue
                
                # Check if exists locally
                if _listing_exists_locally(listing_id, downloads_dir):
                    consecutive_existing += 1
                    existing_listings_count += 1
                    print(f"Known listing found ({consecutive_existing} consecutive)")
                    
                    # Check threshold immediately
                    if consecutive_existing >= incremental_threshold:
                        stopping_reason = "Incremental boundary reached"
                        boundary_reached = True
                        break
                else:
                    consecutive_existing = 0
                    new_listings_count += 1
                    
                    # Check max_new_listings limit
                    if max_new_listings is not None:
                        print(f"New listing found ({new_listings_count}/{max_new_listings})")
                        
                        if new_listings_count >= max_new_listings:
                            stopping_reason = "Import limit reached"
                            import_limit_reached = True
                            boundary_reached = True
                            break

        new_count, _ = _merge_discovery(
            discovered,
            raw_cards,
        )
        
        # Check if we should stop after merge
        if boundary_reached:
            if import_limit_reached:
                print(f"\nImport limit reached ({new_listings_count} new listings).")
                print("Stopping discovery.")
            else:
                print("\nReached sync boundary. Stopping discovery.")
            break

        current_count = len(discovered)

        try:
            current_height = int(
                page.evaluate(
                    """
                    () => Math.max(
                        document.body.scrollHeight,
                        document.documentElement.scrollHeight
                    )
                    """
                )
            )
        except Exception:
            current_height = previous_height

        available_count = sum(
            item.available
            for item in discovered.values()
        )
        unavailable_count = (
            current_count - available_count
        )

        print(
            f"\rScroll {scroll_number:>3} | "
            f"found {current_count:>4} | "
            f"available {available_count:>4} | "
            f"unavailable {unavailable_count:>4}",
            end="",
            flush=True,
        )

        if progress_path is not None:
            save_discovery_results(
                list(discovered.values()),
                progress_path,
            )

        unchanged = (
            current_count == previous_count
            and current_height == previous_height
            and new_count == 0
        )

        if unchanged:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= stable_rounds_required:
            break

        previous_count = current_count
        previous_height = current_height

        # Dynamic wait after scroll
        page.evaluate(
            """
            () => window.scrollTo(
                0,
                document.documentElement.scrollHeight
            )
            """
        )
        
        # Dynamic wait parameters
        check_interval_ms = 150
        minimum_wait_ms = 600
        stable_checks_needed = 4
        max_wait_ms = 2500
        
        # Track timing and card growth
        wait_start_time = time.time()
        elapsed_ms = 0
        previous_card_count = _count_listing_cards(page)
        stable_check_count = 0
        
        # Dynamic wait loop
        while elapsed_ms < max_wait_ms:
            page.wait_for_timeout(check_interval_ms)
            elapsed_ms = (time.time() - wait_start_time) * 1000
            
            current_card_count = _count_listing_cards(page)
            
            if current_card_count > previous_card_count:
                # Growth detected, reset stability counter
                previous_card_count = current_card_count
                stable_check_count = 0
            else:
                # No growth detected
                stable_check_count += 1
                
                # Only allow early exit after minimum wait period
                if elapsed_ms >= minimum_wait_ms:
                    if stable_check_count >= stable_checks_needed:
                        # Stable for required checks, exit early
                        break

        if scroll_number % 5 == 0:
            page.evaluate("() => window.scrollBy(0, -500)")
            page.wait_for_timeout(250)

            page.evaluate(
                """
                () => window.scrollTo(
                    0,
                    document.documentElement.scrollHeight
                )
                """
            )
            page.wait_for_timeout(500)

    print()

    results = sorted(
        discovered.values(),
        key=lambda item: item.listing_id,
    )

    active_count = sum(
        item.available
        for item in results
    )
    inactive_count = len(results) - active_count

    print(f"Discovery complete: {len(results)} total")
    print(f"Active card candidates: {active_count}")
    print(f"Unavailable card candidates: {inactive_count}")
    
    # Report incremental sync statistics
    if downloads_dir is not None:
        print(f"Stopping reason: {stopping_reason}")
        print(f"New listings: {new_listings_count}")
        print(f"Existing listings: {existing_listings_count}")

    return results


def discover_closet_listings(
    page: Page,
    closet_url: str,
    *,
    max_scrolls: int = 600,
    stable_rounds_required: int = 8,
    scroll_pause_ms: int = 1200,
    progress_path: Path | None = None,
    downloads_dir: Path | None = None,
    incremental_threshold: int = DEFAULT_INCREMENTAL_THRESHOLD,
    max_new_listings: int | None = None,
) -> DiscoveryResult:
    """
    Backward-compatible wrapper for the existing root scraper.py.

    The newer discovery engine returns a list[DiscoveredListing].
    The older root scraper expects:
      - available_urls
      - unavailable_cards
      - total_cards

    This wrapper provides that shape without changing the newer
    discover_closet() implementation.
    """
    listings = discover_closet(
        page,
        closet_url,
        max_scrolls=max_scrolls,
        stable_rounds_required=stable_rounds_required,
        scroll_pause_ms=scroll_pause_ms,
        progress_path=progress_path,
        downloads_dir=downloads_dir,
        incremental_threshold=incremental_threshold,
        max_new_listings=max_new_listings,
    )

    available_urls = [
        item.url
        for item in listings
        if item.available
    ]

    unavailable_cards = [
        UnavailableCard(
            url=item.url,
            status=item.card_status,
            unavailable_reason=(
                item.matched_status_text
                or item.card_status
                or None
            ),
            listing_id=item.listing_id,
            title=item.title,
        )
        for item in listings
        if not item.available
    ]

    return DiscoveryResult(
        available_urls=available_urls,
        unavailable_cards=unavailable_cards,
        total_cards=len(listings),
    )


def save_discovery_results(
    listings: list[DiscoveredListing],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "saved_at": time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        ),
        "total": len(listings),
        "available": sum(
            item.available
            for item in listings
        ),
        "unavailable": sum(
            not item.available
            for item in listings
        ),
        "listings": [
            asdict(item)
            for item in listings
        ],
    }

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover Poshmark closet listings."
    )

    parser.add_argument(
        "--closet-url",
        required=True,
    )
    parser.add_argument(
        "--state",
        default="source_state.json",
    )
    parser.add_argument(
        "--output",
        default="downloads/discovered_listings.json",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=600,
    )
    parser.add_argument(
        "--stable-rounds",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--scroll-pause",
        type=int,
        default=1200,
    )

    args = parser.parse_args()

    state_path = Path(args.state)

    if not state_path.exists():
        raise FileNotFoundError(
            "Playwright storage state not found: "
            f"{state_path.resolve()}"
        )

    output_path = Path(args.output)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=args.headless,
        )

        context = browser.new_context(
            storage_state=str(state_path),
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = context.new_page()

        try:
            listings = discover_closet(
                page,
                args.closet_url,
                max_scrolls=args.max_scrolls,
                stable_rounds_required=args.stable_rounds,
                scroll_pause_ms=args.scroll_pause,
                progress_path=output_path,
            )

            save_discovery_results(
                listings,
                output_path,
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
