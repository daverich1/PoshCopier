"""
Persistent destination closet cache for duplicate detection.

Reduces redundant full closet scans by caching listing URLs for 24 hours.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from runtime_paths import LOGS_DIR


CACHE_FILE = LOGS_DIR / "destination_closet_cache.json"
DEFAULT_TTL_HOURS = 24


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write JSON to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        
        Path(temp_path).replace(path)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise


def load_cache() -> dict[str, Any] | None:
    """Load cache from disk. Returns None if missing or invalid."""
    if not CACHE_FILE.exists():
        return None
    
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(closet_url: str, listing_urls: list[str], full_scan: bool = False) -> None:
    """
    Save cache to disk.
    
    Args:
        closet_url: Destination closet URL
        listing_urls: List of listing URLs
        full_scan: True if this is from a full scan, False for incremental updates
    """
    now = datetime.now(timezone.utc).isoformat()
    
    if full_scan:
        # Full scan: Set both timestamps to now
        full_scan_at = now
    else:
        # Incremental update: Preserve existing full_scan_at
        # Load existing cache to get full_scan_at (even if stale)
        existing_cache = load_cache()
        
        if existing_cache and isinstance(existing_cache, dict):
            # Check if cache is structurally valid for same closet
            if (existing_cache.get("version") == 1 and
                existing_cache.get("closet_url") == closet_url and
                existing_cache.get("full_scan_at")):
                # Preserve existing full_scan_at (even if > 24 hours old)
                full_scan_at = existing_cache["full_scan_at"]
            else:
                # Invalid structure or different closet, treat as full scan
                full_scan_at = now
        else:
            # No valid cache exists, treat as full scan
            full_scan_at = now
    
    payload = {
        "version": 1,
        "closet_url": closet_url,
        "full_scan_at": full_scan_at,
        "updated_at": now,
        "ttl_hours": DEFAULT_TTL_HOURS,
        "listing_urls": listing_urls,
    }
    _atomic_write_json(CACHE_FILE, payload)


def is_cache_fresh(cache: dict | None, closet_url: str) -> bool:
    """Check if cache is valid and fresh based on full_scan_at."""
    if not cache or not isinstance(cache, dict):
        return False
    
    if cache.get("version") != 1:
        return False
    
    if cache.get("closet_url") != closet_url:
        return False
    
    # Check full_scan_at (NOT updated_at)
    full_scan_at = cache.get("full_scan_at")
    if not full_scan_at:
        return False
    
    try:
        scanned = datetime.fromisoformat(full_scan_at)
        age_hours = (datetime.now(timezone.utc) - scanned).total_seconds() / 3600
        ttl = cache.get("ttl_hours", DEFAULT_TTL_HOURS)
        
        if age_hours > ttl:
            return False
    except (ValueError, TypeError):
        return False
    
    listing_urls = cache.get("listing_urls", [])
    if not isinstance(listing_urls, list) or len(listing_urls) == 0:
        return False
    
    return True


def merge_urls(cached_urls: list[str], fresh_urls: list[str]) -> list[str]:
    """Merge fresh URLs into cached URLs, newest first, deduplicated."""
    seen = set()
    merged = []
    
    for url in fresh_urls:
        if url not in seen:
            seen.add(url)
            merged.append(url)
    
    for url in cached_urls:
        if url not in seen:
            seen.add(url)
            merged.append(url)
    
    return merged


def add_url(listing_urls: list[str], url: str) -> None:
    """Add URL to list if not present (prepends)."""
    if url and url not in listing_urls:
        listing_urls.insert(0, url)


def get_or_refresh_destination_urls(
    page: Page,
    closet_url: str,
    refresh_count: int = 96,
) -> list[str]:
    """
    Get destination URLs using cache + small refresh, or full scan if needed.
    
    Args:
        page: Playwright page
        closet_url: Destination closet URL
        refresh_count: Number of newest listings to refresh (default: 96)
    
    Returns:
        List of destination listing URLs
    """
    from uploader.duplicate_detector import collect_destination_listing_urls
    from uploader.publisher import load_fresh_listings_with_scroll
    
    cache = load_cache()
    
    if is_cache_fresh(cache, closet_url):
        # Cache is fresh (full_scan_at < 24 hours old)
        print(f"Using cached destination URLs ({len(cache['listing_urls'])} listings)")
        
        # Small refresh
        print(f"Refreshing {refresh_count} newest listings...")
        page.goto(closet_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        fresh_urls = load_fresh_listings_with_scroll(page, refresh_count)
        
        # Merge
        merged = merge_urls(cache["listing_urls"], fresh_urls)
        print(f"Merged: {len(merged)} total URLs")
        
        # Save merged cache (incremental update, preserves full_scan_at)
        try:
            save_cache(closet_url, merged, full_scan=False)
            print("Destination cache updated with fresh URLs")
        except Exception as error:
            print(f"Warning: Could not update destination cache: {error}")
        
        return merged
    
    # Cache is stale or missing - perform full scan
    print("Cache miss - performing full destination scan...")
    destination_urls = collect_destination_listing_urls(page, closet_url)
    
    # Save cache (full scan, sets both timestamps to now)
    try:
        save_cache(closet_url, destination_urls, full_scan=True)
        print("Destination cache saved")
    except Exception as e:
        print(f"Warning: Could not save cache: {e}")
    
    return destination_urls
