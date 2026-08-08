"""
TASK-027A.1A - Diagnose dveshop Closet Loading

Investigate why listing discovery is returning 0 results when previous
tests successfully found listings in dveshop.
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


def main():
    """Diagnose dveshop closet loading and listing discovery."""
    print("=" * 80)
    print("DVESHOP CLOSET DIAGNOSTIC")
    print("=" * 80)
    
    closet_url = "https://poshmark.com/closet/dveshop"
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser
            print("\n1. Opening browser with DESTINATION_STATE_FILE...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("   [SUCCESS] Browser opened")
            
            # Navigate to closet
            print(f"\n2. Navigating to: {closet_url}")
            page.goto(closet_url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for page to stabilize
            print("   Waiting for page to load...")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)  # Wait for dynamic content
            
            # Check page state
            print("\n3. Page State Analysis:")
            print(f"   Final URL: {page.url}")
            print(f"   Title: {page.title()}")
            
            # Check for login redirect
            if "/login" in page.url or "/signin" in page.url:
                print("   [ERROR] Redirected to login - session expired")
                return
            
            # Check if page contains dveshop
            page_text = page.evaluate("() => document.body.textContent")
            contains_dveshop = "dveshop" in page_text.lower()
            print(f"   Contains 'dveshop': {contains_dveshop}")
            
            # Show first 1000 chars of visible text
            print(f"\n   First 1000 chars of page text:")
            print(f"   {page_text[:1000]}")
            
            # Scroll the page to trigger lazy loading
            print("\n4. Scrolling page to trigger lazy loading...")
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)
            
            # Count listings with multiple selectors
            print("\n5. Counting listings with different selectors:")
            
            counts = page.evaluate("""
                () => {
                    return {
                        selector1: document.querySelectorAll('a[href*="/listing/"]').length,
                        selector2: document.querySelectorAll('a[href^="/listing/"]').length,
                        selector3: document.querySelectorAll('[href*="poshmark.com/listing/"]').length,
                        all_links: document.querySelectorAll('a').length,
                    };
                }
            """)
            
            print(f"   a[href*='/listing/']: {counts['selector1']}")
            print(f"   a[href^='/listing/']: {counts['selector2']}")
            print(f"   [href*='poshmark.com/listing/']: {counts['selector3']}")
            print(f"   Total <a> tags: {counts['all_links']}")
            
            # Get actual listing URLs
            print("\n6. Extracting listing URLs with JavaScript:")
            
            listing_urls = page.evaluate("""
                () => {
                    const allLinks = Array.from(document.querySelectorAll('a'));
                    const listingLinks = allLinks
                        .map(a => a.href)
                        .filter(h => h && h.includes('/listing/'));
                    
                    // Deduplicate
                    const unique = [...new Set(listingLinks)];
                    
                    return {
                        total: unique.length,
                        first_10: unique.slice(0, 10),
                    };
                }
            """)
            
            print(f"   Total unique listing URLs: {listing_urls['total']}")
            print(f"   First 10 URLs:")
            for i, url in enumerate(listing_urls['first_10'], 1):
                print(f"     {i}. {url}")
            
            # Check for test_share_discover_selectors.py pattern
            print("\n7. Checking test_share_discover_selectors.py pattern:")
            
            # Try the pattern from working tests
            tile_count = page.evaluate("""
                () => {
                    const tiles = document.querySelectorAll('[data-test="tile"]');
                    const cards = document.querySelectorAll('.card');
                    const items = document.querySelectorAll('[class*="item"]');
                    
                    return {
                        tiles: tiles.length,
                        cards: cards.length,
                        items: items.length,
                    };
                }
            """)
            
            print(f"   [data-test='tile']: {tile_count['tiles']}")
            print(f"   .card: {tile_count['cards']}")
            print(f"   [class*='item']: {tile_count['items']}")
            
            # Verify account identity
            print("\n8. Verifying account identity:")
            
            account_info = page.evaluate("""
                () => {
                    // Look for username in page
                    const bodyText = document.body.textContent || '';
                    const hasDveshop = bodyText.toLowerCase().includes('dveshop');
                    
                    // Look for profile/account indicators
                    const profileLinks = document.querySelectorAll('a[href*="/closet/"]');
                    const closetUrls = Array.from(profileLinks)
                        .map(a => a.href)
                        .filter(h => h.includes('/closet/'));
                    
                    return {
                        has_dveshop: hasDveshop,
                        closet_urls: closetUrls.slice(0, 5),
                    };
                }
            """)
            
            print(f"   Page contains 'dveshop': {account_info['has_dveshop']}")
            print(f"   Closet URLs found: {account_info['closet_urls']}")
            
            # Final diagnosis
            print("\n" + "=" * 80)
            print("DIAGNOSIS SUMMARY")
            print("=" * 80)
            
            if listing_urls['total'] == 0:
                print("\n[ERROR] Zero listings found after all checks")
                print("\nPossible causes:")
                print("  1. Closet is genuinely empty")
                print("  2. Page structure has changed")
                print("  3. Content is lazy-loaded and not triggering")
                print("  4. Session/authentication issue")
                
                # Take screenshot
                print("\nTaking screenshot for analysis...")
                screenshot_path = PROJECT_DIR / "logs" / "dveshop_diagnostic.png"
                screenshot_path.parent.mkdir(exist_ok=True)
                page.screenshot(path=str(screenshot_path))
                print(f"  Screenshot saved: {screenshot_path}")
                
                # Save HTML
                print("\nSaving page HTML...")
                html_path = PROJECT_DIR / "logs" / "dveshop_diagnostic.html"
                html = page.content()
                html_path.write_text(html, encoding='utf-8')
                print(f"  HTML saved: {html_path}")
                
            else:
                print(f"\n[SUCCESS] Found {listing_urls['total']} listings")
                print("\nThe selector is working correctly.")
                print("Previous '0 listings' result was likely a timing/loading issue.")
            
            # Keep browser open
            print("\n" + "=" * 80)
            print("Browser will remain open for manual inspection")
            print("Press Enter to close...")
            print("=" * 80)
            input()
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
