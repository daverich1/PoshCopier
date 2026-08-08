"""
TASK-027A.2 - Discover Actual Posh Party Sharing Flow

Find the real UI path to share a listing to a live Posh Party.

The closet-card share modal does NOT contain parties.
This script investigates the party page itself.
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
from party.party_manager import PartyManager
from party.eligibility import is_listing_eligible_for_party
from party.party_models import PartyEligibilityStatus, PartyType
from scraper.availability import verify_listing_availability, AvailabilityStatus
from inventory.inventory_manager import InventoryManager


def main():
    """Discover actual party sharing flow."""
    print("=" * 80)
    print("TASK-027A.2: DISCOVER ACTUAL POSH PARTY SHARING FLOW")
    print("=" * 80)
    print("\nObjective: Find how to share OUR OWN listing to a live Posh Party")
    print("")
    
    # Initialize managers
    inventory_manager = InventoryManager()
    party_manager = PartyManager()
    
    with sync_playwright() as p:
        try:
            # Open browser
            print("Opening browser with destination account...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened")
            
            # PHASE 1: LIVE PARTY SELECTION
            print("\n" + "=" * 80)
            print("PHASE 1: LIVE PARTY SELECTION")
            print("=" * 80)
            
            print("\nForce-refreshing party data from Poshmark...")
            parties = party_manager.refresh_cache(page)
            
            live_parties = party_manager.get_live_parties(parties)
            print(f"\n[INFO] Found {len(live_parties)} currently live parties")
            
            if not live_parties:
                print("[ERROR] No live parties available")
                print("Cannot proceed without a live party")
                return
            
            # Prefer UNIVERSAL party
            universal_party = None
            for party in live_parties:
                if party.party_type == PartyType.UNIVERSAL:
                    universal_party = party
                    break
            
            selected_party = universal_party if universal_party else live_parties[0]
            
            print(f"\n[SUCCESS] Selected party:")
            print(f"  Name: {selected_party.name}")
            print(f"  ID: {selected_party.party_id}")
            print(f"  URL: {selected_party.url}")
            print(f"  Type: {selected_party.party_type.value}")
            if selected_party.guidelines:
                print(f"  Brands: {selected_party.guidelines.brands_allowed}")
                print(f"  Categories: {selected_party.guidelines.categories_allowed}")
            
            # Find eligible listing
            print("\nFinding AVAILABLE + ACTIVE + ELIGIBLE listing...")
            
            # For UNIVERSAL party, any AVAILABLE listing works
            # For others, need to check eligibility
            
            # Load inventory
            items = inventory_manager.load_items()
            print(f"Loaded {len(items)} items from inventory")
            
            selected_listing = None
            eligibility_result = None
            
            for item in items[:20]:  # Check first 20
                # Load listing data
                try:
                    import json
                    with open(item.listing_path, 'r', encoding='utf-8') as f:
                        listing_data = json.load(f)
                except Exception:
                    continue
                
                # Get availability
                availability_str = listing_data.get("availability", "unknown")
                try:
                    availability = AvailabilityStatus(availability_str)
                except ValueError:
                    availability = AvailabilityStatus.UNKNOWN
                
                # Only check AVAILABLE listings
                if availability != AvailabilityStatus.AVAILABLE:
                    continue
                
                # Build listing dict for eligibility
                listing_dict = {
                    "availability": availability,
                    "brand": listing_data.get("brand", ""),
                    "department": listing_data.get("department", ""),
                    "category": listing_data.get("category", ""),
                    "subcategory": listing_data.get("subcategory", ""),
                    "size": listing_data.get("size", ""),
                }
                
                # Check eligibility
                eligibility = is_listing_eligible_for_party(listing_dict, selected_party)
                
                if eligibility.status == PartyEligibilityStatus.ELIGIBLE:
                    selected_listing = item
                    eligibility_result = eligibility
                    break
            
            if not selected_listing:
                print("[ERROR] No ELIGIBLE listing found")
                print("Cannot proceed without an eligible listing")
                return
            
            print(f"\n[SUCCESS] Selected listing:")
            print(f"  Title: {selected_listing.title}")
            print(f"  ID: {selected_listing.listing_id}")
            print(f"  Eligibility: {eligibility_result.status.value}")
            print(f"  Reason: {eligibility_result.reason}")
            
            # PHASE 2: OPEN LIVE PARTY PAGE
            print("\n" + "=" * 80)
            print("PHASE 2: OPEN LIVE PARTY PAGE")
            print("=" * 80)
            
            print(f"\nNavigating to party page: {selected_party.url}")
            page.goto(selected_party.url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            # Confirm party page
            page_title = page.title()
            page_text = page.evaluate("() => document.body.textContent")
            
            print(f"\n[INFO] Page title: {page_title}")
            print(f"[INFO] Party name in page: {selected_party.name in page_text}")
            print(f"[INFO] 'Ends in' found: {'ends in' in page_text.lower()}")
            
            # PHASE 3: DISCOVER SHARE ENTRY POINTS
            print("\n" + "=" * 80)
            print("PHASE 3: DISCOVER SHARE ENTRY POINTS")
            print("=" * 80)
            
            print("\nSearching for share/listing controls on party page...")
            
            controls = page.evaluate("""
                () => {
                    const keywords = ['share', 'listing', 'add', 'sell', 'my listings', 'closet'];
                    const found = [];
                    
                    // Search all buttons and links
                    const elements = document.querySelectorAll('button, a, [role="button"]');
                    
                    for (const el of elements) {
                        const text = (el.textContent || '').toLowerCase();
                        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                        const dataTest = el.getAttribute('data-test') || '';
                        const dataEtName = el.getAttribute('data-et-name') || '';
                        
                        // Check if element matches keywords
                        const matchesKeyword = keywords.some(kw => 
                            text.includes(kw) || ariaLabel.includes(kw) || 
                            dataTest.includes(kw) || dataEtName.includes(kw)
                        );
                        
                        if (matchesKeyword && el.offsetParent !== null) {
                            // Extract data-et-prop-* attributes
                            const etProps = {};
                            for (const attr of el.attributes) {
                                if (attr.name.startsWith('data-et-prop-')) {
                                    etProps[attr.name.replace('data-et-prop-', '')] = attr.value;
                                }
                            }
                            
                            found.push({
                                tag: el.tagName,
                                text: (el.textContent || '').trim().substring(0, 100),
                                class: el.className,
                                href: el.href || null,
                                data_test: dataTest,
                                data_testid: el.getAttribute('data-testid'),
                                data_et_name: dataEtName,
                                data_et_props: etProps,
                                aria_label: el.getAttribute('aria-label'),
                                role: el.getAttribute('role'),
                                outer_html: el.outerHTML.substring(0, 300),
                            });
                        }
                    }
                    
                    return found;
                }
            """)
            
            print(f"\n[INFO] Found {len(controls)} potential share/listing controls")
            
            if controls:
                print("\nControls found:")
                for i, ctrl in enumerate(controls, 1):
                    print(f"\n{i}. {ctrl['tag']}: {ctrl['text'][:80]}")
                    print(f"   data-et-name: {ctrl['data_et_name']}")
                    print(f"   data-test: {ctrl['data_test']}")
                    print(f"   aria-label: {ctrl['aria_label']}")
                    if ctrl['data_et_props']:
                        print(f"   data-et-props: {ctrl['data_et_props']}")
            else:
                print("\n[WARNING] No share/listing controls found on party page")
            
            # PHASE 4: CHECK OWN-LISTING INTERACTIONS
            print("\n" + "=" * 80)
            print("PHASE 4: CHECK OWN-LISTING INTERACTIONS")
            print("=" * 80)
            
            # Check if there's a way to access "My Listings" from party page
            my_listings_controls = [c for c in controls if 'my listing' in c['text'].lower() or 'closet' in c['text'].lower()]
            
            if my_listings_controls:
                print(f"\n[INFO] Found {len(my_listings_controls)} 'My Listings' related controls")
                for ctrl in my_listings_controls:
                    print(f"  - {ctrl['text'][:80]}")
            else:
                print("\n[INFO] No 'My Listings' controls found on party page")
            
            # PHASE 6: ALTERNATE FLOW - CHECK LISTING DETAIL PAGE
            print("\n" + "=" * 80)
            print("PHASE 6: ALTERNATE FLOW - LISTING DETAIL PAGE")
            print("=" * 80)
            
            listing_url = f"https://poshmark.com/listing/{selected_listing.listing_id}"
            print(f"\nNavigating to listing detail page: {listing_url}")
            page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            
            print("\nSearching for share controls on listing detail page...")
            
            listing_share_controls = page.evaluate("""
                () => {
                    const found = [];
                    const shareElements = document.querySelectorAll('[class*="share" i], [data-test*="share" i], button:has-text("Share"), a:has-text("Share")');
                    
                    for (const el of shareElements) {
                        if (el.offsetParent === null) continue;
                        
                        found.push({
                            tag: el.tagName,
                            text: (el.textContent || '').trim().substring(0, 100),
                            class: el.className,
                            data_test: el.getAttribute('data-test'),
                            data_et_name: el.getAttribute('data-et-name'),
                            outer_html: el.outerHTML.substring(0, 200),
                        });
                    }
                    
                    return found;
                }
            """)
            
            print(f"\n[INFO] Found {len(listing_share_controls)} share controls on listing detail page")
            
            if listing_share_controls:
                for i, ctrl in enumerate(listing_share_controls, 1):
                    print(f"\n{i}. {ctrl['tag']}: {ctrl['text'][:80]}")
                    print(f"   class: {ctrl['class'][:80]}")
                    print(f"   data-et-name: {ctrl['data_et_name']}")
            
            # PHASE 7: OUTPUT
            print("\n" + "=" * 80)
            print("DISCOVERY SUMMARY")
            print("=" * 80)
            
            print(f"\n1. Live party tested: {selected_party.name}")
            print(f"2. Listing tested: {selected_listing.title}")
            print(f"3. Eligibility: {eligibility_result.status.value} - {eligibility_result.reason}")
            print(f"4. Party-page share controls: {len(controls)} found")
            print(f"5. My Listings UI: {'YES' if my_listings_controls else 'NO'}")
            print(f"6. Listing-page share controls: {len(listing_share_controls)} found")
            
            print(f"\n7. Party sharing appears to be:")
            if my_listings_controls:
                print(f"   - Possibly party-page initiated (My Listings controls found)")
            elif listing_share_controls:
                print(f"   - Possibly listing-page initiated (share controls on listing)")
            else:
                print(f"   - UNKNOWN (no obvious controls found)")
            
            print(f"\n8. Recommended next steps:")
            print(f"   - Manual testing during live party hours")
            print(f"   - Check mobile app for comparison")
            print(f"   - Review Poshmark documentation")
            
            print("\n" + "=" * 80)
            print("Discovery complete - browser remains open for inspection")
            print("=" * 80)
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
