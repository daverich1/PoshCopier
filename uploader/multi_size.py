from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Locator, Page


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
    return " ".join(value.casefold().split())


def compact_text(value: str | None) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        normalize_text(value),
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

            area = max(box["width"], 1) * max(box["height"], 1)
            matches.append((area, candidate))

        except Exception:
            continue

    if not matches:
        return None

    matches.sort(key=lambda item: item[0])
    return matches[0][1]


def click_safely(locator: Locator) -> None:
    locator.scroll_into_view_if_needed()

    try:
        locator.click(timeout=5000)
        return
    except Exception:
        pass

    try:
        locator.click(timeout=5000, force=True)
        return
    except Exception:
        pass

    box = locator.bounding_box()

    if box is None:
        raise RuntimeError(
            "Could not determine the element position."
        )

    locator.page.mouse.click(
        box["x"] + box["width"] / 2,
        box["y"] + box["height"] / 2,
    )


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

            if compact_text(
                candidate.inner_text()
            ) != target:
                continue

            box = candidate.bounding_box()

            if box is None:
                continue

            area = max(box["width"], 1) * max(box["height"], 1)
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
        page.wait_for_timeout(400)
        return True
    except Exception:
        return False


def select_multi_item(page: Page) -> None:
    control = find_exact_visible_text(
        page,
        "Multi Item",
    )

    if control is None:
        raise RuntimeError(
            "Could not find the Multi Item control."
        )

    click_safely(control)
    page.wait_for_timeout(700)
    print("Multi Item selected.")


def open_size_picker(page: Page) -> None:
    candidates = page.locator(
        '[data-test="dropdown"], '
        'button, [role="button"], div[tabindex="0"]'
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
                click_safely(candidate)
                page.wait_for_timeout(700)
                return

        except Exception:
            continue

    raise RuntimeError(
        "Could not find the Select Size control."
    )


def try_add_preset_size(
    page: Page,
    size_value: str,
) -> bool:
    for tab_name in (None, *PRESET_TABS):
        if tab_name is not None:
            if not select_tab(
                page,
                tab_name,
            ):
                continue

        option = find_exact_visible_text(
            page,
            size_value,
        )

        if option is None:
            continue

        click_safely(option)
        page.wait_for_timeout(250)

        if tab_name:
            print(
                f"Preset size added: {size_value} "
                f"under {tab_name}"
            )
        else:
            print(
                "Preset size added:",
                size_value,
            )

        return True

    return False


def find_visible_save_button(
    page: Page,
) -> Locator | None:
    return first_visible(
        page.get_by_text(
            "Save",
            exact=True,
        )
    )


def find_input_left_of(
    page: Page,
    reference: Locator,
) -> Locator | None:
    reference_box = reference.bounding_box()

    if reference_box is None:
        return None

    inputs = page.locator(
        'input[type="text"], '
        'input:not([type]), textarea'
    )

    matches: list[
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

            vertical_distance = abs(
                (
                    box["y"]
                    + box["height"] / 2
                )
                - (
                    reference_box["y"]
                    + reference_box["height"] / 2
                )
            )

            horizontal_gap = (
                reference_box["x"]
                - (
                    box["x"]
                    + box["width"]
                )
            )

            if vertical_distance > 50:
                continue

            if horizontal_gap < -30:
                continue

            score = (
                vertical_distance * 1000
                + abs(horizontal_gap)
            )

            matches.append(
                (
                    score,
                    candidate,
                )
            )

        except Exception:
            continue

    if not matches:
        return None

    matches.sort(
        key=lambda item: item[0]
    )
    return matches[0][1]


def add_custom_size(
    page: Page,
    size_value: str,
) -> None:
    if not select_tab(
        page,
        "Custom",
    ):
        raise RuntimeError(
            "Could not open the Custom size tab."
        )

    page.wait_for_timeout(400)

    add_another = first_visible(
        page.get_by_text(
            "Add another size",
            exact=True,
        )
    )

    if add_another is not None:
        click_safely(add_another)
        page.wait_for_timeout(400)

    save_button = find_visible_save_button(
        page
    )

    if save_button is None:
        raise RuntimeError(
            f"Could not find Save for custom size {size_value}."
        )

    custom_input = find_input_left_of(
        page,
        save_button,
    )

    if custom_input is None:
        raise RuntimeError(
            "Could not find the custom size box beside Save."
        )

    click_safely(custom_input)
    custom_input.fill("")
    custom_input.type(
        size_value,
        delay=100,
    )

    if compact_text(
        custom_input.input_value()
    ) != compact_text(
        size_value
    ):
        raise RuntimeError(
            f"Custom size field did not retain {size_value}."
        )

    click_safely(save_button)
    page.wait_for_timeout(600)
    print(
        "Custom size added:",
        size_value,
    )


def click_done(page: Page) -> None:
    done = first_visible(
        page.get_by_text(
            "Done",
            exact=True,
        )
    )

    if done is None:
        raise RuntimeError(
            "Could not find Done in the size picker."
        )

    click_safely(done)
    page.wait_for_timeout(800)
    print("Multi-size picker closed.")


def normalize_sizes(
    values: Any,
) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        size = str(value).strip()

        if not size:
            continue

        key = compact_text(size)

        if key in seen:
            continue

        seen.add(key)
        result.append(size)

    return result


def build_quantity_map(
    listing: dict[str, Any],
    sizes: list[str],
) -> dict[str, int]:
    quantities = {
        size: 1
        for size in sizes
    }

    inventory = listing.get(
        "inventory"
    )

    if not isinstance(
        inventory,
        list,
    ):
        return quantities

    for item in inventory:
        if not isinstance(
            item,
            dict,
        ):
            continue

        size = str(
            item.get("size", "")
        ).strip()

        if not size:
            continue

        try:
            quantity = int(
                item.get(
                    "quantity",
                    1,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            quantity = 1

        quantities[size] = max(
            quantity,
            1,
        )

    return quantities


def find_inventory_rows(
    page: Page,
) -> list[Locator]:
    inputs = page.locator(
        'input[type="number"], '
        'input[inputmode="numeric"], '
        'input'
    )

    rows: list[
        tuple[float, Locator]
    ] = []

    seen: set[
        tuple[int, int, int, int]
    ] = set()

    for index in range(inputs.count()):
        input_locator = inputs.nth(index)

        try:
            if not input_locator.is_visible():
                continue

            box = input_locator.bounding_box()

            if box is None:
                continue

            parent = input_locator.locator(
                "xpath=.."
            )

            # Walk upward until the row contains visible text
            # but remains reasonably small.
            row = parent

            for _ in range(4):
                text = normalize_text(
                    row.inner_text()
                )

                row_box = row.bounding_box()

                if (
                    row_box is not None
                    and row_box["height"] <= 90
                    and text
                ):
                    break

                row = row.locator(
                    "xpath=.."
                )

            row_box = row.bounding_box()

            if row_box is None:
                continue

            key = (
                round(row_box["x"]),
                round(row_box["y"]),
                round(row_box["width"]),
                round(row_box["height"]),
            )

            if key in seen:
                continue

            seen.add(key)
            rows.append(
                (
                    row_box["y"],
                    row,
                )
            )

        except Exception:
            continue

    rows.sort(
        key=lambda item: item[0]
    )

    return [
        row
        for _, row in rows
    ]


def set_available_quantities(
    page: Page,
    sizes: list[str],
    quantities: dict[str, int],
) -> None:
    rows = find_inventory_rows(
        page
    )

    if len(rows) < len(sizes):
        raise RuntimeError(
            "Could not find enough Available quantity rows. "
            f"Expected {len(sizes)}, found {len(rows)}."
        )

    used_rows: set[int] = set()

    for size in sizes:
        target_row: Locator | None = None
        target_index = -1

        for index, row in enumerate(rows):
            if index in used_rows:
                continue

            try:
                row_text = compact_text(
                    row.inner_text()
                )
            except Exception:
                continue

            if compact_text(size) in row_text:
                target_row = row
                target_index = index
                break

        if target_row is None:
            for index, row in enumerate(rows):
                if index not in used_rows:
                    target_row = row
                    target_index = index
                    break

        if target_row is None:
            raise RuntimeError(
                f"Could not find inventory row for size {size}."
            )

        quantity_input = first_visible(
            target_row.locator(
                "input"
            )
        )

        if quantity_input is None:
            raise RuntimeError(
                f"Could not find Available input for size {size}."
            )

        quantity = quantities.get(
            size,
            1,
        )

        quantity_input.fill(
            str(quantity)
        )

        used_rows.add(
            target_index
        )

        print(
            f"Available quantity set: "
            f"{size} = {quantity}"
        )


def fill_multi_size_inventory(
    page: Page,
    listing: dict[str, Any],
) -> None:
    sizes = normalize_sizes(
        listing.get("sizes")
    )

    if len(sizes) < 2:
        raise RuntimeError(
            "Multi-size workflow requires at least two sizes."
        )

    quantities = build_quantity_map(
        listing,
        sizes,
    )

    select_multi_item(page)
    open_size_picker(page)

    custom_sizes: list[str] = []

    for size in sizes:
        if not try_add_preset_size(
            page,
            size,
        ):
            custom_sizes.append(
                size
            )

    for size in custom_sizes:
        add_custom_size(
            page,
            size,
        )

    click_done(page)

    set_available_quantities(
        page,
        sizes,
        quantities,
    )

    print(
        "Multi-size inventory completed:",
        sizes,
    )
