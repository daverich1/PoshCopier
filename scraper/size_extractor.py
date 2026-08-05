from __future__ import annotations

import re

from playwright.sync_api import Page


_SIZE_PATTERN = re.compile(
    r"^(XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|"
    r"\d{1,3}(?:\.\d+)?|"
    r"\d{1,3}[WT]?|"
    r"\d+/\d+)$",
    re.IGNORECASE,
)


def extract_sizes(
    page: Page,
) -> list[str]:
    sizes: list[str] = []
    seen: set[str] = set()

    selectors = [
        "button",
        '[role="button"]',
    ]

    for selector in selectors:
        locator = page.locator(selector)

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(count):
            candidate = locator.nth(index)

            try:
                if not candidate.is_visible():
                    continue

                text = candidate.inner_text().strip()
            except Exception:
                continue

            if not text:
                continue

            text = " ".join(text.split())

            if not _SIZE_PATTERN.fullmatch(text):
                continue

            normalized = text.upper()

            if normalized in seen:
                continue

            seen.add(normalized)
            sizes.append(text)

    return sizes