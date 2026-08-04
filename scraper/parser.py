import re


CONDITION_LABELS = (
    "New With Tags",
    "New Without Tags",
    "New With Box",
    "New Without Box",
    "Excellent",
    "Good",
    "Fair",
)

IGNORED_BRAND_LINES = {
    "Listing Metrics",
    "Last 60 days",
    "Edit Listing",
}


def clean_lines(body_text):
    return [
        line.strip()
        for line in body_text.splitlines()
        if line.strip()
    ]


def extract_price(lines, title):
    if not title or title not in lines:
        return None

    title_index = lines.index(title)
    nearby_lines = lines[title_index + 1:title_index + 15]

    for line in nearby_lines:
        match = re.search(
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?",
            line,
        )

        if match:
            return match.group()

    return None


def extract_brand(lines, title):
    if not title or title not in lines:
        return None

    title_index = lines.index(title)
    nearby_lines = lines[title_index + 1:title_index + 15]

    for line in nearby_lines:
        if line in CONDITION_LABELS:
            continue

        if line in IGNORED_BRAND_LINES:
            continue

        if re.search(
            r"\$\d+(?:,\d{3})*(?:\.\d{2})?",
            line,
        ):
            continue

        if line.startswith("Pay in 4"):
            continue

        if line.startswith("Updated "):
            continue

        return line

    return None


def extract_size(lines):
    if "SIZE" not in lines:
        return None

    size_index = lines.index("SIZE")

    if size_index + 1 < len(lines):
        return lines[size_index + 1]

    return None


def extract_description(lines):
    if "Offer / Price Drop" not in lines:
        return None

    start = lines.index("Offer / Price Drop") + 1

    stopping_labels = (
        "CATEGORY",
        "COLOR",
        "STYLE TAGS",
        "SHIPPING/DISCOUNT",
    )

    end = len(lines)

    for label in stopping_labels:
        if label in lines:
            label_index = lines.index(label)

            if label_index > start:
                end = min(end, label_index)

    description_lines = lines[start:end]

    if not description_lines:
        return None

    return "\n".join(description_lines)


def extract_condition(lines):
    for condition in CONDITION_LABELS:
        if condition in lines:
            return condition

    return None


def extract_category(lines):
    if "CATEGORY" not in lines:
        return None

    category_index = lines.index("CATEGORY")

    if category_index + 1 < len(lines):
        return lines[category_index + 1]

    return None


def extract_colors(lines):
    if "COLOR" not in lines:
        return []

    color_index = lines.index("COLOR")
    colors = []

    stopping_labels = {
        "STYLE TAGS",
        "SHIPPING/DISCOUNT",
        "QUANTITY",
        "AVAILABILITY",
        "CATEGORY",
    }

    for line in lines[color_index + 1:]:
        if line in stopping_labels:
            break

        if line.startswith("Listing"):
            break

        colors.append(line)

        # Poshmark normally allows only a small number of colors.
        if len(colors) >= 2:
            break

    return colors