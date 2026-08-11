"""Tests for safe, unpublished eBay inventory request previews."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ebay.draft import EbayDraftBuilder
from ebay.inventory_payload import EbayInventoryPayloadBuilder


class EbayInventoryPayloadTests(unittest.TestCase):
    def _draft(self, image_urls=None):
        listing = {
            "listing_id": "abc 123",
            "title": "Test Bag",
            "description": "Useful description",
            "price": "$25",
            "condition": "New With Tags",
            "brand": "Example",
            "image_urls": image_urls or [],
        }
        directory = tempfile.TemporaryDirectory()
        listing_dir = Path(directory.name)
        (listing_dir / "image.jpg").write_bytes(b"image")
        draft = EbayDraftBuilder().build(listing, listing_dir)
        directory.cleanup()
        return draft

    def test_builds_exact_inventory_item_shape(self):
        draft = self._draft(["https://images.example/item.jpg"])
        preview = EbayInventoryPayloadBuilder().preview(draft)
        self.assertEqual(preview.method, "PUT")
        self.assertTrue(preview.url.startswith("https://api.sandbox.ebay.com/"))
        self.assertTrue(preview.url.endswith("POSH-abc%20123"))
        self.assertEqual(
            preview.payload["availability"]["shipToLocationAvailability"]["quantity"],
            1,
        )
        self.assertEqual(preview.payload["product"]["imageUrls"], ["https://images.example/item.jpg"])

    def test_preview_never_contains_a_real_token(self):
        preview = EbayInventoryPayloadBuilder().preview(
            self._draft(["https://images.example/item.jpg"])
        )
        self.assertEqual(
            preview.headers["Authorization"], "Bearer <USER_TOKEN_REDACTED>"
        )

    def test_blocks_local_only_images(self):
        with self.assertRaisesRegex(ValueError, "HTTPS image URL"):
            EbayInventoryPayloadBuilder().preview(self._draft())


if __name__ == "__main__":
    unittest.main()
