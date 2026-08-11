"""Conservative category suggestions for eBay draft review."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EbayCategorySuggestion:
    source_prefix: str
    ebay_category_name: str


SUGGESTIONS = (
    EbayCategorySuggestion("WomenIntimates&Sleepwear", "Women's Intimates & Sleep"),
    EbayCategorySuggestion("WomenJackets&Coats", "Women's Coats, Jackets & Vests"),
    EbayCategorySuggestion("WomenPants&Jumpsuits", "Women's Pants & Jumpsuits"),
    EbayCategorySuggestion("WomenSkincare", "Skin Care"),
    EbayCategorySuggestion("WomenDresses", "Women's Dresses"),
    EbayCategorySuggestion("WomenSweaters", "Women's Sweaters"),
    EbayCategorySuggestion("WomenShorts", "Women's Shorts"),
    EbayCategorySuggestion("WomenSkirts", "Women's Skirts"),
    EbayCategorySuggestion("WomenJeans", "Women's Jeans"),
    EbayCategorySuggestion("WomenShoes", "Women's Shoes"),
    EbayCategorySuggestion("WomenBags", "Women's Bags & Handbags"),
    EbayCategorySuggestion("WomenSwim", "Women's Swimwear"),
    EbayCategorySuggestion("WomenTops", "Women's Tops"),
    EbayCategorySuggestion("WomenMakeup", "Makeup"),
    EbayCategorySuggestion("Home", "Home & Garden"),
    EbayCategorySuggestion("Men", "Men's Clothing, Shoes & Accessories"),
    EbayCategorySuggestion("Kids", "Kids' Clothing, Shoes & Accessories"),
    EbayCategorySuggestion("Pets", "Pet Supplies"),
    EbayCategorySuggestion("Electronics", "Consumer Electronics"),
)


def suggest_ebay_category(source_category: str | None) -> str | None:
    normalized = _compact(source_category)
    matches = sorted(
        SUGGESTIONS,
        key=lambda suggestion: len(_compact(suggestion.source_prefix)),
        reverse=True,
    )
    for suggestion in matches:
        if normalized.startswith(_compact(suggestion.source_prefix)):
            return suggestion.ebay_category_name
    return None


def _compact(value: str | None) -> str:
    return "".join(
        character.casefold()
        for character in str(value or "")
        if character.isalnum()
    )
