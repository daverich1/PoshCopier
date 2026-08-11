"""Tests for bulk offline eBay readiness scanning."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ebay.draft_store import EbayDraftReview, EbayDraftReviewStore
from ebay.category_rules import EbayCategoryRuleStore
from ebay.condition_rules import EbayConditionRuleStore
from ebay.readiness import EbayReadinessScanner
from ebay.settings import EbaySettings, EbaySettingsStore


class EbayReadinessScannerTests(unittest.TestCase):
    def _listing(self, root: Path, listing_id: str = "abc123") -> Path:
        folder = root / listing_id
        folder.mkdir(parents=True)
        (folder / "image_1.jpg").write_bytes(b"image")
        (folder / "listing.json").write_text(
            json.dumps(
                {
                    "listing_id": listing_id,
                    "title": "Blue Dress",
                    "description": "A useful description.",
                    "price": "$25",
                    "brand": "Example",
                    "size": "M",
                    "category": "WomenDresses",
                    "condition": "New With Tags",
                }
            ),
            encoding="utf-8",
        )
        return folder

    def test_complete_offline_configuration_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            settings_store = EbaySettingsStore(root / "settings.json")
            settings_store.save(
                EbaySettings(
                    merchant_location_key="main",
                    payment_policy_id="pay",
                    fulfillment_policy_id="ship",
                    return_policy_id="returns",
                )
            )
            review_store = EbayDraftReviewStore(root / "reviews")
            review_store.save(EbayDraftReview("abc123", "63861"))
            report = EbayReadinessScanner(
                downloads,
                settings_store=settings_store,
                review_store=review_store,
                eligible_listing_ids={"abc123"},
            ).scan()
        self.assertEqual(report.total, 1)
        self.assertEqual(report.ready, 1)
        self.assertEqual(report.category_confirmed, 1)
        self.assertEqual(report.database_eligible, 1)
        self.assertEqual(report.missing_local_files, 0)

    def test_missing_configuration_is_classified_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                eligible_listing_ids={"abc123"},
            ).scan()
        self.assertEqual(report.needs_configuration, 1)
        self.assertEqual(report.needs_source_fix, 0)

    def test_non_dveshop_listing_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                eligible_listing_ids=set(),
            ).scan()
        self.assertEqual(report.total, 0)

    def test_database_record_without_local_file_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = EbayReadinessScanner(
                root / "downloads",
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                eligible_listing_ids={"missing123"},
            ).scan()
        self.assertEqual(report.database_eligible, 1)
        self.assertEqual(report.total, 0)
        self.assertEqual(report.missing_local_files, 1)

    def test_bulk_category_rule_applies_to_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            rules = EbayCategoryRuleStore(root / "rules.json")
            rules.set_rule("WomenDresses", "63861")
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                category_rule_store=rules,
                eligible_listing_ids={"abc123"},
            ).scan()
        self.assertEqual(report.items[0].category_id, "63861")
        self.assertEqual(report.category_confirmed, 1)
        self.assertEqual(report.category_groups[0].listing_count, 1)

    def test_bulk_condition_rule_overrides_default_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            conditions = EbayConditionRuleStore(root / "conditions.json")
            conditions.set_rule(
                "WomenDresses",
                "New With Tags",
                "NEW_WITH_DEFECTS",
            )
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                condition_rule_store=conditions,
                eligible_listing_ids={"abc123"},
            ).scan()
        self.assertEqual(report.items[0].ebay_condition, "NEW_WITH_DEFECTS")
        self.assertEqual(report.condition_groups[0].listing_count, 1)

    def test_default_condition_is_resolved_in_condition_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads)
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=EbayDraftReviewStore(root / "reviews"),
                eligible_listing_ids={"abc123"},
            ).scan()
        self.assertEqual(report.condition_groups[0].ebay_condition, "NEW")

    def test_mixed_per_listing_categories_resolve_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / "downloads"
            self._listing(downloads, "first")
            self._listing(downloads, "second")
            reviews = EbayDraftReviewStore(root / "reviews")
            reviews.save(EbayDraftReview("first", "53557"))
            reviews.save(EbayDraftReview("second", "55793"))
            report = EbayReadinessScanner(
                downloads,
                settings_store=EbaySettingsStore(root / "missing.json"),
                review_store=reviews,
                category_rule_store=EbayCategoryRuleStore(root / "rules.json"),
                eligible_listing_ids={"first", "second"},
            ).scan()
        self.assertEqual(report.category_groups[0].category_id, "PER_LISTING")


if __name__ == "__main__":
    unittest.main()
