"""
TASK-027A.1 - Corrected Party Share Modal Discovery

Correct workflow:
1. Open closet page
2. Find listing cards
3. Verify availability by checking listing detail page
4. Return to closet and click share button ON THE CARD
5. Analyze party destinations in modal
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE
from scraper.availability import verify_listing_availability, AvailabilityStatus


def main():
    """Correct discovery workflow using closet cards."""
    print("=" * 80)
    print("CORRECTED PARTY SHARE MODAL DISCOVERY")
    print("=" * 80)
    print("\nCorrect workflow:")
    print("1. Open closet page")
    print("2. Find listing cards")
    print("3. Verify availability on listing detail page")
    print("4. Return to closet and click share button ON CARD")
    print("5. Analyze party destinations in modal")
    print("\nWARNING: NO ACTUAL SHARING WILL OCCUR")
    print("")
    
    # Load config to show source vs destination
    import json
    config_file = PROJECT_DIR / "config.json"
    source_closet = "unknown"
    
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
            source_closet = config.get("source_closet_url", "unknown")
        except Exception:
            pass
    
    # Destination closet for sharing (from test_share_single.py pattern)
    destination_closet = "https://poshmark.com/closet/dveshop"
    
    print(f"\nCloset Configuration:")
    print(f"  Source closet: {source_closet}")
    print(f"  Destination closet: {destination_closet}")
    print(f"  Sharing closet selected: {destination_closet}")
    print("")
    
    closet_url = destination_closet
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser (use DESTINATION state for destination closet)
            print("Opening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened with destination account")
            
            # Navigate to closet
            print(f"\nNavigating to closet: {closet_url}")
            page.goto(closet_url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait for page to fully load (match diagnostic script timing)
            print("  Waiting for page to load...")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)  # Initial wait
            
            # Scroll to trigger lazy loading (match diagnostic script)
            print("  Scrolling to trigger lazy loading...")
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)  # Wait for content to load
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(1000)  # Wait after scroll back
            
            print("[SUCCESS] Closet loaded")
            
            # Collect listing URLs from closet cards
            print("\nCollecting listing URLs from closet cards...")
            
            listing_data = page.evaluate("""
                () => {
                    // Use the exact working pattern from diagnostic script
                    const allLinks = Array.from(document.querySelectorAll('a'));
                    const listingLinks = allLinks
                        .map(a => a.href)
                        .filter(h => h && h.includes('/listing/'));
                    
                    // Deduplicate
                    const unique = [...new Set(listingLinks)];
                    
                    // Extract listing IDs - use URL parsing
                    const listings = unique.map(url => {
                        try {
                            const urlObj = new URL(url);
                            const pathParts = urlObj.pathname.split('/');
                            const listingIndex = pathParts.indexOf('listing');
                            if (listingIndex >= 0 && listingIndex < pathParts.length - 1) {
                                const listingId = pathParts[listingIndex + 1];
                                return { url: url, listing_id: listingId };
                            }
                        } catch (e) {}
                        return { url: url, listing_id: null };
                    }).filter(item => item.listing_id);
                    
                    // Debug info
                    return {
                        listings: listings,
                        debug: {
                            total_links: allLinks.length,
                            listing_links: listingLinks.length,
                            unique_listings: unique.length,
                        }
                    };
                }
            """)
            
            debug = listing_data.get('debug', {})
            listings = listing_data.get('listings', [])
            
            print(f"[DEBUG] Total <a> tags: {debug.get('total_links', 0)}")
            print(f"[DEBUG] Links with '/listing/': {debug.get('listing_links', 0)}")
            print(f"[DEBUG] Unique listing URLs: {debug.get('unique_listings', 0)}")
            print(f"[SUCCESS] Found {len(listings)} unique listings")
            
            listing_data = listings
            
            if not listing_data:
                print("[ERROR] No listings found in closet")
                return
            
            # Check availability for each listing with HARD GATE
            print("\nChecking availability with HARD GATE...")
            print("Only AVAILABLE + ACTIVE listings will be accepted")
            available_listing = None
            
            for i, listing in enumerate(listing_data[:10], 1):  # Check first 10
                print(f"\n  {i}. Listing: {listing['listing_id']}")
                print(f"     URL: {listing['url']}")
                
                # Navigate to listing detail page
                page.goto(listing['url'], wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                
                # HARD AVAILABILITY GATE - use existing scraper/availability.py
                try:
                    result = verify_listing_availability(page)
                    
                    print(f"     Availability: {result.status.value}")
                    print(f"     Available: {result.available}")
                    
                    # HARD GATE: Only AVAILABLE status is accepted
                    if result.status == AvailabilityStatus.AVAILABLE and result.available:
                        print(f"     Decision: ACCEPT - listing is AVAILABLE and active")
                        available_listing = listing
                        break
                    elif result.status == AvailabilityStatus.UNKNOWN:
                        print(f"     Decision: SKIP - UNKNOWN status (never share)")
                    elif not result.available:
                        print(f"     Decision: SKIP - not available for sale")
                    else:
                        print(f"     Decision: SKIP - status is {result.status.value}")
                        
                except Exception as e:
                    print(f"     [ERROR] Could not check availability: {e}")
                    print(f"     Decision: SKIP - availability check failed")
                    continue
            
            if not available_listing:
                print("\n[ERROR] No AVAILABLE listings found in first 10")
                print("  Try running scraper to refresh inventory")
                return
            
            print(f"\n[SUCCESS] Using listing: {available_listing['listing_id']}")
            print(f"  URL: {available_listing['url']}")
            
            # Return to closet page
            print(f"\nReturning to closet page...")
            page.goto(closet_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            print("[SUCCESS] Back on closet page")
            
            # Find the specific card for this listing
            print(f"\nLocating card for listing {available_listing['listing_id']}...")
            
            card_found = page.evaluate(f"""
                (listingUrl) => {{
                    const cards = document.querySelectorAll('a[href*="/listing/"]');
                    
                    for (const card of cards) {{
                        if (card.href === listingUrl) {{
                            // Found the card, now find share button within its container
                            let container = card;
                            
                            // Walk up to find card container
                            while (container && container !== document.body) {{
                                container = container.parentElement;
                                if (!container) break;
                                
                                // Look for share button in this container
                                const shareBtn = container.querySelector('div.share-v2.cursor--pointer');
                                if (shareBtn) {{
                                    // Mark it for easy finding
                                    shareBtn.setAttribute('data-discovery-target', 'true');
                                    return true;
                                }}
                            }}
                        }}
                    }}
                    
                    return false;
                }}
            """, available_listing['url'])
            
            if not card_found:
                print("[ERROR] Could not find share button on card")
                return
            
            print("[SUCCESS] Found share button on card")
            
            # Click the share button
            print("\nClicking share button...")
            share_button = page.locator('[data-discovery-target="true"]').first
            share_button.click()
            
            # Wait for modal
            print("\nWaiting for share modal...")
            page.wait_for_selector("[data-test='listing-share-modal-container']", timeout=10000)
            page.wait_for_timeout(2000)  # Let modal fully render
            
            print("[SUCCESS] Modal opened")
            
            # Analyze modal structure
            print("\n" + "=" * 80)
            print("ANALYZING SHARE MODAL - PARTY DESTINATIONS")
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
                        
                        // Extract ALL data-et-prop-* attributes
                        const etProps = {};
                        for (const attr of el.attributes) {
                            if (attr.name.startsWith('data-et-prop-')) {
                                const propName = attr.name.replace('data-et-prop-', '');
                                etProps[propName] = attr.value;
                            }
                        }
                        
                        destinations.push({
                            text: text.substring(0, 150),
                            tag: el.tagName,
                            is_party: isParty,
                            href: el.href || null,
                            data_test: el.getAttribute('data-test'),
                            data_testid: el.getAttribute('data-testid'),
                            data_et_name: el.getAttribute('data-et-name'),
                            data_et_props: etProps,
                            aria_label: el.getAttribute('aria-label'),
                            aria_disabled: el.getAttribute('aria-disabled'),
                            role: el.getAttribute('role'),
                            class: el.className,
                            disabled: el.disabled || el.getAttribute('disabled') !== null,
                            outer_html: el.outerHTML.substring(0, 400),
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
            
            # Show ALL destinations for complete analysis
            print("\n" + "-" * 80)
            print(f"ALL {len(destinations)} DESTINATIONS:")
            print("-" * 80)
            for i, dest in enumerate(destinations, 1):
                print(f"\n{i}. Text: {dest['text'][:80]}")
                print(f"   data-et-name: {dest['data_et_name']}")
                print(f"   Is Party: {dest['is_party']}")
                
                # Flag Posh Shows Host
                if "posh show" in dest['text'].lower():
                    print(f"   >>> POSH SHOWS HOST (do not click) <<<")
            
            # Filter and show party destinations
            party_destinations = [d for d in destinations if d['is_party']]
            
            print("\n" + "-" * 80)
            print(f"PARTY DESTINATIONS: {len(party_destinations)} found")
            print("-" * 80)
            
            for i, dest in enumerate(party_destinations, 1):
                print(f"\n{'=' * 80}")
                print(f"PARTY DESTINATION #{i}")
                print('=' * 80)
                print(f"\nVisible Text: {dest['text']}")
                print(f"Tag: {dest['tag']}")
                print(f"Class: {dest['class']}")
                print(f"Href: {dest['href']}")
                print(f"\nAttributes:")
                print(f"  data-test: {dest['data_test']}")
                print(f"  data-testid: {dest['data_testid']}")
                print(f"  data-et-name: {dest['data_et_name']}")
                print(f"  aria-label: {dest['aria_label']}")
                print(f"  aria-disabled: {dest['aria_disabled']}")
                print(f"  role: {dest['role']}")
                print(f"  disabled: {dest['disabled']}")
                
                print(f"\ndata-et-prop-* attributes:")
                if dest['data_et_props']:
                    for key, value in dest['data_et_props'].items():
                        print(f"  {key}: {value}")
                        
                        # Check if this contains a party ID
                        if 'party' in key.lower() and value:
                            print(f"    >>> PARTY ID FOUND: {value} <<<")
                else:
                    print(f"  (none)")
                
                print(f"\nouterHTML (first 400 chars):")
                print(f"  {dest['outer_html']}")
            
            # Summary
            print("\n" + "=" * 80)
            print("DISCOVERY SUMMARY")
            print("=" * 80)
            
            print(f"\nTotal destinations: {len(destinations)}")
            print(f"Party destinations: {len(party_destinations)}")
            
            if party_destinations:
                # Check if party_id is available
                has_party_id = any(
                    'party_id' in dest['data_et_props'] or
                    'party' in str(dest['data_et_props']).lower()
                    for dest in party_destinations
                )
                
                print(f"\nParty ID in DOM: {'YES' if has_party_id else 'NO'}")
                
                if has_party_id:
                    print("\n[SUCCESS] Recommended Strategy:")
                    print("  1. Match by data-et-prop-party_id attribute")
                    print("  2. Fallback to text matching")
                else:
                    print("\n[WARNING] Recommended Strategy:")
                    print("  1. Match by party name text only")
                    print("  2. Risk: Party name changes could break matching")
            
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
