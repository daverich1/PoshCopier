"""Tests for portable downloaded-image resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uploader.listing_loader import get_image_paths


class ListingLoaderTests(unittest.TestCase):
    def test_windows_saved_path_falls_back_to_local_listing_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            downloads = Path(directory)
            listing_dir = downloads / "abc123"
            listing_dir.mkdir()
            local_image = listing_dir / "image_1.jpg"
            local_image.write_bytes(b"image")
            listing = {
                "listing_id": "abc123",
                "local_images": [
                    r"C:\Users\old-machine\PoshCopier\downloads\abc123\image_1.jpg"
                ],
            }

            with patch("uploader.listing_loader.DOWNLOADS_DIR", downloads):
                result = get_image_paths(listing)

            self.assertEqual(result, [str(local_image)])


if __name__ == "__main__":
    unittest.main()
