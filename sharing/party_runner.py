"""Guarded validation and one-share execution for live Posh Parties."""

from __future__ import annotations

from collections.abc import Callable

from playwright.sync_api import sync_playwright

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from party.eligibility import is_listing_eligible_for_party
from party.party_manager import PartyManager
from party.party_models import PartyEligibilityStatus
from scraper.availability import AvailabilityStatus, verify_listing_availability
from scraper.listing_scraper import scrape_listing
from sharing.share_config import ShareConfig
from sharing.share_engine import PoshmarkShareEngine, ShareableListing
from sharing.share_progress import ShareError, ShareErrorType, ShareResult
from sharing.share_runner import listing_id_from_url
from uploader.category import split_category


CLOSET_URL = "https://poshmark.com/closet/dveshop"


def _failed(message: str, listing_id: str = "") -> ShareResult:
    return ShareResult(
        success=False,
        failed=1,
        errors=[ShareError(
            error_type=ShareErrorType.PARTY_SHARE_FAILED,
            message=message,
            listing_id=listing_id,
            recoverable=False,
        )],
        message=message,
    )


def run_party_candidate(
    listing_url: str,
    party_name: str,
    *,
    perform_share: bool = False,
    engine_callback: Callable[[PoshmarkShareEngine], None] | None = None,
) -> ShareResult:
    """Validate one destination listing and optionally share it once."""
    listing_id = listing_id_from_url(listing_url)
    if not listing_id:
        return _failed("The listing URL does not contain a valid Poshmark ID")

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            manager = PartyManager()
            parties = manager.discover_parties(page)
            party = next(
                (
                    item for item in parties
                    if item.name == party_name and item.is_live
                ),
                None,
            )
            if party is None:
                return _failed("The selected party is not currently live", listing_id)

            manager.load_guidelines(page, party)
            if party.guidelines is None:
                return _failed("Live party guidelines are unavailable", listing_id)

            page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            availability = verify_listing_availability(page)
            if not availability.available:
                return _failed(f"Listing unavailable: {availability.reason}", listing_id)

            data = scrape_listing(page, listing_url, download_images=False)
            raw_category = data.get("category", "") or ""
            try:
                department, category, subcategory = split_category(raw_category)
            except RuntimeError:
                department, category, subcategory = "", raw_category, ""

            eligibility = is_listing_eligible_for_party(
                {
                    "availability": AvailabilityStatus.AVAILABLE,
                    "brand": data.get("brand", ""),
                    "department": department or "",
                    "category": category or "",
                    "subcategory": subcategory or "",
                    "size": data.get("size", ""),
                },
                party,
            )
            if eligibility.status != PartyEligibilityStatus.ELIGIBLE:
                result = _failed(
                    f"Party eligibility {eligibility.status.value}: {eligibility.reason}",
                    listing_id,
                )
                result.eligibility_status = eligibility.status.value
                result.eligibility_reason = eligibility.reason
                return result

            if not perform_share:
                return ShareResult(
                    success=True,
                    message=f"Eligible: {eligibility.reason}",
                    party_id=party.party_id,
                    party_name=party.name,
                    eligibility_status=eligibility.status.value,
                    eligibility_reason=eligibility.reason,
                )

            listing = ShareableListing(
                listing_id=listing_id,
                url=listing_url,
                title=data.get("title", "Unknown listing"),
                available=True,
                active=True,
                party_eligible=True,
                eligibility_reason=eligibility.reason,
            )
            engine = PoshmarkShareEngine(
                page,
                ShareConfig(
                    closet_url=CLOSET_URL,
                    share_to_parties=True,
                    share_to_posh_shows=False,
                    party_share_limit=1,
                ),
            )
            if engine_callback is not None:
                engine_callback(engine)
            return engine.share_listing_to_party(listing, party, retry=False)
        finally:
            context.close()
            browser.close()
