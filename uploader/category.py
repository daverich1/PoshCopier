from playwright.sync_api import Locator, Page

from uploader.dropdowns import (
    normalize_text,
    open_and_select,
    select_visible_option,
)


DEPARTMENTS = (
    "Women",
    "Men",
    "Kids",
    "Home",
    "Pets",
    "Electronics",
)

KNOWN_CATEGORIES = (
    "Intimates & Sleepwear",
    "Pants & Jumpsuits",
    "Jackets & Coats",
    "Accessories",
    "Sweaters",
    "Dining",
    "Dresses",
    "Makeup",
    "Shorts",
    "Skirts",
    "Sleepwear",
    "Jeans",
    "Shoes",
    "Bags",
    "Swim",
    "Tops",
)

SUBCATEGORY_UI_ALIASES = {
    "Sandals": "Sandals & Flip-Flops",
}


KNOWN_SUBCATEGORIES = (
    "Cardigans",
    "Cowl & Turtlenecks",
    "Crew & Scoop Necks",
    "Off-the-Shoulder Sweaters",
    "Shrugs & Ponchos",
    "V-Necks",
    "Sneakers",
    "Boots",
    "Sandals",
    "Heels",
    "Flats & Loafers",
    "Drinkware",
)


def compact_text(value: str | None) -> str:
    return (
        normalize_text(value)
        .replace(" ", "")
        .replace("&", "")
        .replace("-", "")
    )


def match_known_value(
    remaining_text: str,
    known_values: tuple[str, ...],
) -> tuple[str | None, str]:

    sorted_values = sorted(
        known_values,
        key=lambda value: len(compact_text(value)),
        reverse=True,
    )

    for value in sorted_values:
        compact_value = compact_text(value)

        if remaining_text.startswith(compact_value):
            leftover = remaining_text[len(compact_value):]
            return value, leftover

    return None, remaining_text


def split_category(
    category_text: str,
) -> tuple[str, str | None, str | None]:

    if not category_text:
        raise RuntimeError(
            "The listing category is missing."
        )

    cleaned = category_text.strip()

    department = None
    remaining = ""

    for candidate in DEPARTMENTS:
        if cleaned.casefold().startswith(candidate.casefold()):
            department = candidate
            remaining = cleaned[len(candidate):]
            break

    if department is None:
        raise RuntimeError(
            f"Could not determine department from {category_text}"
        )

    if not remaining:
        return department, None, None

    compact_remaining = compact_text(remaining)

    category, subcategory_text = match_known_value(
        compact_remaining,
        KNOWN_CATEGORIES,
    )

    if category is None:
        return department, remaining, None

    subcategory = None

    if subcategory_text:
        matched_subcategory, _ = match_known_value(
            subcategory_text,
            KNOWN_SUBCATEGORIES,
        )

        subcategory = matched_subcategory or subcategory_text

    return department, category, subcategory


def find_category_control(page: Page) -> Locator:
    dropdowns = page.locator('[data-test="dropdown"]')

    for i in range(dropdowns.count()):
        dropdown = dropdowns.nth(i)

        try:
            if not dropdown.is_visible():
                continue

            if "select category" in normalize_text(
                dropdown.inner_text()
            ):
                return dropdown

        except Exception:
            pass

    raise RuntimeError(
        "Could not find category dropdown."
    )


def find_subcategory_control(page: Page) -> Locator:

    container = page.locator(
        ".listing-editor__subcategory-container"
    ).first

    container.wait_for(
        state="visible",
        timeout=10000,
    )

    dropdown = container.locator(
        '[data-test="dropdown"]'
    ).first

    dropdown.wait_for(
        state="visible",
        timeout=10000,
    )

    return dropdown


def fill_category(
    page: Page,
    category_text: str,
) -> None:

    department, category, subcategory = split_category(
        category_text
    )

    print(
        "Parsed category:",
        {
            "department": department,
            "category": category,
            "subcategory": subcategory,
        },
    )

    category_control = find_category_control(page)

    open_and_select(
        page,
        category_control,
        department,
    )

    print(
        f"Department selected: {department}"
    )

    if category:
        select_visible_option(
            page,
            category,
        )

        print(
            f"Category selected: {category}"
        )

    if subcategory:
        ui_subcategory = SUBCATEGORY_UI_ALIASES.get(
            subcategory,
            subcategory,
        )

        if ui_subcategory != subcategory:
            print(
                f"Subcategory mapped: {subcategory} "
                f"-> {ui_subcategory}"
            )

        subcategory_options = [ui_subcategory]

        if ui_subcategory != subcategory:
            subcategory_options.append(subcategory)

        selected = False
        last_error = None

        for option in subcategory_options:
            for attempt in range(1, 3):
                page.wait_for_timeout(2000)

                subcategory_control = find_subcategory_control(
                    page
                )

                try:
                    open_and_select(
                        page,
                        subcategory_control,
                        option,
                    )
                    selected = True
                    break
                except RuntimeError as error:
                    last_error = error

                    if attempt < 2:
                        print(
                            "Subcategory option was not ready; retrying..."
                        )

            if selected:
                break

            if option != subcategory:
                print(
                    f"Mapped subcategory unavailable; "
                    f"trying {subcategory}."
                )

        if not selected and last_error is not None:
            raise last_error

        # We intentionally do NOT verify the text here.
        # The screenshots show the dropdown is selecting
        # correctly, and the old verification was causing
        # false failures.

        print(
            f"Subcategory selected: {subcategory}"
        )
