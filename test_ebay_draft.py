"""Tests for offline eBay draft construction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ebay.draft import EbayDraftBuilder


class EbayDraftBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = EbayDraftBuilder()
        self.listing = {
            "listing_id": "abc123",
            "title": "Test\u205fJacket",
            "description": "A useful description.",
            "price": "$25",
            "brand": "Example",
            "size": "M",
            "colors": ["Blue", "White"],
            "condition": "New With Tags",
        }

    def test_builds_reviewable_draft_without_publishing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")

            draft = self.builder.build(self.listing, listing_dir)

        self.assertEqual(draft.sku, "POSH-abc123")
        self.assertEqual(draft.title, "Test Jacket")
        self.assertEqual(draft.price, "25.00")
        self.assertEqual(draft.condition, "NEW")
        self.assertEqual(draft.aspects["Color"], ["Blue", "White"])
        self.assertTrue(draft.ready_for_review)
        self.assertFalse(draft.ready_to_publish)
        self.assertIn(
            "Configuration: eBay category ID is required.",
            draft.blockers,
        )

    def test_complete_configuration_removes_configuration_blockers(self):
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")

            draft = self.builder.build(
                self.listing,
                listing_dir,
                category_id="57988",
                merchant_location_key="main",
                payment_policy_id="payment",
                fulfillment_policy_id="shipping",
                return_policy_id="returns",
            )

        self.assertTrue(draft.ready_to_publish)

    def test_overlong_title_is_a_source_blocker(self):
        listing = dict(self.listing, title="x" * 81)
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")

            draft = self.builder.build(listing, listing_dir)

        self.assertFalse(draft.ready_for_review)
        self.assertIn("80-character limit", " ".join(draft.blockers))

    def test_like_new_condition_maps_to_pre_owned_excellent(self):
        listing = dict(self.listing, condition="Like New")
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")
            draft = self.builder.build(listing, listing_dir)
        self.assertTrue(draft.ready_for_review)
        self.assertEqual(draft.condition, "PRE_OWNED_EXCELLENT")
        self.assertNotIn("explicit eBay mapping", " ".join(draft.blockers))

    def test_new_shoes_without_box_evidence_use_new_other(self):
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")
            draft = self.builder.build(
                self.listing,
                listing_dir,
                category_id="53557",
            )
        self.assertEqual(draft.condition, "NEW_OTHER")

    def test_new_shoes_with_original_box_evidence_use_new(self):
        listing = dict(self.listing, description="Brand new in box.")
        with tempfile.TemporaryDirectory() as directory:
            listing_dir = Path(directory)
            (listing_dir / "image_1.jpg").write_bytes(b"image")
            draft = self.builder.build(
                listing,
                listing_dir,
                category_id="53557",
            )
        self.assertEqual(draft.condition, "NEW")


if __name__ == "__main__":
    unittest.main()
