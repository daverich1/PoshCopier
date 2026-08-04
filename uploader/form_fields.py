import re

from playwright.sync_api import Locator, Page


def try_fill(
    locator: Locator,
    value: str,
) -> bool:
    try:
        if locator.count() == 0:
            return False

        field = locator.first

        field.wait_for(
            state="visible",
            timeout=5000,
        )

        field.scroll_into_view_if_needed()
        field.fill(value)

        return True

    except Exception:
        return False


def fill_title(
    page: Page,
    title: str,
) -> None:
    if not title:
        raise RuntimeError(
            "The listing title is missing."
        )

    selectors = [
        'input[placeholder*="selling" i]',
        'input[name="title"]',
        'textarea[name="title"]',
        'input[id*="title" i]',
        'textarea[id*="title" i]',
        'input[placeholder*="title" i]',
        'textarea[placeholder*="title" i]',
        'input[aria-label*="title" i]',
        'textarea[aria-label*="title" i]',
    ]

    for selector in selectors:
        if try_fill(
            page.locator(selector),
            title,
        ):
            print("Title entered.")
            return

    raise RuntimeError(
        "Could not find the title field."
    )


def fill_description(
    page: Page,
    description: str,
) -> None:
    if not description:
        raise RuntimeError(
            "The listing description is missing."
        )

    selectors = [
        'textarea[name="description"]',
        'textarea[id*="description" i]',
        'textarea[placeholder*="description" i]',
        'textarea[aria-label*="description" i]',
        'textarea[placeholder*="describe" i]',
    ]

    for selector in selectors:
        if try_fill(
            page.locator(selector),
            description,
        ):
            print("Description entered.")
            return

    try:
        locator = page.get_by_label(
            "Description",
            exact=False,
        )

        if try_fill(locator, description):
            print("Description entered.")
            return

    except Exception:
        pass

    description_labels = page.get_by_text(
        "Description",
        exact=True,
    )

    try:
        for index in range(
            description_labels.count()
        ):
            label = description_labels.nth(index)

            nearby_textarea = label.locator(
                "xpath=following::textarea[1]"
            )

            if try_fill(
                nearby_textarea,
                description,
            ):
                print("Description entered.")
                return

    except Exception:
        pass

    raise RuntimeError(
        "Could not find the description field."
    )


def clean_price(price) -> str:
    if price is None:
        return ""

    match = re.search(
        r"\d+(?:,\d{3})*(?:\.\d{1,2})?",
        str(price),
    )

    if not match:
        return ""

    return match.group().replace(",", "")


def fill_price(
    page: Page,
    price,
) -> None:
    price_value = clean_price(price)

    if not price_value:
        raise RuntimeError(
            "The listing price is missing or invalid."
        )

    page.wait_for_timeout(2000)

    selectors = [
        'input[name="price"]',
        'input[name*="listingPrice" i]',
        'input[id*="listing-price" i]',
        'input[id*="listingPrice" i]',
        'input[placeholder*="listing price" i]',
        'input[aria-label*="listing price" i]',
        'input[data-vv-name*="price" i]',
    ]

    for selector in selectors:
        if try_fill(
            page.locator(selector),
            price_value,
        ):
            print("Price entered.")
            return

    listing_price_labels = page.get_by_text(
        "Listing Price",
        exact=True,
    )

    try:
        for index in range(
            listing_price_labels.count()
        ):
            label = listing_price_labels.nth(index)

            nearby_input = label.locator(
                "xpath=following::input[1]"
            )

            if try_fill(
                nearby_input,
                price_value,
            ):
                print("Price entered.")
                return

    except Exception:
        pass

    raise RuntimeError(
        "Could not find the listing price field."
    )


def close_price_modal(
    page: Page,
) -> None:
    page.wait_for_timeout(1000)

    modal_selectors = [
        '[data-test="modal"]',
        '.modal-backdrop--in',
        '.modal-backdrop',
    ]

    modal_visible = False

    for selector in modal_selectors:
        try:
            modal = page.locator(selector).first

            if (
                modal.count() > 0
                and modal.is_visible()
            ):
                modal_visible = True
                break

        except Exception:
            continue

    if not modal_visible:
        return

    button_selectors = [
        '[data-test="modal"] button:has-text("Apply")',
        '[data-test="modal"] button:has-text("Done")',
        '[data-test="modal"] button:has-text("Continue")',
        '[data-test="modal"] button:has-text("Got it")',
        '[data-test="modal"] button:has-text("Close")',
        '[data-test="modal"] button[aria-label*="close" i]',
        '.modal button:has-text("Apply")',
        '.modal button:has-text("Done")',
        '.modal button:has-text("Close")',
        '.modal button[aria-label*="close" i]',
    ]

    for selector in button_selectors:
        button = page.locator(selector).first

        try:
            if button.count() == 0:
                continue

            button.wait_for(
                state="visible",
                timeout=2000,
            )

            button.click()
            page.wait_for_timeout(1000)

            print("Price modal closed.")
            return

        except Exception:
            continue

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)

        print("Attempted to close price modal with Escape.")

    except Exception:
        pass


def find_brand_field(
    page: Page,
):
    selectors = [
        'input[name="brand"]',
        'input[id*="brand" i]',
        'input[placeholder*="brand" i]',
        'input[aria-label*="brand" i]',
    ]

    for selector in selectors:
        locator = page.locator(selector).first

        try:
            if locator.count() == 0:
                continue

            locator.wait_for(
                state="visible",
                timeout=4000,
            )

            return locator

        except Exception:
            continue

    try:
        locator = page.get_by_label(
            "Brand",
            exact=False,
        ).first

        if locator.count() > 0:
            return locator

    except Exception:
        pass

    brand_labels = page.get_by_text(
        "Brand",
        exact=True,
    )

    try:
        for index in range(
            brand_labels.count()
        ):
            label = brand_labels.nth(index)

            nearby_input = label.locator(
                "xpath=following::input[1]"
            )

            if nearby_input.count() > 0:
                return nearby_input.first

    except Exception:
        pass

    return None


def fill_brand(
    page: Page,
    brand: str,
) -> None:
    if not brand:
        raise RuntimeError(
            "The listing brand is missing."
        )

    brand_field = find_brand_field(page)

    if brand_field is None:
        raise RuntimeError(
            "Could not find the brand field."
        )

    brand_field.scroll_into_view_if_needed()

    try:
        brand_field.click(
            timeout=5000,
        )

    except Exception:
        close_price_modal(page)

        brand_field.click(
            timeout=5000,
            force=True,
        )

    brand_field.fill(brand)

    print(f"Brand typed: {brand}")

    page.wait_for_timeout(2500)

    option_selectors = [
        f'[role="option"]:has-text("{brand}")',
        f'li:has-text("{brand}")',
        f'div[role="option"]:has-text("{brand}")',
    ]

    for selector in option_selectors:
        option = page.locator(selector).first

        try:
            if option.count() == 0:
                continue

            option.wait_for(
                state="visible",
                timeout=3000,
            )

            option.click()

            print("Brand selected.")
            return

        except Exception:
            continue

    try:
        exact_option = page.get_by_text(
            brand,
            exact=True,
        ).last

        exact_option.wait_for(
            state="visible",
            timeout=3000,
        )

        exact_option.click()

        print("Brand selected.")
        return

    except Exception:
        pass

    print(
        "No exact brand suggestion was found. "
        "Brand text remains entered."
    )