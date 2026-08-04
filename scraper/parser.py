from __future__ import annotations

import re


CONDITION_PATTERNS = (
    ("new with tags", "New With Tags"),
    ("nwt", "New With Tags"),

    ("new without tags", "New Without Tags"),
    ("nwot", "New Without Tags"),

    ("new with box", "New With Box"),
    ("new without box", "New Without Box"),

    ("like new", "Like New"),

    (
        "excellent used condition",
        "Excellent Used Condition",
    ),
    (
        "excellent condition",
        "Excellent Used Condition",
    ),
    (
        "excellent",
        "Excellent Used Condition",
    ),

    (
        "good used condition",
        "Good Used Condition",
    ),
    (
        "good condition",
        "Good Used Condition",
    ),
    (
        "good",
        "Good Used Condition",
    ),

    (
        "fair used condition",
        "Fair Condition",
    ),
    (
        "fair condition",
        "Fair Condition",
    ),
    (
        "fair",
        "Fair Condition",
    ),
)


IGNORED_BRAND_LINES = {
    "Listing Metrics",
    "Last 60 days",
    "Edit Listing",
}


def clean_lines(
    body_text: str,
) -> list[str]:
    return [
        line.strip()
        for line in body_text.splitlines()
        if line.strip()
    ]


def normalize_line(
    value: str | None,
) -> str:
    if not value:
        return ""

    return " ".join(
        value.casefold().split()
    )


def extract_condition(
    lines: list[str],
) -> str | None:
    for line in lines:
        normalized = normalize_line(
            line
        )

        for pattern, result in CONDITION_PATTERNS:
            # Exact-line matching first prevents accidentally
            # detecting words such as "good" inside descriptions.
            if normalized == pattern:
                return result

        # Handle common labels embedded in a longer line.
        for pattern, result in CONDITION_PATTERNS:
            if (
                len(pattern) >= 8
                and pattern in normalized
            ):
                return result

    return None


def line_is_condition(
    line: str,
) -> bool:
    normalized = normalize_line(
        line
    )

    for pattern, _ in CONDITION_PATTERNS:
        if normalized == pattern:
            return True

    return False


def extract_price(
    lines: list[str],
    title: str | None,
) -> str | None:
    if not title or title not in lines:
        return None

    title_index = lines.index(
        title
    )

    nearby_lines = lines[
        title_index + 1:
        title_index + 15
    ]

    for line in nearby_lines:
        match = re.search(
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?",
            line,
        )

        if match:
            return match.group()

    return None


def extract_brand(
    lines: list[str],
    title: str | None,
) -> str | None:
    if not title or title not in lines:
        return None

    title_index = lines.index(
        title
    )

    nearby_lines = lines[
        title_index + 1:
        title_index + 15
    ]

    for line in nearby_lines:
        if line_is_condition(
            line
        ):
            continue

        if line in IGNORED_BRAND_LINES:
            continue

        if re.search(
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?",
            line,
        ):
            continue

        if line.startswith(
            "Pay in 4"
        ):
            continue

        if line.startswith(
            "Updated "
        ):
            continue

        return line

    return None


def extract_size(
    lines: list[str],
) -> str | None:
    for label in (
        "SIZE",
        "Size",
    ):
        if label not in lines:
            continue

        size_index = lines.index(
            label
        )

        if (
            size_index + 1
            < len(lines)
        ):
            next_line = lines[
                size_index + 1
            ].strip()

            if (
                next_line
                and normalize_line(next_line)
                != "size chart"
            ):
                return next_line

    return None


def extract_description(
    lines: list[str],
) -> str | None:
    if "Offer / Price Drop" not in lines:
        return None

    start = (
        lines.index(
            "Offer / Price Drop"
        )
        + 1
    )

    stopping_labels = (
        "CATEGORY",
        "COLOR",
        "STYLE TAGS",
        "SHIPPING/DISCOUNT",
    )

    end = len(
        lines
    )

    for label in stopping_labels:
        if label not in lines:
            continue

        label_index = lines.index(
            label
        )

        if label_index > start:
            end = min(
                end,
                label_index,
            )

    description_lines = lines[
        start:end
    ]

    if not description_lines:
        return None

    return "\n".join(
        description_lines
    )


def extract_category(
    lines: list[str],
) -> str | None:
    if "CATEGORY" not in lines:
        return None

    category_index = lines.index(
        "CATEGORY"
    )

    if (
        category_index + 1
        < len(lines)
    ):
        return lines[
            category_index + 1
        ]

    return None


def extract_colors(
    lines: list[str],
) -> list[str]:
    if "COLOR" not in lines:
        return []

    color_index = lines.index(
        "COLOR"
    )

    colors: list[str] = []

    stopping_labels = {
        "STYLE TAGS",
        "SHIPPING/DISCOUNT",
        "QUANTITY",
        "AVAILABILITY",
        "CATEGORY",
    }

    for line in lines[
        color_index + 1:
    ]:
        if line in stopping_labels:
            break

        if line.startswith(
            "Listing"
        ):
            break

        colors.append(
            line
        )

        if len(colors) >= 2:
            break

    return colors
