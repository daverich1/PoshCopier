"""
Test script for single-listing share with selector discovery.

This script tests the PoshmarkShareEngine by:
1. Opening an authenticated browser session (destination account)
2. Navigating to the destination closet
3. Attempting to share a single listing
4. Reporting discovered selectors and results

Usage:
    python tools/test_share_single.py

Requirements:
    - destination_state.json must exist (run login.py first)
    - Destination closet must have at least one active listing
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE
from sharing.share_config import ShareConfig
from sharing.share_engine import PoshmarkShareEngine, ShareableListing


def get_destination_closet_url() -> str:
    """
    Get destination closet URL from config.json or use default.
    
    Returns:
        Closet URL string
    """
    import json
    
    config_file = PROJECT_DIR / "config.json"
    
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
            # Try to infer from source URL or use hardcoded default
            source_url = config.get("source_closet_url", "")
            if source_url:
                print(f"Found source closet URL in config: {source_url}")
        except Exception:
            pass
    
    # Default destination closet (from run_pipeline.py)
    return "https://poshmark.com/closet/dveshop"


def discover_first_listing(page) -> ShareableListing | None:
    """
    Discover the first available listing in the closet.
    
    Args:
        page: Playwright page on closet
    
    Returns:
        ShareableListing or None if no listings found
    """
    print("\n" + "=" * 60)
    print("DISCOVERING FIRST LISTING")
    print("=" * 60)
    
    try:
        # Find all listing links
        listing_links = page.locator('a[href*="/listing/"]').all()
        
        if not listing_links:
            print("ERROR: No listing links found in closet")
            return None
        
        print(f"Found {len(listing_links)} listing link(s)")
        
        # Get first listing
        first_link = listing_links[0]
        url = first_link.get_attribute("href")
        
        if not url:
            print("ERROR: First link has no href")
            return None
        
        # Make URL absolute
        if url.startswith("/"):
            url = f"https://poshmark.com{url}"
        
        print(f"First listing URL: {url}")
        
        # Extract listing ID from URL
        listing_id = url.split("/")[-1].split("-")[-1] if "-" in url else url.split("/")[-1]
        
        # Try to get title from card
        try:
            # Navigate up to find card container
            card = first_link.locator("xpath=ancestor::*[contains(@class, 'card') or contains(@class, 'tile') or contains(@class, 'item')]").first
            title_text = card.inner_text()
            # Clean up title (first line usually)
            title = title_text.split("\n")[0].strip()[:100]
        except Exception:
            title = "Unknown Title"
        
        print(f"Listing ID: {listing_id}")
        print(f"Title: {title}")
        
        listing = ShareableListing(
            listing_id=listing_id,
            url=url,
            title=title,
            available=True,
        )
        
        return listing
    
    except Exception as error:
        print(f"ERROR discovering listing: {error}")
        return None


def main() -> None:
    """Main test function."""
    print("\n" + "=" * 60)
    print("POSHMARK SHARE ENGINE - SINGLE LISTING TEST")
    print("=" * 60)
    
    # Check for destination state file
    if not DESTINATION_STATE_FILE.exists():
        print(f"\nERROR: {DESTINATION_STATE_FILE.name} not found!")
        print("Please run login.py first to save destination account session.")
        sys.exit(1)
    
    print(f"\n✓ Found {DESTINATION_STATE_FILE.name}")
    
    # Get closet URL
    closet_url = get_destination_closet_url()
    print(f"✓ Destination closet: {closet_url}")
    
    # Create share config
    config = ShareConfig(
        closet_url=closet_url,
        delay_seconds=5.0,
        jitter_seconds=2.0,
        share_timeout_seconds=15.0,
        modal_timeout_seconds=10.0,
    )
    
    print("\n" + "=" * 60)
    print("OPENING AUTHENTICATED BROWSER")
    print("=" * 60)
    
    with sync_playwright() as playwright:
        try:
            # Open logged-in browser
            browser, context, page = open_logged_in_browser(
                playwright,
                state_file=DESTINATION_STATE_FILE,
            )
            
            print("✓ Browser opened with destination account session")
            
            # Create share engine
            engine = PoshmarkShareEngine(
                page=page,
                config=config,
                progress_callback=None,  # No callback for test
            )
            
            # Navigate to closet
            print("\n" + "=" * 60)
            print("NAVIGATING TO CLOSET")
            print("=" * 60)
            
            engine.open_closet()
            print("✓ Closet loaded")
            
            # Discover first listing
            listing = discover_first_listing(page)
            
            if listing is None:
                print("\nERROR: Could not discover any listings to share")
                print("Please ensure your destination closet has at least one active listing.")
                context.close()
                browser.close()
                sys.exit(1)
            
            # Attempt to share the listing
            print("\n" + "=" * 60)
            print("ATTEMPTING TO SHARE LISTING")
            print("=" * 60)
            
            result = engine.share_listing(listing)
            
            # Report results
            print("\n" + "=" * 60)
            print("SHARE RESULT")
            print("=" * 60)
            
            print(f"Success: {result.success}")
            print(f"Shared: {result.shared}")
            print(f"Failed: {result.failed}")
            print(f"Elapsed: {result.elapsed_seconds:.2f}s")
            print(f"Message: {result.message}")
            
            if result.errors:
                print("\nErrors:")
                for error in result.errors:
                    print(f"  - {error.error_type}: {error.message}")
            
            # Keep browser open for inspection
            print("\n" + "=" * 60)
            print("BROWSER INSPECTION")
            print("=" * 60)
            print("Browser will remain open for 10 seconds for inspection.")
            print("Check the browser window to verify share status.")
            
            import time
            time.sleep(10)
            
            # Cleanup
            context.close()
            browser.close()
            
            print("\n" + "=" * 60)
            print("TEST COMPLETE")
            print("=" * 60)
            
            if result.success:
                print("✓ Share test PASSED")
                sys.exit(0)
            else:
                print("✗ Share test FAILED")
                sys.exit(1)
        
        except Exception as error:
            print(f"\n✗ FATAL ERROR: {error}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
