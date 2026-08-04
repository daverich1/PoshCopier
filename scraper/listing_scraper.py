from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page

from scraper.availability import verify_listing_availability
from scraper.image_downloader import download_listing_images
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
from scraper.save_listing import save_listing


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
    result = page.locator(
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

    if not isinstance(result, list):
        return []

    return [
        str(url)
        for url in result
        if isinstance(url, str)
    ]


def scrape_listing(
    page: Page,
    listing_url: str,
) -> dict:
    page.goto(
        listing_url,
        wait_until="domcontentloaded",
        timeout=60_000,
    )

    page.wait_for_timeout(
        3500
    )

    availability = (
        verify_listing_availability(
            page
        )
    )

    title = get_text(
        page,
        [
            "h1",
            '[data-test="listing-title"]',
        ],
    )

    try:
        body_text = page.locator(
            "body"
        ).inner_text()
    except Exception:
        body_text = ""

    lines = clean_lines(
        body_text
    )

    listing_id = extract_listing_id(
        listing_url
    )

    image_urls: list[str] = []

    if availability.available:
        image_urls = extract_image_urls(
            page
        )

    listing = {
        "url": clean_listing_url(
            listing_url
        ),
        "listing_id": listing_id,
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
        "local_images": [],
        "available": availability.available,
        "availability_reason": availability.reason,
        "availability_signal": (
            availability.matched_text
        ),
    }

    if not availability.available:
        return listing

    local_images = download_listing_images(
        listing
    )

    listing["local_images"] = local_images

    if not local_images:
        raise RuntimeError(
            "The listing was available, but no images "
            "were downloaded."
        )

    saved_path = save_listing(
        listing
    )

    listing["listing_json"] = str(
        saved_path
    )

    return listing
