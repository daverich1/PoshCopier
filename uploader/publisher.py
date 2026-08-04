import re
import unicodedata

from playwright.sync_api import Locator, Page


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip().lower()


def find_visible(
    locator: Locator,
) -> Locator | None:
    for index in range(locator.count()):
        candidate = locator.nth(index)

        try:
            if candidate.is_visible():
                return candidate

        except Exception:
            continue

    return None


def click_next(page: Page) -> None:
    selectors = [
        'button:text-is("Next")',
        'button:has-text("Next")',
        '[role="button"]:text-is("Next")',
    ]

    for selector in selectors:
        button = find_visible(
            page.locator(selector)
        )

        if button is None:
            continue

        button.scroll_into_view_if_needed()
        button.click()

        page.wait_for_timeout(2500)

        print("Next clicked.")
        return

    raise RuntimeError(
        "Could not find the Next button."
    )


def find_publish_button(
    page: Page,
) -> Locator | None:
    button_names = [
        "List Item",
        "List This Item",
        "Publish",
        "List",
    ]

    for name in button_names:
        button = find_visible(
            page.get_by_role(
                "button",
                name=name,
                exact=True,
            )
        )

        if button is not None:
            return button

    selectors = [
        'button:has-text("List Item")',
        'button:has-text("List This Item")',
        'button:has-text("Publish")',
    ]

    for selector in selectors:
        button = find_visible(
            page.locator(selector)
        )

        if button is not None:
            return button

    return None


def collect_listing_links(
    page: Page,
) -> list[str]:
    page.wait_for_timeout(4000)

    links = page.locator(
        'a[href*="/listing/"]'
    ).evaluate_all(
        """
        elements => [
            ...new Set(
                elements
                    .map(element => element.href)
                    .filter(Boolean)
            )
        ]
        """
    )

    return links


def find_published_listing(
    page: Page,
    expected_title: str,
) -> str | None:
    expected = normalize_text(expected_title)

    listing_links = collect_listing_links(page)

    print(
        f"Checking {len(listing_links)} closet "
        f"listing links for the new listing."
    )

    # The newest listings should appear first,
    # so only inspect the first several.
    for listing_url in listing_links[:15]:
        try:
            page.goto(
                listing_url,
                wait_until="domcontentloaded",
            )

            page.wait_for_timeout(1800)

            title_locator = page.locator("h1").first

            if title_locator.count() == 0:
                continue

            actual_title = title_locator.inner_text().strip()
            actual = normalize_text(actual_title)

            if (
                actual == expected
                or expected in actual
                or actual in expected
            ):
                print(
                    "Published listing verified:"
                )
                print(page.url)

                return page.url

        except Exception:
            continue

    return None


def publish_listing(
    page: Page,
    listing_title: str,
) -> str:
    click_next(page)

    publish_button = find_publish_button(page)

    if publish_button is None:
        raise RuntimeError(
            "Could not find the final publish button."
        )

    print("\nThe listing is ready for publishing.")
    print("Review every field in the browser.")

    confirmation = input(
        "Type PUBLISH to click the final button: "
    ).strip()

    if confirmation != "PUBLISH":
        raise RuntimeError(
            "Publishing was cancelled."
        )

    publish_button.scroll_into_view_if_needed()
    publish_button.click()

    print("Final publish button clicked.")

    page.wait_for_timeout(8000)

    current_url = page.url

    # Some publishes go directly to the new listing.
    if "/listing/" in current_url:
        print("Listing published successfully.")
        print("Destination URL:", current_url)

        return current_url

    # Poshmark may redirect back to the destination closet.
    if "/closet/" in current_url:
        print(
            "Redirected to the closet. "
            "Searching for the published listing."
        )

        destination_url = find_published_listing(
            page,
            listing_title,
        )

        if destination_url:
            print("Listing published successfully.")
            print(
                "Destination URL:",
                destination_url,
            )

            return destination_url

    raise RuntimeError(
        "The final button was clicked, but the "
        "published listing could not be verified. "
        f"Current URL: {current_url}"
    )