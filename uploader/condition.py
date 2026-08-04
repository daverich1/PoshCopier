from playwright.sync_api import Locator, Page


CONDITION_ALIASES = {
    "new with tags": "New With Tags (NWT)",
    "new without tags": "Like New",
    "new with box": "New With Tags (NWT)",
    "new without box": "Like New",
    "excellent": "Like New",
    "like new": "Like New",
    "good": "Good",
    "fair": "Fair",
}


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def get_destination_condition(
    source_condition: str,
) -> str:
    normalized = normalize_text(source_condition)

    return CONDITION_ALIASES.get(
        normalized,
        source_condition,
    )


def find_condition_control(
    page: Page,
) -> Locator | None:
    candidates = page.locator(
        '[data-test="dropdown"], '
        'button, '
        '[role="button"], '
        'div[tabindex="0"]'
    )

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        try:
            if not candidate.is_visible():
                continue

            text = normalize_text(
                candidate.inner_text()
            )

            if (
                text == "select condition"
                or text.startswith("select condition")
            ):
                return candidate

        except Exception:
            continue

    return None


def find_visible_condition_option(
    page: Page,
    condition_value: str,
) -> Locator | None:
    target = normalize_text(condition_value)

    selectors = [
        "button",
        '[role="option"]',
        '[role="button"]',
        ".dropdown__link",
        "li",
        "div",
    ]

    partial_match = None

    for selector in selectors:
        candidates = page.locator(selector)

        for index in range(candidates.count()):
            candidate = candidates.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                full_text = candidate.inner_text().strip()

                if not full_text:
                    continue

                first_line = full_text.splitlines()[0].strip()
                normalized_first_line = normalize_text(
                    first_line
                )

                if normalized_first_line == target:
                    return candidate

                if (
                    target in normalized_first_line
                    or normalized_first_line in target
                ):
                    partial_match = candidate

            except Exception:
                continue

    return partial_match


def verify_condition_selected(
    page: Page,
    condition_value: str,
) -> bool:
    target = normalize_text(condition_value)

    candidates = page.locator(
        '[data-test="dropdown"], '
        '[role="button"], '
        'div[tabindex="0"]'
    )

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        try:
            if not candidate.is_visible():
                continue

            text = normalize_text(
                candidate.inner_text()
            )

            if (
                text == target
                or target in text
            ):
                return True

        except Exception:
            continue

    return False


def fill_condition(
    page: Page,
    condition_value: str,
) -> None:
    if not condition_value:
        raise RuntimeError(
            "The listing condition is missing."
        )

    destination_condition = get_destination_condition(
        condition_value
    )

    condition_control = find_condition_control(page)

    if condition_control is None:
        raise RuntimeError(
            "Could not find the condition control."
        )

    condition_control.scroll_into_view_if_needed()
    condition_control.click()

    page.wait_for_timeout(1000)

    option = find_visible_condition_option(
        page,
        destination_condition,
    )

    if option is None:
        raise RuntimeError(
            "Could not find condition option: "
            f"{destination_condition}"
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

    page.wait_for_timeout(1000)

    if not verify_condition_selected(
        page,
        destination_condition,
    ):
        raise RuntimeError(
            f"Condition {destination_condition} "
            "was clicked, but could not be verified."
        )

    print(
        f"Condition selected: "
        f"{destination_condition}"
    )
