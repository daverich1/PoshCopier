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

        const getStatusLabels = (card) => {
            const labels = [];
            const seen = new Set();

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

                    if (text && !seen.has(normalized)) {
                        labels.push(text);
                        seen.add(normalized);
                    }
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

            return (
                best?.node ||
                anchor.closest("article, li, [role='listitem']") ||
                anchor.parentElement ||
                anchor
            );
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

            results.push({
                url,
                title,
                cardText,
                statusLabels: getStatusLabels(card)
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


def _apply_available_items_filter(page: Page) -> bool:
    """
    Apply Poshmark's "Available Items" filter before discovery.
    
    Returns:
        True if filter was successfully applied, False otherwise.
    """
    try:
        print("Applying Available Items filter...")
        
        # Step 1: Find and click the Availability filter button
        # Try text-based selector first (most resilient)
        availability_button = None
        
        try:
            # Look for button/element containing "Availability" text
            availability_button = page.get_by_text("Availability", exact=False).first
            if availability_button.is_visible(timeout=5000):
                availability_button.click(timeout=5000)
            else:
                availability_button = None
        except Exception:
            availability_button = None
        
        # Fallback: try role-based selector
        if availability_button is None:
            try:
                availability_button = page.locator('button:has-text("Availability")').first
                if availability_button.is_visible(timeout=5000):
                    availability_button.click(timeout=5000)
                else:
                    availability_button = None
            except Exception:
                availability_button = None
        
        if availability_button is None:
            print("Warning: Could not locate Availability filter button")
            return False
        
        # Wait for dropdown/menu to appear
        page.wait_for_timeout(1000)
        
        # Step 2: Select "Available Items" radio option
        radio_option = None
        
        try:
            # Look for radio input with label "Available Items"
            # Try to find the radio button by role first
            radio_option = page.get_by_role("radio", name="Available Items", exact=True)
            if radio_option.is_visible(timeout=5000):
                radio_option.click(timeout=5000)
            else:
                radio_option = None
        except Exception:
            radio_option = None
        
        # Fallback: try finding by label text and associated radio
        if radio_option is None:
            try:
                # Look for label containing "Available Items" and find associated radio
                label = page.locator('label:has-text("Available Items")').first
                if label.is_visible(timeout=5000):
                    # Try to find radio input within or associated with this label
                    radio_option = label.locator('input[type="radio"]').first
                    if not radio_option.is_visible(timeout=1000):
                        # Radio might be a sibling or parent element
                        radio_option = label.locator('..').locator('input[type="radio"]').first
                    
                    if radio_option.is_visible(timeout=1000):
                        radio_option.click(timeout=5000)
                    else:
                        # Click the label itself if radio not directly accessible
                        label.click(timeout=5000)
                        radio_option = label  # Use label as reference for verification
                else:
                    radio_option = None
            except Exception:
                radio_option = None
        
        # Final fallback: click any element with "Available Items" text
        if radio_option is None:
            try:
                radio_option = page.get_by_text("Available Items", exact=True).first
                if radio_option.is_visible(timeout=5000):
                    radio_option.click(timeout=5000)
                else:
                    radio_option = None
            except Exception:
                radio_option = None
        
        if radio_option is None:
            print("Warning: Could not locate Available Items option")
            return False
        
        # Step 3: Verify the radio button is selected
        page.wait_for_timeout(1000)
        
        verified = False
        try:
            # Try to verify the radio is checked
            # Check for aria-checked attribute
            if radio_option.get_attribute("aria-checked", timeout=2000) == "true":
                verified = True
            elif radio_option.get_attribute("checked", timeout=2000) is not None:
                verified = True
            elif radio_option.is_checked(timeout=2000):
                verified = True
        except Exception:
            # If verification fails, try to find any checked radio with "Available Items"
            try:
                checked_radio = page.locator('input[type="radio"][aria-checked="true"]').first
                if checked_radio.is_visible(timeout=2000):
                    # Check if it's associated with "Available Items" label
                    parent = checked_radio.locator('..')
                    if "Available Items" in parent.inner_text(timeout=1000):
                        verified = True
            except Exception:
                pass
        
        if not verified:
            print("Warning: Unable to verify Available Items filter selection.")
        
        # Wait for filter to be applied and page to stabilize
        page.wait_for_timeout(2000)
        
        print("Available Items filter applied.")
        return True
        
    except Exception as e:
        print(f"Warning: Failed to apply Available Items filter: {e}")
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

        new_count, _ = _merge_discovery(
            discovered,
            raw_cards,
        )
        
        # Check if we should stop after merge
        if boundary_reached:
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

        page.evaluate(
            """
            () => window.scrollTo(
                0,
                document.documentElement.scrollHeight
            )
            """
        )
        page.wait_for_timeout(scroll_pause_ms)

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
