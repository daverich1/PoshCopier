import sqlite3
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_DIR / "poshcopier.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def initialize_database():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS copied_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_listing_id TEXT UNIQUE NOT NULL,
                destination_listing_id TEXT,
                title TEXT,
                copied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def listing_already_copied(source_listing_id):
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT 1
            FROM copied_listings
            WHERE source_listing_id = ?
            LIMIT 1
            """,
            (source_listing_id,),
        ).fetchone()

    return result is not None


def mark_listing_copied(
    source_listing_id,
    destination_listing_id=None,
    title=None,
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO copied_listings (
                source_listing_id,
                destination_listing_id,
                title
            )
            VALUES (?, ?, ?)
            """,
            (
                source_listing_id,
                destination_listing_id,
                title,
            ),
        )
