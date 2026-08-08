"""
TASK-027A.1 - Live Party Share Destination Discovery

Discover how party destinations appear in the share modal and determine
the best strategy for matching PoshParty.party_id to modal destinations.

Requirements:
1. Use ONE AVAILABLE listing eligible for live party
2. Open share modal
3. Enumerate all share destinations
4. Capture party destination DOM details
5. Determine best selector strategy
6. DO NOT click or share anything

Critical: This is discovery only - no actual sharing.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright, Page

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE
from inventory.inventory_manager import InventoryManager
from party.party_manager import PartyManager
from party.eligibility import is_listing_eligible_for_party
from party.party_models import PartyEligibilityStatus
from scraper.availability import AvailabilityStatus


def find_eligible_listing(inventory_manager: InventoryManager, party_manager: PartyManager, page: Page):
    """
    Find ONE AVAILABLE listing that is eligible for a currently live party.
    
    Returns:
        tuple: (listing_item, party, eligibility_result) or (None, None, None)
    """
    print("\n" + "=" * 80)
    print("STEP 1: Finding Eligible Listing")
    print("=" * 80)
    
    # Load inventory
    print("\nLoading inventory...")
    items = inventory_manager.load_items()
    print(f"Found {len(items)} items in inventory")
    
    # FORCE LIVE REFRESH - Do not use cached test data
    print("\n" + "=" * 80)
    print("FORCING LIVE PARTY REFRESH FROM POSHMARK")
    print("=" * 80)
    print("\nNavigating to https://poshmark.com/parties...")
    
    # Refresh party cache from live Poshmark data
    refreshed_parties = party_manager.refresh_cache(page)
    print(f"\n[SUCCESS] Refreshed {len(refreshed_parties)} parties from Poshmark")
    
    # Verify parties have real Poshmark data
    print("\nVerifying party data...")
    for party in refreshed_parties:
        print(f"\n  Party: {party.name}")
        print(f"    ID: {party.party_id}")
        print(f"    URL: {party.url}")
        print(f"    Is Live: {party.is_live}")
        print(f"    Type: {party.party_type.value}")
        
        # Verify URL format
        if not party.url.startswith("https://poshmark.com/party/"):
            print(f"    [WARNING] Invalid URL format: {party.url}")
        
        # Verify party_id is not a placeholder
        if party.party_id in ["designer-handbags", "campus-debut", "test-party"]:
            print(f"    [WARNING] Placeholder party_id detected: {party.party_id}")
        
        if party.guidelines:
            print(f"    Brands: {party.guidelines.brands_allowed}")
            print(f"    Categories: {party.guidelines.categories_allowed}")
            print(f"    Parse Confidence: {party.guidelines.parse_confidence.value}")
    
    # Get live parties
    live_parties = party_manager.get_live_parties(refreshed_parties)
    print(f"\n[INFO] Found {len(live_parties)} currently live parties")
    
    if not live_parties:
        print("\n[ERROR] No live parties available")
        print("  This may be normal if no parties are currently happening.")
        return None, None, None
    
    # Show live parties
    print("\n" + "=" * 80)
    print("LIVE PARTIES (Currently Happening)")
    print("=" * 80)
    for party in live_parties:
        print(f"\n  - {party.name}")
        print(f"    ID: {party.party_id}")
        print(f"    URL: {party.url}")
        print(f"    Type: {party.party_type.value}")
        if party.guidelines:
            print(f"    Brands: {party.guidelines.brands_allowed}")
            print(f"    Categories: {party.guidelines.categories_allowed}")
    
    # Try to find eligible listing
    print("\n" + "-" * 80)
    print("Checking listings for eligibility...")
    print("-" * 80)
    
    for item in items:
        # Load full listing data from listing.json
        listing_file = item.listing_path
        
        try:
            with open(listing_file, 'r', encoding='utf-8') as f:
                listing_data = json.load(f)
        except Exception as e:
            print(f"\nSkipping {item.title}: Could not load listing.json - {e}")
            continue
        
        # Get availability
        availability_str = listing_data.get("availability", "unknown")
        try:
            availability = AvailabilityStatus(availability_str)
        except ValueError:
            availability = AvailabilityStatus.UNKNOWN
        
        # Only check available listings
        if availability != AvailabilityStatus.AVAILABLE:
            continue
        
        print(f"\nChecking: {item.title}")
        print(f"  Listing ID: {item.listing_id}")
        print(f"  Availability: {availability.value}")
        print(f"  Brand: {listing_data.get('brand', '')}")
        print(f"  Department: {listing_data.get('department', '')}")
        print(f"  Category: {listing_data.get('category', '')}")
        
        # Build listing dict for eligibility check
        listing_dict = {
            "availability": availability,
            "brand": listing_data.get("brand", ""),
            "department": listing_data.get("department", ""),
            "category": listing_data.get("category", ""),
            "subcategory": listing_data.get("subcategory", ""),
            "size": listing_data.get("size", ""),
        }
        
        # Check against each live party
        for party in live_parties:
            eligibility = is_listing_eligible_for_party(listing_dict, party)
            
            print(f"  Party: {party.name}")
            print(f"    Eligibility: {eligibility.status.value}")
            print(f"    Reason: {eligibility.reason}")
            
            if eligibility.status == PartyEligibilityStatus.ELIGIBLE:
                print(f"\n[SUCCESS] Found eligible listing!")
                print(f"   Listing: {item.title}")
                print(f"   Party: {party.name}")
                return item, party, eligibility
    
    print("\n[ERROR] No eligible listings found")
    return None, None, None


def open_share_modal(page: Page, listing_url: str):
    """
    Navigate to listing and open share modal.
    
    Returns:
        bool: True if modal opened successfully
    """
    print("\n" + "=" * 80)
    print("STEP 2: Opening Share Modal")
    print("=" * 80)
    
    # Navigate to listing
    print(f"\nNavigating to: {listing_url}")
    page.goto(listing_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    
    # Find and click share button (closet card share control)
    print("\nLooking for share button: div.share-v2.cursor--pointer")
    
    try:
        share_button = page.locator("div.share-v2.cursor--pointer").first
        
        if not share_button.is_visible(timeout=5000):
            print("[ERROR] Share button not visible")
            return False
        
        print("[SUCCESS] Share button found")
        print("Clicking share button...")
        share_button.click()
        
        # Wait for modal
        print("\nWaiting for modal: [data-test='listing-share-modal-container']")
        page.wait_for_selector("[data-test='listing-share-modal-container']", timeout=10000)
        page.wait_for_timeout(1500)  # Let modal fully render
        
        print("[SUCCESS] Modal opened successfully")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to open modal: {e}")
        return False


def enumerate_share_destinations(page: Page):
    """
    Enumerate all share destinations in the modal.
    
    Returns:
        list: List of destination data dicts
    """
    print("\n" + "=" * 80)
    print("STEP 3: Enumerating Share Destinations")
    print("=" * 80)
    
    result = page.evaluate("""
        () => {
            // Find modal container
            const modal = document.querySelector('[data-test="listing-share-modal-container"]');
            
            if (!modal) {
                return { found: false, error: "Modal not found" };
            }
            
            // Find all clickable share destinations
            // Try multiple strategies
            const destinations = [];
            
            // Strategy 1: Find all buttons/links in modal
            const clickables = modal.querySelectorAll('button, a, [role="button"], [class*="share"]');
            
            for (const el of clickables) {
                // Skip if not visible
                if (el.offsetParent === null) continue;
                
                const text = el.textContent.trim();
                
                // Skip empty or very short text
                if (text.length < 3) continue;
                
                // Extract all attributes
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }
                
                // Extract data-et-prop-* attributes
                const etProps = {};
                for (const attr of el.attributes) {
                    if (attr.name.startsWith('data-et-prop-')) {
                        const propName = attr.name.replace('data-et-prop-', '');
                        etProps[propName] = attr.value;
                    }
                }
                
                destinations.push({
                    tag: el.tagName,
                    text: text,
                    class: el.className,
                    href: el.href || null,
                    data_test: el.getAttribute('data-test'),
                    data_testid: el.getAttribute('data-testid'),
                    data_et_name: el.getAttribute('data-et-name'),
                    data_et_props: etProps,
                    aria_label: el.getAttribute('aria-label'),
                    role: el.getAttribute('role'),
                    disabled: el.disabled || el.getAttribute('disabled') !== null,
                    clickable: el.offsetParent !== null,
                    outer_html: el.outerHTML.substring(0, 500),  // First 500 chars
                });
            }
            
            return {
                found: true,
                destination_count: destinations.length,
                destinations: destinations,
            };
        }
    """)
    
    if not result.get("found"):
        print(f"[ERROR] {result.get('error', 'Unknown error')}")
        return []
    
    destinations = result.get("destinations", [])
    print(f"\n[SUCCESS] Found {len(destinations)} potential share destinations")
    
    return destinations


def analyze_party_destination(destinations: list, party_name: str, party_id: str):
    """
    Identify and analyze the party destination.
    
    Returns:
        dict: Analysis results
    """
    print("\n" + "=" * 80)
    print("STEP 4: Analyzing Party Destination")
    print("=" * 80)
    
    print(f"\nLooking for party: {party_name}")
    print(f"Party ID: {party_id}")
    
    # Find party destination by text match
    party_dest = None
    
    for dest in destinations:
        text = dest.get("text", "").lower()
        
        # Check if text contains party name (partial match)
        if party_name.lower() in text or "posh party" in text:
            party_dest = dest
            break
    
    if not party_dest:
        print("\n[ERROR] Party destination not found in modal")
        print("\nAll destinations:")
        for i, dest in enumerate(destinations, 1):
            print(f"\n  Destination {i}:")
            print(f"    Text: {dest.get('text', '')[:100]}")
            print(f"    Tag: {dest.get('tag')}")
            print(f"    data-et-name: {dest.get('data_et_name')}")
        return None
    
    print("\n[SUCCESS] Party destination found!")
    print("\n" + "-" * 80)
    print("PARTY DESTINATION DETAILS")
    print("-" * 80)
    
    print(f"\nTag: {party_dest.get('tag')}")
    print(f"Visible Text: {party_dest.get('text')}")
    print(f"Class: {party_dest.get('class')}")
    print(f"Href: {party_dest.get('href')}")
    print(f"data-test: {party_dest.get('data_test')}")
    print(f"data-testid: {party_dest.get('data_testid')}")
    print(f"data-et-name: {party_dest.get('data_et_name')}")
    print(f"aria-label: {party_dest.get('aria_label')}")
    print(f"role: {party_dest.get('role')}")
    print(f"Disabled: {party_dest.get('disabled')}")
    print(f"Clickable: {party_dest.get('clickable')}")
    
    print(f"\ndata-et-prop-* attributes:")
    et_props = party_dest.get('data_et_props', {})
    for key, value in et_props.items():
        print(f"  {key}: {value}")
    
    print(f"\nouterHTML (first 500 chars):")
    print(party_dest.get('outer_html', ''))
    
    # Check if party_id appears anywhere
    print("\n" + "-" * 80)
    print("PARTY ID ANALYSIS")
    print("-" * 80)
    
    party_id_found = False
    party_id_locations = []
    
    # Check in various attributes
    for attr_name, attr_value in [
        ("href", party_dest.get("href")),
        ("data-test", party_dest.get("data_test")),
        ("data-testid", party_dest.get("data_testid")),
        ("data-et-name", party_dest.get("data_et_name")),
        ("class", party_dest.get("class")),
        ("outer_html", party_dest.get("outer_html")),
    ]:
        if attr_value and party_id in str(attr_value):
            party_id_found = True
            party_id_locations.append(attr_name)
    
    # Check in data-et-prop-* attributes
    for key, value in et_props.items():
        if party_id in str(value):
            party_id_found = True
            party_id_locations.append(f"data-et-prop-{key}")
    
    if party_id_found:
        print(f"[SUCCESS] Party ID '{party_id}' found in:")
        for loc in party_id_locations:
            print(f"   - {loc}")
    else:
        print(f"[ERROR] Party ID '{party_id}' NOT found in destination DOM")
        print("   Will need to match by party name text")
    
    # Determine best selector
    print("\n" + "-" * 80)
    print("RECOMMENDED SELECTOR STRATEGY")
    print("-" * 80)
    
    selectors = []
    
    if party_dest.get("data_test"):
        selectors.append(f"[data-test='{party_dest.get('data_test')}']")
    
    if party_dest.get("data_testid"):
        selectors.append(f"[data-testid='{party_dest.get('data_testid')}']")
    
    if party_dest.get("data_et_name"):
        selectors.append(f"[data-et-name='{party_dest.get('data_et_name')}']")
    
    if party_dest.get("href") and party_id in str(party_dest.get("href")):
        selectors.append(f"[href*='{party_id}']")
    
    # Fallback: text-based selector
    selectors.append(f"text='{party_dest.get('text')}'")
    
    print("\nRecommended selectors (in priority order):")
    for i, sel in enumerate(selectors, 1):
        print(f"  {i}. {sel}")
    
    # Analysis summary
    analysis = {
        "party_destination": party_dest,
        "party_id_found": party_id_found,
        "party_id_locations": party_id_locations,
        "recommended_selectors": selectors,
        "all_destinations": destinations,
    }
    
    return analysis


def generate_report(analysis: dict, party_name: str, party_id: str):
    """Generate final discovery report."""
    print("\n" + "=" * 80)
    print("DISCOVERY REPORT")
    print("=" * 80)
    
    if not analysis:
        print("\n[ERROR] Analysis failed - no party destination found")
        return
    
    party_dest = analysis.get("party_destination")
    all_dests = analysis.get("all_destinations", [])
    
    print(f"\n1. PARTY DESTINATION DOM")
    print(f"   Tag: {party_dest.get('tag')}")
    print(f"   Text: {party_dest.get('text')}")
    print(f"   data-et-name: {party_dest.get('data_et_name')}")
    print(f"   Clickable: {party_dest.get('clickable')}")
    
    print(f"\n2. RECOMMENDED SELECTOR")
    selectors = analysis.get("recommended_selectors", [])
    if selectors:
        print(f"   Primary: {selectors[0]}")
        if len(selectors) > 1:
            print(f"   Fallback: {selectors[1]}")
    
    print(f"\n3. PARTY ID AVAILABILITY")
    if analysis.get("party_id_found"):
        print(f"   [SUCCESS] Party ID '{party_id}' is available in DOM")
        print(f"   Locations: {', '.join(analysis.get('party_id_locations', []))}")
    else:
        print(f"   [ERROR] Party ID '{party_id}' NOT available in DOM")
        print(f"   Must match by party name text")
    
    print(f"\n4. PARTY NAME EXTRACTION")
    print(f"   Visible text: {party_dest.get('text')}")
    print(f"   Method: Direct text content")
    
    print(f"\n5. MULTIPLE PARTY DESTINATIONS")
    party_count = sum(1 for d in all_dests if "posh party" in d.get("text", "").lower())
    print(f"   Found {party_count} party-related destinations")
    if party_count > 1:
        print(f"   [WARNING] Multiple parties may appear simultaneously")
    else:
        print(f"   [SUCCESS] Only one party destination visible")
    
    print(f"\n6. INELIGIBLE PARTIES")
    print(f"   Analysis: Check if all live parties appear or only eligible ones")
    print(f"   Total destinations: {len(all_dests)}")
    
    print(f"\n7. DESTINATION STATE")
    print(f"   Disabled: {party_dest.get('disabled')}")
    print(f"   Clickable: {party_dest.get('clickable')}")
    
    print(f"\n8. RECOMMENDED PRODUCTION STRATEGY")
    if analysis.get("party_id_found"):
        print(f"   [SUCCESS] Match by party_id in href/data attributes")
        print(f"   Fallback: Match by party name text")
    else:
        print(f"   [WARNING] Match by party name text only")
        print(f"   Risk: Party name changes could break matching")
    
    print("\n" + "=" * 80)
    print("DISCOVERY COMPLETE")
    print("=" * 80)
    print("\n[SUCCESS] Ready for production implementation")
    print("   Wait for approval before modifying share_engine.py")


def main():
    """Main discovery workflow."""
    print("=" * 80)
    print("TASK-027A.1: Live Party Share Destination Discovery")
    print("=" * 80)
    print("\nThis script will:")
    print("1. Find ONE AVAILABLE listing eligible for live party")
    print("2. Open share modal")
    print("3. Enumerate share destinations")
    print("4. Analyze party destination DOM")
    print("5. Determine best selector strategy")
    print("\nWARNING: NO ACTUAL SHARING WILL OCCUR")
    print("")
    
    # Initialize managers
    inventory_manager = InventoryManager()
    party_manager = PartyManager()
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser (destination account)
            print("\nOpening logged-in browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened with saved session")
            
            # Find eligible listing
            listing, party, eligibility = find_eligible_listing(
                inventory_manager,
                party_manager,
                page
            )
            
            if not listing or not party:
                print("\n[ERROR] Could not find eligible listing")
                print("   Please ensure:")
                print("   - At least one party is currently live")
                print("   - Party cache has been loaded")
                print("   - At least one listing is AVAILABLE and eligible")
                return
            
            # Build listing URL
            listing_url = f"https://poshmark.com/listing/{listing.listing_id}"
            
            # Open share modal
            if not open_share_modal(page, listing_url):
                print("\n[ERROR] Failed to open share modal")
                return
            
            # Enumerate destinations
            destinations = enumerate_share_destinations(page)
            
            if not destinations:
                print("\n[ERROR] No share destinations found")
                return
            
            # Analyze party destination
            analysis = analyze_party_destination(
                destinations,
                party.name,
                party.party_id
            )
            
            # Generate report
            generate_report(analysis, party.name, party.party_id)
            
            # Keep browser open for manual inspection
            print("\n" + "=" * 80)
            print("Browser will remain open for manual inspection")
            print("Press Enter to close...")
            print("=" * 80)
            input()
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
