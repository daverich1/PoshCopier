"""
Selector discovery tool for Poshmark share functionality.

This script opens a browser to a listing page and helps discover
the correct selectors for:
1. Share button on listing page
2. "Share to My Followers" option in modal

Usage:
    python tools/test_share_discover_selectors.py

The browser will pause at key points for manual inspection.
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


def pause_for_inspection(message: str) -> None:
    """Pause and wait for user to press Enter."""
    print("\n" + "=" * 60)
    print(message)
    print("=" * 60)
    input("Press ENTER to continue...")


def discover_share_button(page) -> None:
    """Discover share button selectors."""
    print("\n" + "=" * 60)
    print("DISCOVERING SHARE BUTTON SELECTORS")
    print("=" * 60)
    
    # Try various selectors
    selectors = [
        ('Role: button[name="Share"]', 'page.get_by_role("button", name="Share")'),
        ('[aria-label*="Share"]', 'page.locator(\'[aria-label*="Share" i]\')'),
        ('[data-test*="share"]', 'page.locator(\'[data-test*="share" i]\')'),
        ('button[class*="share"]', 'page.locator(\'button[class*="share" i]\')'),
        ('button:has-text("Share")', 'page.locator(\'button:has-text("Share")\')'),
    ]
    
    print("\nTrying selectors:")
    for description, selector_code in selectors:
        print(f"\n  {description}")
        print(f"  Code: {selector_code}")
        
        try:
            if "get_by_role" in selector_code:
                locator = page.get_by_role("button", name="Share")
            else:
                selector = selector_code.split("'")[1]
                locator = page.locator(selector)
            
            count = locator.count()
            print(f"  Found: {count} element(s)")
            
            if count > 0:
                for i in range(min(count, 3)):
                    element = locator.nth(i)
                    try:
                        visible = element.is_visible()
                        text = element.inner_text() if visible else "N/A"
                        print(f"    [{i}] Visible: {visible}, Text: {text[:50]}")
                    except Exception as e:
                        print(f"    [{i}] Error: {e}")
        
        except Exception as error:
            print(f"  Error: {error}")
    
    # JavaScript inspection
    print("\n" + "-" * 60)
    print("JavaScript DOM Inspection:")
    print("-" * 60)
    
    try:
        result = page.evaluate("""
            () => {
                // Find all buttons
                const buttons = Array.from(document.querySelectorAll('button'));
                const shareButtons = buttons.filter(btn => {
                    const text = btn.textContent.toLowerCase();
                    const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const dataTest = (btn.getAttribute('data-test') || '').toLowerCase();
                    return text.includes('share') || ariaLabel.includes('share') || dataTest.includes('share');
                });
                
                return shareButtons.map(btn => ({
                    text: btn.textContent.trim(),
                    ariaLabel: btn.getAttribute('aria-label'),
                    dataTest: btn.getAttribute('data-test'),
                    className: btn.className,
                    visible: btn.offsetParent !== null,
                }));
            }
        """)
        
        if result:
            print(f"Found {len(result)} share-related button(s):")
            for i, btn in enumerate(result):
                print(f"\n  Button {i + 1}:")
                print(f"    Text: {btn['text'][:50]}")
                print(f"    aria-label: {btn['ariaLabel']}")
                print(f"    data-test: {btn['dataTest']}")
                print(f"    class: {btn['className'][:80]}")
                print(f"    Visible: {btn['visible']}")
        else:
            print("No share buttons found via JavaScript")
    
    except Exception as error:
        print(f"JavaScript inspection error: {error}")


def discover_followers_option(page) -> None:
    """Discover 'Share to My Followers' option selectors."""
    print("\n" + "=" * 60)
    print("DISCOVERING 'SHARE TO MY FOLLOWERS' SELECTORS")
    print("=" * 60)
    
    # Try various selectors
    selectors = [
        ('Role: button[name="Share to My Followers"]', 'page.get_by_role("button", name="Share to My Followers")'),
        ('text="Share to My Followers"', 'page.locator(\'text="Share to My Followers"\')'),
        ('[role="button"]:has-text("Followers")', 'page.locator(\'[role="button"]:has-text("Followers")\')'),
        ('*:has-text("followers")', 'page.locator(\'*:has-text("followers")\')'),
    ]
    
    print("\nTrying selectors:")
    for description, selector_code in selectors:
        print(f"\n  {description}")
        print(f"  Code: {selector_code}")
        
        try:
            if "get_by_role" in selector_code:
                locator = page.get_by_role("button", name="Share to My Followers")
            elif 'text=' in selector_code:
                locator = page.locator('text="Share to My Followers"')
            else:
                selector = selector_code.split("'")[1]
                locator = page.locator(selector)
            
            count = locator.count()
            print(f"  Found: {count} element(s)")
            
            if count > 0:
                for i in range(min(count, 3)):
                    element = locator.nth(i)
                    try:
                        visible = element.is_visible()
                        text = element.inner_text() if visible else "N/A"
                        print(f"    [{i}] Visible: {visible}, Text: {text[:50]}")
                    except Exception as e:
                        print(f"    [{i}] Error: {e}")
        
        except Exception as error:
            print(f"  Error: {error}")
    
    # JavaScript inspection
    print("\n" + "-" * 60)
    print("JavaScript Modal Inspection:")
    print("-" * 60)
    
    try:
        result = page.evaluate("""
            () => {
                // Find modal
                const modal = document.querySelector('[role="dialog"]');
                if (!modal) return { modal: false };
                
                // Find all clickable elements with "followers" text
                const elements = Array.from(modal.querySelectorAll('*'));
                const followerElements = elements.filter(el => {
                    const text = el.textContent.toLowerCase();
                    return text.includes('follower');
                });
                
                return {
                    modal: true,
                    elements: followerElements.slice(0, 5).map(el => ({
                        tag: el.tagName,
                        text: el.textContent.trim().substring(0, 100),
                        role: el.getAttribute('role'),
                        className: el.className,
                        clickable: el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button',
                    }))
                };
            }
        """)
        
        if result['modal']:
            print("✓ Modal found")
            if result['elements']:
                print(f"Found {len(result['elements'])} element(s) with 'follower' text:")
                for i, el in enumerate(result['elements']):
                    print(f"\n  Element {i + 1}:")
                    print(f"    Tag: {el['tag']}")
                    print(f"    Text: {el['text']}")
                    print(f"    Role: {el['role']}")
                    print(f"    Clickable: {el['clickable']}")
            else:
                print("No elements with 'follower' text found in modal")
        else:
            print("✗ No modal found")
    
    except Exception as error:
        print(f"JavaScript inspection error: {error}")


def main() -> None:
    """Main discovery function."""
    print("\n" + "=" * 60)
    print("POSHMARK SHARE SELECTOR DISCOVERY TOOL")
    print("=" * 60)
    
    # Check for destination state file
    if not DESTINATION_STATE_FILE.exists():
        print(f"\nERROR: {DESTINATION_STATE_FILE.name} not found!")
        print("Please run login.py first to save destination account session.")
        sys.exit(1)
    
    print(f"\n✓ Found {DESTINATION_STATE_FILE.name}")
    
    # Get listing URL from user
    print("\n" + "=" * 60)
    print("SETUP")
    print("=" * 60)
    print("\nEnter a listing URL from your destination closet.")
    print("Example: https://poshmark.com/listing/Nike-Air-Max-12345678901234567890abcd")
    
    listing_url = input("\nListing URL: ").strip()
    
    if not listing_url or "/listing/" not in listing_url:
        print("ERROR: Invalid listing URL")
        sys.exit(1)
    
    print(f"✓ Using listing: {listing_url}")
    
    with sync_playwright() as playwright:
        try:
            # Open logged-in browser
            print("\n" + "=" * 60)
            print("OPENING BROWSER")
            print("=" * 60)
            
            browser, context, page = open_logged_in_browser(
                playwright,
                state_file=DESTINATION_STATE_FILE,
            )
            
            print("✓ Browser opened with destination account session")
            
            # Navigate to listing
            print(f"\nNavigating to: {listing_url}")
            page.goto(listing_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            print("✓ Listing page loaded")
            
            # Discover share button
            pause_for_inspection(
                "STEP 1: Inspect the listing page in the browser.\n"
                "Look for the SHARE button and note its appearance."
            )
            
            discover_share_button(page)
            
            pause_for_inspection(
                "STEP 2: Now manually click the SHARE button in the browser.\n"
                "The share modal should appear."
            )
            
            # Discover followers option
            discover_followers_option(page)
            
            pause_for_inspection(
                "STEP 3: Review the discovered selectors above.\n"
                "The browser will close when you press ENTER."
            )
            
            # Cleanup
            context.close()
            browser.close()
            
            print("\n" + "=" * 60)
            print("DISCOVERY COMPLETE")
            print("=" * 60)
            print("\nReview the output above to identify working selectors.")
            print("Update share_engine.py if needed with discovered selectors.")
        
        except Exception as error:
            print(f"\n✗ ERROR: {error}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
