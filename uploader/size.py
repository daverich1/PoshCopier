from playwright.sync_api import Locator, Page


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def find_size_control(
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
                text == "select size"
                or text.startswith("select size")
            ):
                return candidate

        except Exception:
            continue

    return None


def find_visible_size_option(
    page: Page,
    size_value: str,
) -> Locator | None:
    target = normalize_text(size_value)

    selectors = [
        "button",
        '[role="option"]',
        '[role="button"]',
        ".dropdown__link",
        "li",
        "div",
    ]

    for selector in selectors:
        candidates = page.locator(selector)

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


def click_done_with_javascript(
    page: Page,
) -> bool:
    try:
        result = page.evaluate(
            """
            () => {
                const elements = [
                    ...document.querySelectorAll(
                        "button, a, div, span, [role='button']"
                    )
                ];

                const visible = element => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();

                    return (
                        style.display !== "none"
                        && style.visibility !== "hidden"
                        && rect.width > 0
                        && rect.height > 0
                    );
                };

                const doneElement = elements.find(element => {
                    const text = (
                        element.innerText
                        || element.textContent
                        || ""
                    ).trim();

                    return text === "Done" && visible(element);
                });

                if (!doneElement) {
                    return false;
                }

                doneElement.click();
                return true;
            }
            """
        )

        return bool(result)

    except Exception:
        return False


def size_picker_is_open(
    page: Page,
) -> bool:
    try:
        done_text = page.get_by_text(
            "Done",
            exact=True,
        )

        for index in range(done_text.count()):
            if done_text.nth(index).is_visible():
                return True

    except Exception:
        pass

    return False


def verify_size_selected(
    page: Page,
    size_value: str,
) -> bool:
    target = normalize_text(size_value)

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

            if text == target:
                return True

        except Exception:
            continue

    return False


def fill_size(
    page: Page,
    size_value: str,
) -> None:
    if not size_value:
        raise RuntimeError(
            "The listing size is missing."
        )

    size_control = find_size_control(page)

    if size_control is None:
        raise RuntimeError(
            "Could not find the Select Size control."
        )

    size_control.scroll_into_view_if_needed()
    size_control.click()

    page.wait_for_timeout(1200)

    size_option = find_visible_size_option(
        page,
        size_value,
    )

    if size_option is None:
        raise RuntimeError(
            f"Could not find size option: {size_value}"
        )

    try:
        size_option.click(
            timeout=5000,
        )
    except Exception:
        size_option.click(
            timeout=5000,
            force=True,
        )

    print(f"Size selected: {size_value}")

    page.wait_for_timeout(700)

    if click_done_with_javascript(page):
        print("Size picker closed using Done.")

    else:
        print(
            "Done control was not directly clickable. "
            "Closing size picker with Escape."
        )

        page.keyboard.press("Escape")

    page.wait_for_timeout(1200)

    if size_picker_is_open(page):
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)

    if not verify_size_selected(
        page,
        size_value,
    ):
        raise RuntimeError(
            f"Size {size_value} was clicked, "
            "but the final size field could not be verified."
        )

    print("Size confirmed.")