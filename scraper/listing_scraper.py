from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page

from scraper.parser import (
    clean_lines,
    extract_brand,
    extract_category,
    extract_colors,
    extract_condition,
    extract_description,
    extract_price,
    extract_size,
)


UNAVAILABLE_CARD_STATUSES = {
    "sold",
    "sold out",
    "not for sale",
}


UNAVAILABLE_PAGE_SIGNALS = (
    "this item is sold",
    "this item has been sold",
    "this item is no longer available",
    "this listing is no longer available",
    "item is no longer available",
    "item is not available",
    "not for sale",
    "sold out",
)


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    return " ".join(
        value.casefold().split()
    )


def clean_listing_url(
    url: str,
) -> str:
    parts = urlsplit(url)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path.rstrip("/"),
            "",
            "",
        )
    )


def extract_listing_id(
    listing_url: str,
) -> str:
    clean_url = clean_listing_url(
        listing_url
    )

    return clean_url.rsplit(
        "-",
        1,
    )[-1]


def collect_visible_listing_cards(
    page: Page,
) -> list[dict]:
    """
    Collects listing URLs from the closet grid.

    Cards marked SOLD, SOLD OUT, or NOT FOR SALE are
    excluded before their URLs enter the scraping queue.
    """

    cards = page.evaluate(
        """
        () => {
            const normalize = value =>
                (value || "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .toLowerCase();

            const unavailableStatuses = new Set([
                "sold",
                "sold out",
                "not for sale"
            ]);

            const results = [];
            const seenUrls = new Set();

            const listingLinks = [
                ...document.querySelectorAll(
                    'a[href*="/listing/"]'
                )
            ];

            for (const link of listingLinks) {
                const href = link.href;

                if (
                    !href
                    || !href.includes("/listing/")
                    || seenUrls.has(href)
                ) {
                    continue;
                }

                /*
                Walk upward until we find the listing-card
                wrapper containing the status overlay and the
                rest of the card information.
                */
                let card = link;

                for (let depth = 0; depth < 8; depth += 1) {
                    if (!card || !card.parentElement) {
                        break;
                    }

                    const parent = card.parentElement;

                    const hasStatusOverlay =
                        parent.querySelector(
                            ".tile-grid-redesign__listing-status-overlay"
                        );

                    const hasListingImage =
                        parent.querySelector(
                            'img[src*="/posts/"], ' +
                            'img[srcset*="/posts/"]'
                        );

                    if (
                        hasStatusOverlay
                        || hasListingImage
                    ) {
                        card = parent;
                    } else {
                        break;
                    }
                }

                const statusElement =
                    card.querySelector(
                        ".tile-grid-redesign__listing-status-overlay"
                    );

                const statusText = normalize(
                    statusElement
                        ? statusElement.innerText
                        : ""
                );

                const cardText = normalize(
                    card.innerText
                );

                let unavailableStatus = "";

                for (const status of unavailableStatuses) {
                    if (
                        statusText === status
                        || statusText.includes(status)
                        || cardText.startsWith(status + " ")
                        || cardText.includes(" " + status + " ")
                    ) {
                        unavailableStatus = status;
                        break;
                    }
                }

                seenUrls.add(href);

                results.push({
                    url: href,
                    status: statusText,
                    unavailable: Boolean(
                        unavailableStatus
                    ),
                    unavailable_reason:
                        unavailableStatus || null
                });
            }

            return results;
        }
        """
    )

    cleaned_cards = []
    seen_urls = set()

    for card in cards:
        url = clean_listing_url(
            card.get("url", "")
        )

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        cleaned_cards.append(
            {
                "url": url,
                "status": card.get(
                    "status",
                    "",
                ),
                "unavailable": bool(
                    card.get(
                        "unavailable",
                        False,
                    )
                ),
                "unavailable_reason": (
                    card.get(
                        "unavailable_reason"
                    )
                ),
            }
        )

    return cleaned_cards


def get_listing_links(
    page: Page,
    closet_url: str,
    maximum_scrolls: int = 250,
    stable_rounds_required: int = 6,
) -> tuple[list[str], list[dict]]:
    """
    Scrolls through the entire closet.

    Returns:
        available_listing_urls
        unavailable_card_records
    """

    page.goto(
        closet_url,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        5000
    )

    available_urls = set()
    unavailable_by_url = {}

    stable_rounds = 0

    print(
        "\nDiscovering available closet listings..."
    )

    for scroll_number in range(
        1,
        maximum_scrolls + 1,
    ):
        cards = collect_visible_listing_cards(
            page
        )

        previous_available_count = len(
            available_urls
        )

        previous_unavailable_count = len(
            unavailable_by_url
        )

        for card in cards:
            url = card["url"]

            if card["unavailable"]:
                unavailable_by_url[url] = card
                available_urls.discard(url)
            elif url not in unavailable_by_url:
                available_urls.add(url)

        available_count = len(
            available_urls
        )

        unavailable_count = len(
            unavailable_by_url
        )

        new_available = (
            available_count
            - previous_available_count
        )

        new_unavailable = (
            unavailable_count
            - previous_unavailable_count
        )

        print(
            f"Scroll {scroll_number}: "
            f"{available_count} available "
            f"(+{new_available}), "
            f"{unavailable_count} unavailable "
            f"(+{new_unavailable})"
        )

        if (
            new_available == 0
            and new_unavailable == 0
        ):
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= stable_rounds_required:
            print(
                "No new closet cards appeared after "
                f"{stable_rounds_required} scrolls."
            )
            break

        page.evaluate(
            """
            () => {
                window.scrollTo(
                    0,
                    document.body.scrollHeight
                );
            }
            """
        )

        page.wait_for_timeout(
            1800
        )

    listing_links = sorted(
        available_urls
    )

    unavailable_records = sorted(
        unavailable_by_url.values(),
        key=lambda item: item["url"],
    )

    print(
        "\nCloset discovery complete."
    )

    print(
        "Available listing URLs found:",
        len(listing_links),
    )

    print(
        "Unavailable cards skipped:",
        len(unavailable_records),
    )

    return (
        listing_links,
        unavailable_records,
    )


def get_text(
    page: Page,
    selectors: list[str],
) -> str | None:
    for selector in selectors:
        try:
            locator = page.locator(
                selector
            ).first

            if locator.count() == 0:
                continue

            text = locator.inner_text().strip()

            if text:
                return text

        except Exception:
            continue

    return None


def extract_image_urls(
    page: Page,
) -> list[str]:
    return page.locator(
        "img"
    ).evaluate_all(
        r"""
        images => {
            const urls = [];

            for (const image of images) {
                if (image.src) {
                    urls.push(image.src);
                }

                if (image.srcset) {
                    const candidates = image.srcset
                        .split(",")
                        .map(item =>
                            item.trim().split(" ")[0]
                        )
                        .filter(Boolean);

                    urls.push(...candidates);
                }
            }

            const postUrls = [...new Set(urls)]
                .filter(url =>
                    url.startsWith("http")
                    && url.includes("/posts/")
                );

            const normalized = new Map();

            for (const url of postUrls) {
                const key = url.replace(
                    /\/[stl]_/,
                    "/"
                );

                const current =
                    normalized.get(key);

                if (
                    !current
                    || url.includes("/l_")
                ) {
                    normalized.set(
                        key,
                        url
                    );
                }
            }

            return [
                ...normalized.values()
            ];
        }
        """
    )


def page_has_visible_text(
    page: Page,
    expected_text: str,
) -> bool:
    matches = page.get_by_text(
        expected_text,
        exact=False,
    )

    try:
        for index in range(
            matches.count()
        ):
            if matches.nth(
                index
            ).is_visible():
                return True

    except Exception:
        pass

    return False


def get_page_availability(
    page: Page,
    lines: list[str],
) -> tuple[bool, str]:
    """
    Second protection layer after the card-level filter.
    """

    normalized_body = normalize_text(
        "\n".join(lines)
    )

    for signal in UNAVAILABLE_PAGE_SIGNALS:
        if signal in normalized_body:
            return (
                False,
                signal.replace(
                    " ",
                    "_",
                ),
            )

    for label in (
        "SOLD",
        "SOLD OUT",
        "NOT FOR SALE",
    ):
        if page_has_visible_text(
            page,
            label,
        ):
            return (
                False,
                label.casefold().replace(
                    " ",
                    "_",
                ),
            )

    status_selectors = (
        ".tile-grid-redesign__listing-status-overlay",
        '[class*="listing-status" i]',
        '[class*="sold" i]',
        '[data-test*="sold" i]',
        'img[alt*="sold" i]',
    )

    for selector in status_selectors:
        candidates = page.locator(
            selector
        )

        try:
            for index in range(
                candidates.count()
            ):
                candidate = candidates.nth(
                    index
                )

                if not candidate.is_visible():
                    continue

                status_text = normalize_text(
                    candidate.inner_text()
                )

                if (
                    "sold" in status_text
                    or "not for sale" in status_text
                ):
                    return (
                        False,
                        status_text.replace(
                            " ",
                            "_",
                        ),
                    )

        except Exception:
            continue

    return (
        True,
        "available",
    )


def scrape_listing(
    page: Page,
    listing_url: str,
) -> dict:
    page.goto(
        listing_url,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        3500
    )

    title = get_text(
        page,
        [
            "h1",
            '[data-test="listing-title"]',
        ],
    )

    body_text = page.locator(
        "body"
    ).inner_text()

    lines = clean_lines(
        body_text
    )

    (
        available,
        availability_reason,
    ) = get_page_availability(
        page,
        lines,
    )

    image_urls = []

    if available:
        image_urls = extract_image_urls(
            page
        )

    return {
        "url": clean_listing_url(
            listing_url
        ),
        "listing_id": extract_listing_id(
            listing_url
        ),
        "title": title,
        "price": extract_price(
            lines,
            title,
        ),
        "brand": extract_brand(
            lines,
            title,
        ),
        "size": extract_size(
            lines
        ),
        "condition": extract_condition(
            lines
        ),
        "category": extract_category(
            lines
        ),
        "colors": extract_colors(
            lines
        ),
        "description": extract_description(
            lines
        ),
        "image_urls": image_urls,
        "available": available,
        "availability_reason": (
            availability_reason
        ),
    }