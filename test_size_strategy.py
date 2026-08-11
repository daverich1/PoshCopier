"""Tests for combined and separate Poshmark size publishing strategies."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from uploader.size_strategy import build_size_variants, size_variant_key
from run_pipeline import process_destination_listing


class SizeStrategyTests(unittest.TestCase):
    def setUp(self):
        self.listing = {
            "listing_id": "abc123",
            "title": "Example Running Shoe",
            "size": "8",
            "sizes": ["8", "9", "9"],
            "is_multi_size": True,
        }

    def test_combined_mode_preserves_one_multi_size_listing(self):
        variants = build_size_variants(self.listing, "combined")
        self.assertEqual(len(variants), 1)
        self.assertTrue(variants[0]["is_multi_size"])
        self.assertEqual(variants[0]["sizes"], ["8", "9", "9"])

    def test_separate_mode_builds_one_unique_single_size_listing_each(self):
        variants = build_size_variants(self.listing, "separate")
        self.assertEqual([value["size"] for value in variants], ["8", "9"])
        self.assertTrue(all(not value["is_multi_size"] for value in variants))
        self.assertEqual(len({value["variant_key"] for value in variants}), 2)
        self.assertTrue(variants[0]["title"].endswith(" - Size 8"))
        self.assertLessEqual(len(variants[0]["title"]), 80)

    def test_variant_key_is_stable_and_size_specific(self):
        self.assertEqual(size_variant_key("abc", "M"), size_variant_key("abc", " m "))
        self.assertNotEqual(size_variant_key("abc", "M"), size_variant_key("abc", "L"))

    @patch("run_pipeline.mark_local_copied")
    @patch("run_pipeline.mark_database_copied")
    @patch("run_pipeline._process_destination_payload")
    @patch("run_pipeline.listing_already_copied", return_value=False)
    @patch("run_pipeline.load_listing")
    def test_separate_mode_marks_base_complete_only_after_every_variant(
        self,
        load_listing,
        _already_copied,
        process_payload,
        mark_database,
        mark_local,
    ):
        load_listing.return_value = self.listing
        process_payload.side_effect = ["uploaded", "already_exists"]

        result = process_destination_listing(
            Mock(), Path("listing.json"), [], publish=True, size_mode="separate"
        )

        self.assertEqual(result, "uploaded")
        self.assertEqual(process_payload.call_count, 2)
        mark_database.assert_called_once_with("abc123", None, "Example Running Shoe")
        mark_local.assert_called_once_with("abc123")

    @patch("run_pipeline.mark_local_copied")
    @patch("run_pipeline.mark_database_copied")
    @patch("run_pipeline._process_destination_payload")
    @patch("run_pipeline.listing_already_copied", return_value=False)
    @patch("run_pipeline.load_listing")
    def test_ambiguous_size_publish_never_marks_base_complete(
        self,
        load_listing,
        _already_copied,
        process_payload,
        mark_database,
        mark_local,
    ):
        load_listing.return_value = self.listing
        process_payload.side_effect = ["uploaded", "publish_unverified"]

        result = process_destination_listing(
            Mock(), Path("listing.json"), [], publish=True, size_mode="separate"
        )

        self.assertEqual(result, "publish_unverified")
        mark_database.assert_not_called()
        mark_local.assert_not_called()


if __name__ == "__main__":
    unittest.main()
