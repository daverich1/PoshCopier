import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

from playwright.sync_api import Page


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    normalized = unicodedata.normalize(
        "NFKC",
        value,
    )

    normalized = normalized.casefold()

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        normalized,
    )

    return " ".join(
        normalized.split()
    )


def compact_text(value: str | None) -> str:
    return normalize_text(
        value
    ).replace(" ", "")


def clean_price(value) -> str:
    if value is None:
        return ""

    match = re.search(
        r"\d+(?:,\d{3})*(?:\.\d{1,2})?",
        str(value),
    )

    if not match:
        return ""

    return match.group().replace(
        ",",
        "",
    )


def extract_listing_slug(
    listing_url: str,
) -> str:
    path = urlparse(
        listing_url
    ).path.rstrip("/")

    name = path.rsplit(
        "/",
        1,
    )[-1]

    parts = name.rsplit(
        "-",
        1,
    )

    if len(parts) == 2:
        return parts[0]

    return name


def title_similarity(
    first_title: str,
    second_title: str,
) -> float:
    first = compact_text(
        first_title
    )

    second = compact_text(
        second_title
    )

    if not first or not second:
        return 0.0

    if first == second:
        return 1.0

    return SequenceMatcher(
        None,
        first,
        second,
    ).ratio()


def collect_destination_listing_urls(
    page: Page,
    closet_url: str,
    maximum_scrolls: int = 35,
) -> list[str]:
    print(
        "\nScanning destination closet "
        "for existing listings..."
    )

    page.goto(
        closet_url,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        4000
    )

    previous_count = 0
    stable_rounds = 0

    for _ in range(maximum_scrolls):
        listing_urls = page.locator(
            'a[href*="/listing/"]'
        ).evaluate_all(
            """
            elements => [
                ...new Set(
                    elements
                        .map(element => element.href)
                        .filter(url =>
                            url
                            && url.includes("/listing/")
                        )
                )
            ]
            """
        )

        current_count = len(
            listing_urls
        )

        if current_count == previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 3:
            break

        previous_count = current_count

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
            1200
        )

    listing_urls = page.locator(
        'a[href*="/listing/"]'
    ).evaluate_all(
        """
        elements => [
            ...new Set(
                elements
                    .map(element => element.href)
                    .filter(url =>
                        url
                        && url.includes("/listing/")
                    )
            )
        ]
        """
    )

    print(
        "Destination listing URLs cached:",
        len(listing_urls),
    )

    return listing_urls


def extract_page_title(
    page: Page,
) -> str:
    selectors = [
        "h1",
        '[data-test="listing-title"]',
    ]

    for selector in selectors:
        locator = page.locator(
            selector
        ).first

        try:
            if locator.count() == 0:
                continue

            text = locator.inner_text().strip()

            if text:
                return text

        except Exception:
            continue

    return ""


def get_body_lines(
    page: Page,
) -> list[str]:
    try:
        body_text = page.locator(
            "body"
        ).inner_text()
    except Exception:
        return []

    return [
        line.strip()
        for line in body_text.splitlines()
        if line.strip()
    ]


def extract_page_price(
    lines: list[str],
    title: str,
) -> str:
    search_lines = lines

    if title and title in lines:
        title_index = lines.index(
            title
        )

        search_lines = lines[
            title_index + 1:
            title_index + 18
        ]

    for line in search_lines:
        match = re.search(
            r"\$(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
            line,
        )

        if match:
            return match.group(
                1
            ).replace(
                ",",
                "",
            )

    return ""


def extract_page_size(
    lines: list[str],
) -> str:
    for label in (
        "SIZE",
        "Size",
    ):
        if label not in lines:
            continue

        index = lines.index(
            label
        )

        if index + 1 < len(lines):
            next_line = lines[
                index + 1
            ]

            if next_line.lower() != "size chart":
                return next_line

    return ""


def extract_page_brand(
    lines: list[str],
    title: str,
) -> str:
    if not title or title not in lines:
        return ""

    title_index = lines.index(
        title
    )

    nearby_lines = lines[
        title_index + 1:
        title_index + 12
    ]

    ignored = {
        "Listing Metrics",
        "Last 60 days",
        "Edit Listing",
        "New With Tags",
        "New Without Tags",
        "New With Box",
        "New Without Box",
        "Like New",
        "Good",
        "Fair",
    }

    for line in nearby_lines:
        if line in ignored:
            continue

        if line.startswith(
            "Updated "
        ):
            continue

        if line.startswith(
            "Pay in 4"
        ):
            continue

        if "$" in line:
            continue

        return line

    return ""


def calculate_duplicate_score(
    source_listing: dict,
    destination_title: str,
    destination_brand: str,
    destination_size: str,
    destination_price: str,
) -> tuple[int, dict]:
    source_title = source_listing.get(
        "title",
        "",
    )

    source_brand = source_listing.get(
        "brand",
        "",
    )

    source_size = source_listing.get(
        "size",
        "",
    )

    source_price = clean_price(
        source_listing.get(
            "price"
        )
    )

    similarity = title_similarity(
        source_title,
        destination_title,
    )

    score = 0

    details = {
        "title_similarity": round(
            similarity,
            3,
        ),
        "title_match": False,
        "brand_match": False,
        "size_match": False,
        "price_match": False,
    }

    if compact_text(
        source_title
    ) == compact_text(
        destination_title
    ):
        score += 60
        details["title_match"] = True

    elif similarity >= 0.94:
        score += 50
        details["title_match"] = True

    elif similarity >= 0.88:
        score += 35

    if (
        source_brand
        and destination_brand
        and normalize_text(source_brand)
        == normalize_text(destination_brand)
    ):
        score += 15
        details["brand_match"] = True

    if (
        source_size
        and destination_size
        and normalize_text(source_size)
        == normalize_text(destination_size)
    ):
        score += 10
        details["size_match"] = True

    if (
        source_price
        and destination_price
        and source_price == destination_price
    ):
        score += 25
        details["price_match"] = True

    return score, details


def get_candidate_urls(
    listing: dict,
    destination_urls: list[str],
) -> list[tuple[float, str]]:
    source_title = listing.get(
        "title",
        "",
    )

    candidates = []

    for destination_url in destination_urls:
        slug = extract_listing_slug(
            destination_url
        )

        similarity = title_similarity(
            source_title,
            slug,
        )

        if similarity >= 0.75:
            candidates.append(
                (
                    similarity,
                    destination_url,
                )
            )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[:8]


def find_existing_duplicate(
    page: Page,
    listing: dict,
    destination_urls: list[str],
) -> str | None:
    candidates = get_candidate_urls(
        listing,
        destination_urls,
    )

    if not candidates:
        print(
            "Destination duplicate check: "
            "no similar titles found."
        )

        return None

    print(
        "Destination duplicate candidates:",
        len(candidates),
    )

    for slug_similarity, destination_url in candidates:
        try:
            page.goto(
                destination_url,
                wait_until="domcontentloaded",
            )

            page.wait_for_timeout(
                1600
            )

            destination_title = extract_page_title(
                page
            )

            lines = get_body_lines(
                page
            )

            destination_price = extract_page_price(
                lines,
                destination_title,
            )

            destination_size = extract_page_size(
                lines
            )

            destination_brand = extract_page_brand(
                lines,
                destination_title,
            )

            score, details = calculate_duplicate_score(
                listing,
                destination_title,
                destination_brand,
                destination_size,
                destination_price,
            )

            print(
                "Checked destination listing:",
                destination_title,
            )

            print(
                "Duplicate score:",
                score,
                details,
            )

            # Conservative threshold to reduce false matches.
            if score >= 80:
                print(
                    "\nExisting destination listing found:"
                )

                print(
                    destination_url
                )

                return destination_url

        except Exception as error:
            print(
                "Could not inspect duplicate candidate:",
                destination_url,
            )

            print(
                "Reason:",
                error,
            )

    print(
        "Destination duplicate check: "
        "no confirmed duplicate found."
    )

    return None


def add_destination_url(
    destination_urls: list[str],
    destination_url: str,
) -> None:
    if (
        destination_url
        and destination_url not in destination_urls
    ):
        destination_urls.insert(
            0,
            destination_url,
        )