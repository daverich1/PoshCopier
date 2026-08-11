"""Tests for dveshop-only eBay source scoping."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ebay.source_scope import dveshop_source_listing_ids


class EbaySourceScopeTests(unittest.TestCase):
    def test_returns_only_database_copied_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE copied_listings (source_listing_id TEXT)"
                )
                connection.executemany(
                    "INSERT INTO copied_listings VALUES (?)",
                    [
                        ("67a5345f69ef1a55c6e72ffa",),
                        ("6a37221034e98482be8f3305",),
                        ("test-123",),
                    ],
                )
                connection.commit()
            result = dveshop_source_listing_ids(database)
        self.assertEqual(
            result,
            {
                "67a5345f69ef1a55c6e72ffa",
                "6a37221034e98482be8f3305",
            },
        )


if __name__ == "__main__":
    unittest.main()
