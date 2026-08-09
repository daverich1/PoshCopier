from __future__ import annotations

import json
from typing import Any
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
from scraper.size_extractor import extract_sizes


JSONLD_CONDITION_MAP = {
    "https://schema.org/newcondition": "New With Tags",
    "https://schema.org/usedcondition": "Good",
    "https://schema.org/refurbishedcondition": "Good",
    "https://schema.org/damagedcondition": "Fair",
}


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


def _walk_jsonld(
    value: Any,
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []

    if isinstance(value, dict):
        objects.append(value)

        graph = value.get("@graph")

        if isinstance(graph, list):
            for item in graph:
                objects.extend(
                    _walk_jsonld(item)
                )

    elif isinstance(value, list):
        for item in value:
            objects.extend(
                _walk_jsonld(item)
            )

    return objects


def extract_jsonld_products(
    page: Page,
) -> list[dict[str, Any]]:
    try:
        scripts = page.locator(
            'script[type="application/ld+json"]'
        ).all_text_contents()
    except Exception:
        return []

    products: list[dict[str, Any]] = []

    for raw_script in scripts:
        try:
            payload = json.loads(
                raw_script
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            continue

        for item in _walk_jsonld(
            payload
        ):
            item_type = item.get(
                "@type"
            )

            if (
                item_type == "Product"
                or (
                    isinstance(
                        item_type,
                        list,
                    )
                    and "Product" in item_type
                )
            ):
                products.append(
                    item
                )

    return products


def normalize_schema_url(
    value: str | None,
) -> str:
    if not value:
        return ""

    return (
        str(value)
        .strip()
        .rstrip("/")
        .casefold()
    )


def extract_condition_from_jsonld(
    page: Page,
) -> str | None:
    products = extract_jsonld_products(
        page
    )

    for product in products:
        offers = product.get(
            "offers"
        )

        offer_items: list[
            dict[str, Any]
        ] = []

        if isinstance(
            offers,
            dict,
        ):
            offer_items.append(
                offers
            )

        elif isinstance(
            offers,
            list,
        ):
            offer_items.extend(
                item
                for item in offers
                if isinstance(
                    item,
                    dict,
                )
            )

        for offer in offer_items:
            raw_condition = offer.get(
                "itemCondition"
            )

            if isinstance(
                raw_condition,
                dict,
            ):
                raw_condition = (
                    raw_condition.get("@id")
                    or raw_condition.get("url")
                    or raw_condition.get("name")
                )

            normalized = normalize_schema_url(
                str(raw_condition)
                if raw_condition
                else ""
            )

            mapped = JSONLD_CONDITION_MAP.get(
                normalized
            )

            if mapped:
                return mapped

        direct_condition = product.get(
            "itemCondition"
        )

        normalized_direct = (
            normalize_schema_url(
                str(direct_condition)
                if direct_condition
                else ""
            )
        )

        mapped_direct = (
            JSONLD_CONDITION_MAP.get(
                normalized_direct
            )
        )

        if mapped_direct:
            return mapped_direct

    return None

def extract_description_from_jsonld(
    page: Page,
) -> str | None:
    products = extract_jsonld_products(
        page
    )

    for product in products:
        description = product.get(
            "description"
        )

        if isinstance(
            description,
            str,
        ):
            description = (
                description.strip()
            )

            if description:
                return description

    return None
def extract_category_from_breadcrumb(page: Page) -> str | None:
    """
    Extract category from breadcrumb navigation.
    
    Converts breadcrumb like "Women > Shoes > Espadrilles"
    to "WomenShoesEspadrilles"
    
    Preserves spaces within category names:
    "Women > Shoes > Ankle Boots & Booties"
    to "WomenShoesAnkle Boots & Booties"
    
    Returns:
        Category string with separators removed, or None if not found
    """
    try:
        # Semantic selectors for breadcrumb navigation
        breadcrumb_selectors = [
            'nav[aria-label*="breadcrumb" i]',
            '[aria-label*="breadcrumb" i]',
            '[data-test="breadcrumb"]',
        ]
        
        for selector in breadcrumb_selectors:
            try:
                breadcrumb = page.locator(selector).first
                if breadcrumb.count() > 0:
                    text = breadcrumb.inner_text()
                    
                    # Normalize separators: >, /, ›, •
                    normalized = text.replace('>', '|').replace('/', '|').replace('›', '|').replace('•', '|')
                    parts = [part.strip() for part in normalized.split('|') if part.strip()]
                    
                    # Only accept if at least 2 meaningful parts
                    if len(parts) >= 2:
                        # Join without separators, preserving spaces within names
                        return ''.join(parts)
                        
            except Exception:
                continue
        
        return None
        
    except Exception:
        return None


def scrape_listing(
    page: Page,
    listing_url: str,
    *,
    download_images: bool = True,
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

    condition = extract_condition(
        lines
    )

    if condition is None:
        condition = extract_condition_from_jsonld(
            page
        )

        if condition:
            print(
                "Condition recovered from JSON-LD:",
                condition,
            )

    sizes = extract_sizes(
        page
    )

    fallback_size = extract_size(
        lines
    )

    primary_size = (
        sizes[0]
        if sizes
        else fallback_size
    )

    print(
        "Sizes detected:",
        sizes,
    )
    description = extract_description(
        lines
    )

    if description is None:
        description = (
            extract_description_from_jsonld(
                page
            )
        )

        if description:
            print(
                "Description recovered from JSON-LD."
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
        "size": primary_size,
        "sizes": sizes,
        "is_multi_size": (
            len(sizes) > 1
        ),
        "condition": condition,
        "category": (
            extract_category_from_breadcrumb(page)
            or extract_category(lines)
        ),
        "colors": extract_colors(
            lines
        ),
        "description": description,
        "image_urls": image_urls,
        "local_images": [],
        "available": availability.available,
        "availability_reason": availability.reason,
        "availability_signal": (
            availability.matched_text
        ),
    }

    if not availability.available or not download_images:
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
