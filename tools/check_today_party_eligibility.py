"""Find destination-closet listings eligible for today's Posh Parties."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from party.eligibility import is_listing_eligible_for_party
from party.party_manager import PartyManager
from party.party_models import PartyEligibilityStatus
from scraper.availability import AvailabilityStatus, verify_listing_availability
from scraper.listing_scraper import scrape_listing
from uploader.category import split_category


CLOSET_URL = "https://poshmark.com/closet/dveshop"
EXPECTED_TODAY_PARTIES = (
    "Trending: Free People, Anthropologie, Veronica Beard & More Posh Party",
    "Best of Tops & Sweaters Posh Party",
    "Everything Pets Posh Party",
    "Late Summer Looks Posh Party",
)


def collect_listing_urls(page, limit: int) -> list[str]:
    """Collect unique listing URLs currently visible in the closet."""
    page.goto(CLOSET_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    urls: list[str] = []
    seen: set[str] = set()
    for link in page.locator("a.tile__covershot").all():
        href = link.get_attribute("href") or ""
        if href.startswith("/"):
            href = f"https://poshmark.com{href}"
        if href and href not in seen:
            seen.add(href)
            urls.append(href)
        if len(urls) >= limit:
            break
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-limit", type=int, default=40)
    parser.add_argument("--matches-per-party", type=int, default=3)
    parser.add_argument("--party-only", action="store_true")
    args = parser.parse_args()
    if args.scan_limit < 1 or args.matches_per_party < 1:
        parser.error("limits must be positive")

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            manager = PartyManager()
            parties = manager.discover_parties(page)
            today_parties = []
            for expected_name in EXPECTED_TODAY_PARTIES:
                match = next(
                    (party for party in parties if party.name == expected_name),
                    None,
                )
                if match is not None:
                    today_parties.append(match)
            for party in today_parties:
                if not party.guidelines:
                    manager.load_guidelines(page, party)
            print(f"TODAY_PARTIES count={len(today_parties)}", flush=True)
            for party in today_parties:
                confidence = (
                    party.guidelines.parse_confidence.value
                    if party.guidelines else "missing"
                )
                print(
                    f"PARTY name={party.name!r} time={party.start_time_text!r} "
                    f"live={party.is_live} type={party.party_type.value} "
                    f"confidence={confidence}",
                    flush=True,
                )

            if args.party_only:
                return 0

            urls = collect_listing_urls(page, args.scan_limit)
            print(f"LISTINGS_TO_SCAN count={len(urls)}", flush=True)
            matches = {party.party_id: [] for party in today_parties}

            for index, url in enumerate(urls, 1):
                if all(
                    len(matches[party.party_id]) >= args.matches_per_party
                    for party in today_parties
                ):
                    break

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1000)
                    availability = verify_listing_availability(page)
                    if not availability.available:
                        continue
                    data = scrape_listing(page, url, download_images=False)
                    if not data:
                        continue

                    raw_category = data.get("category", "") or ""
                    try:
                        department, category, subcategory = split_category(raw_category)
                    except RuntimeError:
                        department, category, subcategory = "", raw_category, ""

                    listing = {
                        "availability": AvailabilityStatus.AVAILABLE,
                        "brand": data.get("brand", ""),
                        "department": department or "",
                        "category": category or "",
                        "subcategory": subcategory or "",
                        "size": data.get("size", ""),
                    }
                    title = data.get("title", "Unknown listing")
                    print(
                        f"SCAN_PROGRESS {index}/{len(urls)} title={title!r}",
                        flush=True,
                    )

                    for party in today_parties:
                        party_matches = matches[party.party_id]
                        if len(party_matches) >= args.matches_per_party:
                            continue
                        result = is_listing_eligible_for_party(listing, party)
                        if result.status == PartyEligibilityStatus.ELIGIBLE:
                            party_matches.append((title, url, result.reason))
                            print(
                                f"ELIGIBLE party={party.name!r} title={title!r} "
                                f"url={url} reason={result.reason!r}",
                                flush=True,
                            )
                except Exception as error:
                    print(f"SCAN_ERROR url={url} error={error}", flush=True)

            for party in today_parties:
                party_matches = matches[party.party_id]
                print(
                    f"PARTY_RESULT name={party.name!r} live={party.is_live} "
                    f"matches={len(party_matches)}",
                    flush=True,
                )
                for title, url, reason in party_matches:
                    print(
                        f"MATCH title={title!r} url={url} reason={reason!r}",
                        flush=True,
                    )
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
