from playwright.sync_api import Locator, Page


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def find_visible_locator(
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


def open_color_picker(
    page: Page,
) -> None:
    selectors = [
        'span:text-is("Select up to 2 colors")',
        '[data-test="dropdown"]:has-text("Select up to 2 colors")',
        'div[tabindex="0"]:has-text("Select up to 2 colors")',
    ]

    for selector in selectors:
        candidate = find_visible_locator(
            page.locator(selector)
        )

        if candidate is None:
            continue

        candidate.scroll_into_view_if_needed()
        candidate.click()

        page.wait_for_timeout(1000)

        print("Color picker opened.")
        return

    exact_text = find_visible_locator(
        page.get_by_text(
            "Select up to 2 colors",
            exact=True,
        )
    )

    if exact_text is not None:
        exact_text.click()
        page.wait_for_timeout(1000)

        print("Color picker opened.")
        return

    raise RuntimeError(
        "Could not open the color picker."
    )


def find_color_option(
    page: Page,
    color: str,
) -> Locator | None:
    target = normalize_text(color)

    candidates = page.locator(
        "button, label, span, p, div"
    )

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        try:
            if not candidate.is_visible():
                continue

            text = normalize_text(
                candidate.inner_text()
            )

            if text == target:
                return candidate

        except Exception:
            continue

    return None


def click_done(
    page: Page,
) -> None:
    done_button = find_visible_locator(
        page.get_by_text(
            "Done",
            exact=True,
        )
    )

    if done_button is not None:
        try:
            done_button.click(
                timeout=5000,
            )
        except Exception:
            done_button.click(
                timeout=5000,
                force=True,
            )

        page.wait_for_timeout(1000)
        return

    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)


def verify_colors(
    page: Page,
    colors: list[str],
) -> bool:
    targets = {
        normalize_text(color)
        for color in colors
    }

    candidates = page.locator(
        '[data-test="dropdown"], '
        'div[tabindex="0"], '
        '[role="button"]'
    )

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        try:
            if not candidate.is_visible():
                continue

            text = normalize_text(
                candidate.inner_text()
            )

            if all(
                target in text
                for target in targets
            ):
                return True

        except Exception:
            continue

    return False


def fill_colors(
    page: Page,
    colors: list[str],
) -> None:
    if not colors:
        print(
            "No colors were saved. "
            "Skipping color selection."
        )
        return

    open_color_picker(page)

    for color in colors[:2]:
        option = find_color_option(
            page,
            color,
        )

        if option is None:
            raise RuntimeError(
                f"Could not find color option: {color}"
            )

        try:
            option.click(
                timeout=5000,
            )
        except Exception:
            option.click(
                timeout=5000,
                force=True,
            )

        print(f"Color selected: {color}")

        page.wait_for_timeout(500)

    click_done(page)

    if not verify_colors(
        page,
        colors[:2],
    ):
        raise RuntimeError(
            "The colors were selected, but the "
            "final color field could not be verified."
        )

    print("Color selection confirmed.")