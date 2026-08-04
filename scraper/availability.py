from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from playwright.sync_api import Page


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    SOLD = "sold"
    SOLD_OUT = "sold_out"
    NOT_FOR_SALE = "not_for_sale"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class AvailabilityResult:
    status: AvailabilityStatus
    available: bool
    reason: str = ""
    matched_text: str = ""


EXACT_STATUS_MAP: dict[str, AvailabilityStatus] = {
    "sold": AvailabilityStatus.SOLD,
    "sold out": AvailabilityStatus.SOLD_OUT,
    "not for sale": AvailabilityStatus.NOT_FOR_SALE,
    "not available": AvailabilityStatus.UNAVAILABLE,
    "unavailable": AvailabilityStatus.UNAVAILABLE,
    "listing unavailable": AvailabilityStatus.UNAVAILABLE,
    "this listing is no longer available": AvailabilityStatus.UNAVAILABLE,
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip().lower()


def status_from_text(value: str | None) -> AvailabilityStatus:
    """
    Classify text only when it looks like an exact availability label.

    This avoids false matches from descriptions containing sentences such as:
    "This style sold in department stores."
    """
    normalized = normalize_text(value)

    if not normalized:
        return AvailabilityStatus.UNKNOWN

    if normalized in EXACT_STATUS_MAP:
        return EXACT_STATUS_MAP[normalized]

    lines = [
        normalize_text(line)
        for line in re.split(r"[\r\n|•]+", value or "")
        if normalize_text(line)
    ]

    for line in lines:
        if line in EXACT_STATUS_MAP:
            return EXACT_STATUS_MAP[line]

    return AvailabilityStatus.UNKNOWN


def classify_card_status(
    card_text: str,
    status_labels: list[str] | None = None,
) -> AvailabilityResult:
    """
    Determine availability using text from one individual listing card.

    Dedicated status labels are checked first. The general card text is only
    used as a fallback.
    """
    for label in status_labels or []:
        status = status_from_text(label)

        if status != AvailabilityStatus.UNKNOWN:
            return AvailabilityResult(
                status=status,
                available=False,
                reason="Unavailable status found on the listing card.",
                matched_text=label,
            )

    status = status_from_text(card_text)

    if status != AvailabilityStatus.UNKNOWN:
        return AvailabilityResult(
            status=status,
            available=False,
            reason="Unavailable status found in the listing card text.",
            matched_text=card_text,
        )

    return AvailabilityResult(
        status=AvailabilityStatus.AVAILABLE,
        available=True,
        reason="No unavailable status was found on this listing card.",
    )


def _availability_from_json_ld(
    page: Page,
) -> AvailabilityResult | None:
    scripts = page.locator('script[type="application/ld+json"]')

    for index in range(scripts.count()):
        try:
            raw = scripts.nth(index).text_content(timeout=1_000)
        except Exception:
            continue

        if not raw:
            continue

        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            continue

        records: list[dict[str, Any]] = []

        if isinstance(payload, dict):
            records.append(payload)

            graph = payload.get("@graph")

            if isinstance(graph, list):
                records.extend(
                    item
                    for item in graph
                    if isinstance(item, dict)
                )

        elif isinstance(payload, list):
            records.extend(
                item
                for item in payload
                if isinstance(item, dict)
            )

        for record in records:
            offers = record.get("offers")

            if isinstance(offers, dict):
                offers = [offers]

            if not isinstance(offers, list):
                continue

            for offer in offers:
                if not isinstance(offer, dict):
                    continue

                availability = normalize_text(
                    str(offer.get("availability", ""))
                )

                if not availability:
                    continue

                if (
                    availability.endswith("/instock")
                    or availability == "instock"
                ):
                    return AvailabilityResult(
                        status=AvailabilityStatus.AVAILABLE,
                        available=True,
                        reason="JSON-LD reports that the listing is in stock.",
                        matched_text=availability,
                    )

                if (
                    availability.endswith("/soldout")
                    or availability == "soldout"
                ):
                    return AvailabilityResult(
                        status=AvailabilityStatus.SOLD_OUT,
                        available=False,
                        reason="JSON-LD reports that the listing is sold out.",
                        matched_text=availability,
                    )

                if (
                    availability.endswith("/outofstock")
                    or availability == "outofstock"
                ):
                    return AvailabilityResult(
                        status=AvailabilityStatus.UNAVAILABLE,
                        available=False,
                        reason="JSON-LD reports that the listing is out of stock.",
                        matched_text=availability,
                    )

                if (
                    availability.endswith("/discontinued")
                    or availability == "discontinued"
                ):
                    return AvailabilityResult(
                        status=AvailabilityStatus.UNAVAILABLE,
                        available=False,
                        reason="JSON-LD reports that the listing is discontinued.",
                        matched_text=availability,
                    )

    return None


def _collect_visible_status_labels(page: Page) -> list[str]:
    selectors = [
        '[data-et-name*="sold" i]',
        '[data-et-name*="availability" i]',
        '[data-test*="sold" i]',
        '[data-test*="availability" i]',
        '[class*="sold-out" i]',
        '[class*="sold_out" i]',
        '[class~="sold"]',
        '[class*="not-for-sale" i]',
        '[class*="not_for_sale" i]',
        '[class*="listing-status" i]',
        '[class*="listing_status" i]',
        '[class*="inventory-tag" i]',
        '[class*="inventory_tag" i]',
        '[class*="availability" i]',
        '[aria-label="Sold" i]',
        '[aria-label="Sold Out" i]',
        '[aria-label="Not For Sale" i]',
    ]

    labels: list[str] = []
    seen: set[str] = set()

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = min(locator.count(), 30)
        except Exception:
            continue

        for index in range(count):
            element = locator.nth(index)

            try:
                if not element.is_visible(timeout=250):
                    continue

                text = element.inner_text(timeout=500).strip()
            except Exception:
                continue

            normalized = normalize_text(text)

            if normalized and normalized not in seen:
                labels.append(text)
                seen.add(normalized)

    return labels

def _collect_exact_status_lines(page: Page) -> list[str]:
    """
    Search short visible page lines for exact status labels.

    This avoids scanning the entire page for loose keyword matches.
    """
    try:
        body_text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return []

    matches: list[str] = []

    for raw_line in body_text.splitlines():
        line = raw_line.strip()

        if not line or len(line) > 80:
            continue

        if status_from_text(line) != AvailabilityStatus.UNKNOWN:
            matches.append(line)

    return matches


def _has_active_purchase_control(page: Page) -> bool:
    selectors = [
        'button:has-text("Buy Now")',
        'button:has-text("Add to Bundle")',
        'button:has-text("Make an Offer")',
        'a:has-text("Buy Now")',
        '[data-et-name*="buy_now" i]',
        '[data-et-name*="add_to_bundle" i]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = min(locator.count(), 10)
        except Exception:
            continue

        for index in range(count):
            control = locator.nth(index)

            try:
                if not control.is_visible(timeout=250):
                    continue

                if not control.is_disabled(timeout=250):
                    return True
            except Exception:
                continue

    return False


def verify_listing_availability(page: Page) -> AvailabilityResult:
    """
    Verify listing availability after opening the listing page.

    Check order:
    1. Structured JSON-LD availability
    2. Visible status labels
    3. Exact short status lines
    4. Active purchase controls
    """
    json_result = _availability_from_json_ld(page)

    if json_result and not json_result.available:
        return json_result

    labels = _collect_visible_status_labels(page)

    for label in labels:
        status = status_from_text(label)

        if status != AvailabilityStatus.UNKNOWN:
            return AvailabilityResult(
                status=status,
                available=False,
                reason="Visible unavailable status found after opening listing.",
                matched_text=label,
            )

    exact_lines = _collect_exact_status_lines(page)

    for line in exact_lines:
        status = status_from_text(line)

        if status != AvailabilityStatus.UNKNOWN:
            return AvailabilityResult(
                status=status,
                available=False,
                reason="Exact unavailable status line found after opening listing.",
                matched_text=line,
            )

    if _has_active_purchase_control(page):
        return AvailabilityResult(
            status=AvailabilityStatus.AVAILABLE,
            available=True,
            reason="Listing has an active purchase control.",
        )

    if json_result and json_result.available:
        return json_result

    return AvailabilityResult(
        status=AvailabilityStatus.UNKNOWN,
        available=False,
        reason=(
            "No definitive available signal was found. "
            "The listing is skipped to avoid copying an unavailable item."
        ),
    )