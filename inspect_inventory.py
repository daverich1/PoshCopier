from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

from login import (
    SOURCE_STATE_FILE,
    open_logged_in_browser,
)


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def inspect_jsonld(page: Page) -> None:
    print_section("JSON-LD")

    scripts = page.locator(
        'script[type="application/ld+json"]'
    ).all_text_contents()

    if not scripts:
        print("No JSON-LD found.")
        return

    for index, raw in enumerate(scripts, start=1):
        print()
        print(f"JSON-LD #{index}")
        print("-" * 80)

        try:
            payload: Any = json.loads(raw)
            print(
                json.dumps(
                    payload,
                    indent=2,
                    ensure_ascii=False,
                )
            )
        except json.JSONDecodeError:
            print(raw)


def inspect_visible_size_area(page: Page) -> None:
    print_section("VISIBLE SIZE-RELATED TEXT")

    body_text = page.locator("body").inner_text()

    keywords = (
        "size",
        "quantity",
        "multi item",
        "single item",
        "inventory",
    )

    lines = [
        line.strip()
        for line in body_text.splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        normalized = line.casefold()

        if any(
            keyword in normalized
            for keyword in keywords
        ):
            start = max(0, index - 3)
            end = min(
                len(lines),
                index + 8,
            )

            print()
            print(f"Context around line {index}:")

            for nearby_index in range(start, end):
                marker = (
                    ">>"
                    if nearby_index == index
                    else "  "
                )

                print(
                    f"{marker} "
                    f"{nearby_index}: "
                    f"{lines[nearby_index]}"
                )


def inspect_clickable_size_candidates(page: Page) -> None:
    print_section("VISIBLE CLICKABLE CANDIDATES")

    selectors = (
        "button",
        '[role="button"]',
        '[role="option"]',
        "a",
        "label",
    )

    seen: set[str] = set()

    for selector in selectors:
        locator = page.locator(selector)

        for index in range(locator.count()):
            candidate = locator.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                text = candidate.inner_text().strip()

                if not text:
                    continue

                normalized = " ".join(
                    text.casefold().split()
                )

                if normalized in seen:
                    continue

                if len(text) > 80:
                    continue

                seen.add(normalized)

                print(
                    f"[{selector}] {text}"
                )

            except Exception:
                continue


def inspect_script_inventory_clues(page: Page) -> None:
    print_section("SCRIPT INVENTORY CLUES")

    scripts = page.locator("script").all_text_contents()

    patterns = (
        "inventory",
        "quantity",
        "size",
        "variation",
        "variant",
        "multi_item",
        "multi item",
        "inventory_data",
    )

    matches_found = 0

    for script_index, script_text in enumerate(
        scripts,
        start=1,
    ):
        normalized = script_text.casefold()

        if not any(
            pattern in normalized
            for pattern in patterns
        ):
            continue

        compact = re.sub(
            r"\s+",
            " ",
            script_text,
        )

        for pattern in patterns:
            position = compact.casefold().find(
                pattern
            )

            if position == -1:
                continue

            start = max(0, position - 300)
            end = min(
                len(compact),
                position + 700,
            )

            snippet = compact[start:end]

            print()
            print(
                f"Script #{script_index} "
                f"around '{pattern}':"
            )
            print("-" * 80)
            print(snippet)

            matches_found += 1

            if matches_found >= 20:
                print()
                print(
                    "Stopped after 20 script clues "
                    "to keep output manageable."
                )
                return

    if matches_found == 0:
        print(
            "No obvious inventory clues found "
            "inside script text."
        )


def inspect_page_state(page: Page) -> None:
    print_section("WINDOW STATE KEYS")

    result = page.evaluate(
        """
        () => {
            const keys = Object.keys(window);

            return keys.filter(key => {
                const lower = key.toLowerCase();

                return (
                    lower.includes("inventory")
                    || lower.includes("listing")
                    || lower.includes("size")
                    || lower.includes("variation")
                    || lower.includes("variant")
                );
            });
        }
        """
    )

    if isinstance(result, list):
        for key in result:
            print(key)


def inspect_listing(url: str) -> None:
    with sync_playwright() as playwright:
        browser, context, page = (
            open_logged_in_browser(
                playwright,
                SOURCE_STATE_FILE,
            )
        )

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            page.wait_for_timeout(
                5000
            )

            print_section("PAGE")
            print("URL:", page.url)
            print("Title:", page.title())

            inspect_jsonld(page)
            inspect_visible_size_area(page)
            inspect_clickable_size_candidates(page)
            inspect_script_inventory_clues(page)
            inspect_page_state(page)

        finally:
            context.close()
            browser.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a Poshmark listing for "
            "multi-size inventory data."
        )
    )

    parser.add_argument(
        "url",
        help="Full Poshmark listing URL.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    inspect_listing(
        args.url
    )


if __name__ == "__main__":
    main()
