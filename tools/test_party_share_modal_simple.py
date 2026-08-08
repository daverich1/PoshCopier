"""
TASK-027A.1 - Simplified Party Share Modal Discovery

Manually test share modal with a known listing to discover party destinations.
This bypasses eligibility checking to focus on modal structure discovery.
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
    """Test share modal with first available listing."""
    print("=" * 80)
    print("SIMPLIFIED PARTY SHARE MODAL DISCOVERY")
    print("=" * 80)
    print("\nThis will:")
    print("1. Open a listing from your closet")
    print("2. Click share button")
    print("3. Analyze party destinations in modal")
    print("\nWARNING: NO ACTUAL SHARING WILL OCCUR")
    print("")
    
    # Get listing ID to test
    listing_id = input("Enter a listing ID from your closet (or press Enter for 66e0e5e5c9e0e5c9e0e5c9e0): ").strip()
    if not listing_id:
        listing_id = "66e0e5e5c9e0e5c9e0e5c9e0"  # Default test ID
    
    listing_url = f"https://poshmark.com/listing/{listing_id}"
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser
            print("\nOpening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened")
            
            # Navigate to listing
            print(f"\nNavigating to: {listing_url}")
            page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            
            # Check if listing exists
            if "/listing/" not in page.url:
                print("[ERROR] Listing not found or redirected")
                return
            
            print("[SUCCESS] Listing loaded")
            
            # Find and click share button
            print("\nLooking for share button...")
            share_button = page.locator("div.share-v2.cursor--pointer").first
            
            if not share_button.is_visible(timeout=5000):
                print("[ERROR] Share button not visible")
                return
            
            print("[SUCCESS] Share button found")
            print("Clicking share button...")
            share_button.click()
            
            # Wait for modal
            print("\nWaiting for share modal...")
            page.wait_for_selector("[data-test='listing-share-modal-container']", timeout=10000)
            page.wait_for_timeout(2000)  # Let modal fully render
            
            print("[SUCCESS] Modal opened")
            
            # Analyze modal structure
            print("\n" + "=" * 80)
            print("ANALYZING SHARE MODAL")
            print("=" * 80)
            
            result = page.evaluate("""
                () => {
                    const modal = document.querySelector('[data-test="listing-share-modal-container"]');
                    if (!modal) return { found: false };
                    
                    // Find all clickable destinations
                    const destinations = [];
                    const clickables = modal.querySelectorAll('button, a, [role="button"]');
                    
                    for (const el of clickables) {
                        if (el.offsetParent === null) continue;  // Skip hidden
                        
                        const text = el.textContent.trim();
                        if (text.length < 3) continue;  // Skip empty
                        
                        // Check if this looks like a party destination
                        const isParty = /posh party/i.test(text) || /party/i.test(text);
                        
                        // Extract all attributes
                        const attrs = {};
                        for (const attr of el.attributes) {
                            attrs[attr.name] = attr.value;
                        }
                        
                        destinations.push({
                            text: text.substring(0, 100),
                            tag: el.tagName,
                            is_party: isParty,
                            href: el.href || null,
                            data_test: el.getAttribute('data-test'),
                            data_et_name: el.getAttribute('data-et-name'),
                            data_et_prop_party_id: el.getAttribute('data-et-prop-party_id'),
                            class: el.className,
                            outer_html: el.outerHTML.substring(0, 300),
                        });
                    }
                    
                    return {
                        found: true,
                        total_destinations: destinations.length,
                        destinations: destinations,
                    };
                }
            """)
            
            if not result.get("found"):
                print("[ERROR] Modal not found")
                return
            
            destinations = result.get("destinations", [])
            print(f"\n[SUCCESS] Found {len(destinations)} clickable destinations")
            
            # Show all destinations
            print("\n" + "-" * 80)
            print("ALL DESTINATIONS:")
            print("-" * 80)
            
            party_count = 0
            for i, dest in enumerate(destinations, 1):
                print(f"\n{i}. {dest['text']}")
                print(f"   Tag: {dest['tag']}")
                print(f"   Is Party: {dest['is_party']}")
                print(f"   data-et-name: {dest['data_et_name']}")
                print(f"   data-et-prop-party_id: {dest['data_et_prop_party_id']}")
                print(f"   href: {dest['href']}")
                
                if dest['is_party']:
                    party_count += 1
                    print(f"   >>> PARTY DESTINATION <<<")
            
            print("\n" + "=" * 80)
            print(f"SUMMARY: Found {party_count} party destinations")
            print("=" * 80)
            
            if party_count > 0:
                print("\n[SUCCESS] Party destinations are available in share modal")
                print("\nRecommended selector strategy:")
                print("  1. Check for data-et-prop-party_id attribute")
                print("  2. Match party_id from PoshParty model")
                print("  3. Fallback to text matching if party_id not available")
            else:
                print("\n[WARNING] No party destinations found")
                print("  This may mean no parties are currently live")
            
            # Keep browser open
            print("\n" + "=" * 80)
            print("Browser will remain open for inspection")
            print("Press Enter to close...")
            print("=" * 80)
            input()
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
