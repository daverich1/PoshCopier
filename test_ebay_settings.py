"""Tests for eBay category suggestions and settings persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ebay.category_mapping import suggest_ebay_category
from ebay.settings import EbaySettings, EbaySettingsStore
from ebay.draft_store import EbayDraftReview, EbayDraftReviewStore
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore


class EbayCategoryMappingTests(unittest.TestCase):
    def test_specific_women_category_wins(self):
        self.assertEqual(
            suggest_ebay_category("WomenShoesSneakers"),
            "Women's Shoes",
        )

    def test_unknown_category_requires_review(self):
        self.assertIsNone(suggest_ebay_category("UnknownCollectibles"))


class EbaySettingsStoreTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbaySettingsStore(Path(directory) / "settings.json")
            expected = EbaySettings(
                merchant_location_key="main",
                payment_policy_id="pay",
                fulfillment_policy_id="ship",
                return_policy_id="returns",
            )
            store.save(expected)
            actual = store.load()
        self.assertEqual(actual, expected)
        self.assertEqual(actual.missing_fields(), [])

    def test_invalid_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            settings = EbaySettingsStore(path).load()
        self.assertEqual(settings, EbaySettings())


class EbayDraftReviewStoreTests(unittest.TestCase):
    def test_category_selection_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayDraftReviewStore(Path(directory))
            expected = EbayDraftReview("abc123", "63861")
            path = store.save(expected)
            actual = store.load("abc123")
        self.assertTrue(path.name.endswith("abc123.json"))
        self.assertEqual(actual, expected)

    def test_listing_id_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayDraftReviewStore(Path(directory))
            path = store.path_for("../abc")
        self.assertEqual(path.name, "abc.json")


class EbayCategoryRuleStoreTests(unittest.TestCase):
    def test_rule_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayCategoryRuleStore(Path(directory) / "rules.json")
            store.set_rule("WomenDresses", "63861")
            self.assertEqual(store.load(), {"WomenDresses": "63861"})

    def test_non_numeric_rule_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayCategoryRuleStore(Path(directory) / "rules.json")
            with self.assertRaises(ValueError):
                store.set_rule("WomenDresses", "not-an-id")


class EbayConditionRuleStoreTests(unittest.TestCase):
    def test_condition_rule_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayConditionRuleStore(Path(directory) / "conditions.json")
            store.set_rule("WomenDresses", "Like New", "PRE_OWNED_EXCELLENT")
            self.assertEqual(
                store.get_rule("WomenDresses", "Like New"),
                "PRE_OWNED_EXCELLENT",
            )

    def test_unknown_ebay_condition_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EbayConditionRuleStore(Path(directory) / "conditions.json")
            with self.assertRaises(ValueError):
                store.set_rule("WomenDresses", "Like New", "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
