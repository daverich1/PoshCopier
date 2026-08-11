"""Prepare one combined listing or deterministic per-size listing variants."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from uploader.multi_size import normalize_sizes


SIZE_MODE_COMBINED = "combined"
SIZE_MODE_SEPARATE = "separate"
SIZE_MODES = (SIZE_MODE_COMBINED, SIZE_MODE_SEPARATE)
POSHMARK_TITLE_LIMIT = 80


def validate_size_mode(value: str) -> str:
    mode = str(value).strip().casefold()
    if mode not in SIZE_MODES:
        raise ValueError(f"size mode must be one of: {', '.join(SIZE_MODES)}")
    return mode


def size_variant_key(source_listing_id: str, size: str) -> str:
    normalized = " ".join(str(size).casefold().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{source_listing_id}::size::{digest}"


def _size_title(title: str, size: str) -> str:
    suffix = f" - Size {size}"
    available = max(0, POSHMARK_TITLE_LIMIT - len(suffix))
    base = re.sub(r"\s+", " ", str(title)).strip()[:available].rstrip()
    return f"{base}{suffix}"


def build_size_variants(listing: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    selected_mode = validate_size_mode(mode)
    sizes = normalize_sizes(listing.get("sizes"))
    if len(sizes) < 2 or selected_mode == SIZE_MODE_COMBINED:
        return [copy.deepcopy(listing)]

    source_listing_id = str(listing.get("listing_id", "")).strip()
    if not source_listing_id:
        raise ValueError("listing_id is required for separate-size publishing")

    variants: list[dict[str, Any]] = []
    for size in sizes:
        variant = copy.deepcopy(listing)
        variant["source_listing_id"] = source_listing_id
        variant["variant_key"] = size_variant_key(source_listing_id, size)
        variant["size"] = size
        variant["sizes"] = [size]
        variant["is_multi_size"] = False
        variant["title"] = _size_title(str(listing.get("title", "")), size)
        variants.append(variant)
    return variants
