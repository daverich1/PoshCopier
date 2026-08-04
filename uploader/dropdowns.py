import re

from playwright.sync_api import Locator, Page


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        value.casefold().split()
    )


def normalize_option_text(value: str | None) -> str:
    """
    Aggressively normalize dropdown text so that:

    Button Down Shirts
    Button-Down Shirts
    Button Down  Shirts

    all become:

    buttondownshirts

    Likewise:

    Loafers & Slip-Ons
    Loafers Slip Ons

    both become:

    loafersslipons
    """
    return re.sub(
        r"[^a-z0-9]+",
        "",
        normalize_text(value),
    )


def first_visible(
    locator: Locator,
) -> Locator | None:
    try:
        count = locator.count()
    except Exception:
        return None

    for index in range(count):
        candidate = locator.nth(index)

        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue

    return None


def click_locator(
    locator: Locator,
    timeout: int = 5000,
) -> None:
    locator.scroll_into_view_if_needed()

    try:
        locator.click(timeout=timeout)
        return
    except Exception:
        pass

    try:
        locator.click(
            timeout=timeout,
            force=True,
        )
        return
    except Exception:
        pass

    box = locator.bounding_box()

    if box is None:
        raise RuntimeError(
            "Could not determine the position "
            "of the element."
        )

    page = locator.page

    page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + box["height"] / 2,
    )


def find_visible_exact_text(
    page: Page,
    option_text: str,
) -> Locator | None:

    target = normalize_option_text(
        option_text
    )

    selectors = [
        ".dropdown__menu--expanded a",
        ".dropdown__menu--expanded li",
        "a.dropdown__link",
        '[role="option"]',
        '[role="button"]',
        "button",
        "label",
        "li",
        "span",
        "p",
    ]

    available = []

    for selector in selectors:
        candidates = page.locator(selector)

        for index in range(candidates.count()):
            candidate = candidates.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                raw_text = candidate.inner_text().strip()

                if not raw_text:
                    continue

                available.append(raw_text)

                if (
                    normalize_option_text(raw_text)
                    == target
                ):
                    return candidate

            except Exception:
                continue

    print("\nAvailable options:")
    for option in sorted(set(available)):
        print(" -", option)

    return None


def wait_for_visible_exact_text(
    page: Page,
    option_text: str,
    timeout_ms: int = 5000,
) -> Locator | None:

    elapsed = 0
    interval = 250

    while elapsed < timeout_ms:
        option = find_visible_exact_text(
            page,
            option_text,
        )

        if option is not None:
            return option

        page.wait_for_timeout(interval)
        elapsed += interval

    return None


def open_control(
    page: Page,
    control: Locator,
    expected_option: str | None = None,
) -> None:

    click_locator(control)

    if expected_option is None:
        page.wait_for_timeout(800)
        return

    option = wait_for_visible_exact_text(
        page,
        expected_option,
        timeout_ms=2500,
    )

    if option is not None:
        return

    try:
        control.focus()
        page.keyboard.press("Enter")
    except Exception:
        pass

    option = wait_for_visible_exact_text(
        page,
        expected_option,
        timeout_ms=2000,
    )

    if option is not None:
        return

    box = control.bounding_box()

    if box is not None:
        page.mouse.click(
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
        )

    option = wait_for_visible_exact_text(
        page,
        expected_option,
        timeout_ms=2500,
    )

    if option is None:
        raise RuntimeError(
            f"The control did not open an option named: {expected_option}"
        )


def select_visible_option(
    page: Page,
    option_text: str,
) -> None:

    option = wait_for_visible_exact_text(
        page,
        option_text,
        timeout_ms=5000,
    )

    if option is None:
        raise RuntimeError(
            f"Could not find visible option: {option_text}"
        )

    click_locator(option)

    page.wait_for_timeout(800)


def open_and_select(
    page: Page,
    control: Locator,
    option_text: str,
) -> None:

    open_control(
        page,
        control,
        expected_option=option_text,
    )

    select_visible_option(
        page,
        option_text,
    )