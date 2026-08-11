"""Define which local listings are eligible for dveshop crosslisting."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
import re

from runtime_paths import DATABASE_FILE


POSHMARK_LISTING_ID = re.compile(r"^[0-9a-fA-F]{24}$")


def dveshop_source_listing_ids(
    database_file: Path = DATABASE_FILE,
) -> set[str]:
    if not database_file.exists():
        return set()
    with closing(sqlite3.connect(database_file)) as connection:
        rows = connection.execute(
            "SELECT source_listing_id FROM copied_listings"
        ).fetchall()
    return {
        listing_id
        for row in rows
        if (listing_id := str(row[0]).strip())
        and POSHMARK_LISTING_ID.fullmatch(listing_id)
    }
