from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.sync_api import Locator, Page


@dataclass(frozen=True)
class ParsedSize:
    original: str
    base: str
    width: str
    variants: tuple[str, ...]


PRESET_TABS = (
    "Standard",
    "Plus",
    "Petite",
    "Juniors",
    "Maternity",
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        value.casefold().split()
    )


def compact_text(value: str | None) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        normalize_text(value),
    )


def parse_size(size_value: str) -> ParsedSize:
    original = size_value.strip()

    if not original:
        raise RuntimeError(
            "The listing size is missing."
        )

    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*"
        r"(ww|xw|ew|w|m|n|wide|medium|narrow|extra\s+wide)?\s*",
        original,
        flags=re.IGNORECASE,
    )

    base = original
    width = ""

    if match and match.group(2):
        base = match.group(1)

        raw_width = normalize_text(
            match.group(2)
        )

        width = {
            "wide": "W",
            "medium": "M",
            "narrow": "N",
            "extra wide": "WW",
        }.get(
            raw_width,
            raw_width.upper(),
        )

    variants: list[str] = []

    def add(value: str) -> None:
        value = value.strip()

        if not value:
            return

        if compact_text(value) not in {
            compact_text(item)
            for item in variants
        }:
            variants.append(value)

    add(original)
    add(base)

    if width:
        add(f"{base}{width}")
        add(f"{base} {width}")

    add(
        re.sub(
            r"\s*\([^)]*\)\s*$",
            "",
            original,
        )
    )

    return ParsedSize(
        original=original,
        base=base,
        width=width,
        variants=tuple(variants),
    )


def click_safely(locator: Locator) -> None:
    locator.scroll_into_view_if_needed()

    try:
        locator.click(timeout=5000)
        return
    except Exception:
        pass

    try:
        locator.click(
            timeout=5000,
            force=True,
        )
        return
    except Exception:
        pass

    box = locator.bounding_box()

    if box is None:
        raise RuntimeError(
            "Could not determine element position."
        )

    locator.page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + box["height"] / 2,
    )


def first_visible(locator: Locator) -> Locator | None:
    try:
        count = locator.count()
    except Exception:
        return None

    matches: list[tuple[float, Locator]] = []

    for index in range(count):
        candidate = locator.nth(index)

        try:
            if not candidate.is_visible():
                continue

            box = candidate.bounding_box()

            if box is None:
                continue

            area = (
                max(box["width"], 1)
                * max(box["height"], 1)
            )

            matches.append((area, candidate))

        except Exception:
            continue

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def find_size_control(page: Page) -> Locator | None:
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


def find_exact_visible_text(
    page: Page,
    text: str,
) -> Locator | None:
    exact = first_visible(
        page.get_by_text(
            text,
            exact=True,
        )
    )

    if exact is not None:
        return exact

    target = compact_text(text)

    candidates = page.locator(
        "button, [role='button'], [role='option'], "
        "label, a, span, div"
    )

    matches: list[tuple[float, Locator]] = []

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        try:
            if not candidate.is_visible():
                continue

            raw = candidate.inner_text().strip()

            if compact_text(raw) != target:
                continue

            box = candidate.bounding_box()

            if box is None:
                continue

            area = (
                max(box["width"], 1)
                * max(box["height"], 1)
            )

            matches.append((area, candidate))

        except Exception:
            continue

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def select_tab(
    page: Page,
    tab_name: str,
) -> bool:
    tab = find_exact_visible_text(
        page,
        tab_name,
    )

    if tab is None:
        return False

    try:
        click_safely(tab)
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False


def find_size_in_presets(
    page: Page,
    parsed: ParsedSize,
) -> Locator | None:
    for variant in parsed.variants:
        option = find_exact_visible_text(
            page,
            variant,
        )

        if option is not None:
            return option

    for tab_name in PRESET_TABS:
        if not select_tab(page, tab_name):
            continue

        for variant in parsed.variants:
            option = find_exact_visible_text(
                page,
                variant,
            )

            if option is not None:
                print(
                    f"Size found under tab: {tab_name}"
                )
                return option

    return None


def find_custom_save_button(
    page: Page,
) -> Locator | None:
    return first_visible(
        page.get_by_text(
            "Save",
            exact=True,
        )
    )


def find_custom_input_next_to_save(
    page: Page,
    save_button: Locator,
) -> Locator | None:
    save_box = save_button.bounding_box()

    if save_box is None:
        return None

    inputs = page.locator(
        'input[type="text"], '
        'input:not([type]), '
        'textarea'
    )

    candidates: list[
        tuple[float, Locator]
    ] = []

    for index in range(inputs.count()):
        candidate = inputs.nth(index)

        try:
            if not candidate.is_visible():
                continue

            box = candidate.bounding_box()

            if box is None:
                continue

            # Custom input should be on the same row,
            # immediately to the left of Save.
            vertical_distance = abs(
                (
                    box["y"]
                    + box["height"] / 2
                )
                - (
                    save_box["y"]
                    + save_box["height"] / 2
                )
            )

            horizontal_gap = (
                save_box["x"]
                - (
                    box["x"]
                    + box["width"]
                )
            )

            if vertical_distance > 45:
                continue

            if horizontal_gap < -20:
                continue

            score = (
                vertical_distance * 1000
                + abs(horizontal_gap)
            )

            candidates.append(
                (
                    score,
                    candidate,
                )
            )

        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    return candidates[0][1]


def fill_custom_size(
    page: Page,
    size_value: str,
) -> bool:
    if not select_tab(
        page,
        "Custom",
    ):
        return False

    page.wait_for_timeout(
        600
    )

    save_button = find_custom_save_button(
        page
    )

    if save_button is None:
        raise RuntimeError(
            "Custom size tab opened, but Save "
            "could not be found."
        )

    custom_input = find_custom_input_next_to_save(
        page,
        save_button,
    )

    if custom_input is None:
        raise RuntimeError(
            "Could not find the custom size box "
            "immediately next to Save."
        )

    click_safely(
        custom_input
    )

    custom_input.fill("")

    custom_input.type(
        size_value,
        delay=120,
    )

    current_value = (
        custom_input.input_value()
    )

    if compact_text(current_value) != compact_text(
        size_value
    ):
        raise RuntimeError(
            "Custom size box did not retain the "
            f"value {size_value}. Current value: "
            f"{current_value}"
        )

    print(
        "Custom size typed:",
        current_value,
    )

    click_safely(
        save_button
    )

    page.wait_for_timeout(
        800
    )

    print(
        "Custom size saved."
    )

    return True


def click_done(page: Page) -> bool:
    done = first_visible(
        page.get_by_text(
            "Done",
            exact=True,
        )
    )

    if done is None:
        return False

    try:
        click_safely(done)
        return True
    except Exception:
        return False


def picker_is_open(page: Page) -> bool:
    return (
        first_visible(
            page.get_by_text(
                "Done",
                exact=True,
            )
        )
        is not None
    )


def verify_selected(
    page: Page,
    parsed: ParsedSize,
) -> bool:
    accepted = {
        compact_text(value)
        for value in parsed.variants
    }

    accepted.add(
        compact_text(parsed.base)
    )

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

            current = compact_text(
                candidate.inner_text()
            )

            if current in accepted:
                return True

        except Exception:
            continue

    return False


def fill_size(
    page: Page,
    size_value: str,
) -> None:
    parsed = parse_size(
        size_value
    )

    control = find_size_control(
        page
    )

    if control is None:
        raise RuntimeError(
            "Could not find the Select Size control."
        )

    click_safely(control)
    page.wait_for_timeout(1000)

    option = find_size_in_presets(
        page,
        parsed,
    )

    if option is not None:
        try:
            selected_text = (
                option.inner_text().strip()
            )
        except Exception:
            selected_text = parsed.base

        click_safely(option)

        print(
            "Size selected:",
            selected_text or parsed.base,
        )

    else:
        print(
            "Preset size not found. "
            "Using Custom size."
        )

        if not fill_custom_size(
            page,
            parsed.original,
        ):
            raise RuntimeError(
                "Could not open the Custom size tab."
            )

    page.wait_for_timeout(500)

    if click_done(page):
        print(
            "Size picker closed using Done."
        )
    else:
        page.keyboard.press("Escape")
        print(
            "Size picker closed using Escape."
        )

    page.wait_for_timeout(800)

    if picker_is_open(page):
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

    if not verify_selected(
        page,
        parsed,
    ):
        raise RuntimeError(
            f"Size {parsed.original} was entered, "
            "but the final size field could not "
            "be verified."
        )

    print("Size confirmed.")
