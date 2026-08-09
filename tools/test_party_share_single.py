"""
TASK-027B: Single Party Share Test

Test party sharing with ONE listing to ONE live party.
Includes dry-run mode for safety.
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
from party.party_models import PartyEligibilityStatus
from party.eligibility import is_listing_eligible_for_party
from scraper.availability import verify_listing_availability, AvailabilityStatus
from scraper.listing_scraper import scrape_listing
from sharing.share_engine import PoshmarkShareEngine, ShareableListing
from sharing.share_config import ShareConfig


def print_section(title):
    """Print section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def main():
    """Main execution."""
    print_section("TASK-027B: SINGLE PARTY SHARE TEST")
    
    # Check for dry-run mode
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("[DRY RUN MODE] Will stop before clicking party destination\n")
    else:
        print("[LIVE MODE] Will perform ONE real party share\n")
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser
            print("Opening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened\n")
            
            # Initialize PartyManager
            party_manager = PartyManager()
            
            # STEP 1: Find live party
            print_section("STEP 1: FIND LIVE PARTY")
            
            print("Refreshing party cache...")
            all_parties = party_manager.refresh_cache(page)
            
            live_parties = [p for p in all_parties if p.is_live]
            
            if not live_parties:
                print("ERROR: No live parties found")
                print("Cannot proceed without a live party")
                return
            
            # Choose first live party
            party = live_parties[0]
            
            print(f"[OK] Live Party Found:")
            print(f"  Party ID: {party.party_id}")
            print(f"  Party Name: {party.name}")
            print(f"  Party Type: {party.party_type}")
            print(f"  Is Live: {party.is_live}")
            
            # STEP 2: Find eligible listing
            print_section("STEP 2: FIND ELIGIBLE LISTING")
            
            closet_url = "https://poshmark.com/closet/dveshop"
            print(f"Opening closet: {closet_url}")
            
            page.goto(closet_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)
            
            # Collect listing URLs
            print("Collecting listing URLs...")
            listing_links = page.locator("a.tile__covershot").all()
            listing_urls = []
            for link in listing_links:
                href = link.get_attribute("href")
                if href:
                    if href.startswith('/'):
                        href = f"https://poshmark.com{href}"
                    listing_urls.append(href)
            listing_urls = list(set(listing_urls))
            
            print(f"Found {len(listing_urls)} unique listings")
            
            # Test listings for eligibility
            eligible_listing = None
            eligible_data = None
            
            for idx, listing_url in enumerate(listing_urls[:20], 1):
                print(f"\n[{idx}/20] Testing: {listing_url}")
                
                try:
                    # Navigate to listing
                    page.goto(listing_url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                    
                    # Check availability
                    availability_result = verify_listing_availability(page)
                    
                    if not availability_result.available:
                        print(f"  SKIP: Not available")
                        continue
                    
                    print(f"  [OK] Availability: AVAILABLE")
                    
                    # Scrape listing data
                    listing_data = scrape_listing(page, listing_url)
                    
                    if not listing_data:
                        print(f"  SKIP: Could not scrape listing data")
                        continue
                    
                    # Build eligibility data
                    eligibility_data = {
                        'brand': listing_data.get('brand', ''),
                        'department': listing_data.get('department', ''),
                        'category': listing_data.get('category', ''),
                        'subcategory': listing_data.get('subcategory', ''),
                        'size': listing_data.get('size', ''),
                        'availability': AvailabilityStatus.AVAILABLE
                    }
                    
                    print(f"  Brand: {eligibility_data['brand']}")
                    print(f"  Category: {eligibility_data['category']}")
                    
                    # Check eligibility
                    eligibility = is_listing_eligible_for_party(eligibility_data, party)
                    print(f"  Eligibility: {eligibility.status}")
                    print(f"  Reason: {eligibility.reason}")
                    
                    if eligibility.status == PartyEligibilityStatus.ELIGIBLE:
                        eligible_listing = listing_url
                        eligible_data = listing_data
                        eligible_data['eligibility'] = eligibility
                        print(f"\n[OK] ELIGIBLE LISTING FOUND")
                        break
                
                except Exception as e:
                    print(f"  ERROR: {e}")
                    continue
            
            if not eligible_listing:
                print("\nERROR: No eligible listing found")
                print("Cannot proceed without an eligible listing")
                return
            
            # STEP 3: Prepare for share
            print_section("STEP 3: PREPARE FOR SHARE")
            
            listing_id = eligible_listing.split('/')[-1]
            
            # ASCII-safe output
            title = eligible_data.get('title', 'Unknown').encode('ascii', 'replace').decode('ascii')
            
            print(f"Listing ID: {listing_id}")
            print(f"Listing URL: {eligible_listing}")
            print(f"Listing Title: {title}")
            print(f"Availability: AVAILABLE")
            print(f"Active: True (assumed)")
            print(f"Party: {party.name} (ID: {party.party_id})")
            print(f"Eligibility: {eligible_data['eligibility'].status}")
            print(f"Reason: {eligible_data['eligibility'].reason}")
            
            # Create ShareableListing
            shareable_listing = ShareableListing(
                listing_id=listing_id,
                url=eligible_listing,
                title=eligible_data.get('title', 'Unknown'),
                available=True,
                active=True,
                party_eligible=True,
                eligibility_reason=eligible_data['eligibility'].reason,
            )
            
            # STEP 4: Initialize share engine
            print_section("STEP 4: INITIALIZE SHARE ENGINE")
            
            config = ShareConfig(
                closet_url=closet_url,
                share_to_parties=True,
                share_to_posh_shows=False,
                party_share_limit=1,
            )
            
            print(f"Config:")
            print(f"  share_to_parties: {config.share_to_parties}")
            print(f"  share_to_posh_shows: {config.share_to_posh_shows}")
            print(f"  party_share_limit: {config.party_share_limit}")
            
            share_engine = PoshmarkShareEngine(page, config)
            
            # STEP 5: Dry run or real share
            if dry_run:
                print_section("STEP 5: DRY RUN - VERIFY GATES")
                
                print("Opening share modal...")
                if not share_engine._open_share_modal_from_closet(listing_id):
                    print("ERROR: Could not open share modal")
                    return
                
                print("[OK] Share modal opened")
                
                # Detect Posh Shows
                if share_engine._detect_posh_shows_destination():
                    print("[OK] Posh Shows Host detected (will be skipped)")
                else:
                    print("  Posh Shows Host not detected")
                
                # Find party destination
                print(f"\nLooking for party destination...")
                party_dest = share_engine._find_party_destination(party.party_id, party.name)
                
                if party_dest is None:
                    print("ERROR: Party destination not found")
                    return
                
                print("[OK] Party destination found")
                
                # Verify destination
                print("\nVerifying party destination...")
                if not share_engine._verify_party_destination(party_dest, party.name):
                    print("ERROR: Party destination verification failed")
                    return
                
                print("[OK] Party destination verified")
                
                # Get party ID from element
                party_id_attr = party_dest.get_attribute('data-et-prop-party_id')
                print(f"\nParty ID Match: {party_id_attr == party.party_id}")
                print(f"  Expected: {party.party_id}")
                print(f"  Got: {party_id_attr}")
                
                # Get party name from element
                party_text = party_dest.text_content() or ""
                print(f"\nParty Name Match: {party.name.lower() in party_text.lower()}")
                print(f"  Expected: {party.name}")
                print(f"  Got: {party_text[:100]}")
                
                print_section("DRY RUN COMPLETE")
                print("All gates passed successfully!")
                print("\nTo perform real share, run without --dry-run flag")
                
            else:
                print_section("STEP 5: PERFORM REAL SHARE")
                
                print("WARNING: About to perform ONE real party share")
                print("Press Ctrl+C within 5 seconds to cancel...")
                
                try:
                    page.wait_for_timeout(5000)
                except KeyboardInterrupt:
                    print("\nCancelled by user")
                    return
                
                print("\nProceeding with share...")
                
                result = share_engine.share_listing_to_party(
                    shareable_listing,
                    party,
                    retry=False,
                )
                
                print_section("SHARE RESULT")
                
                print(f"Success: {result.success}")
                print(f"Shared: {result.shared}")
                print(f"Failed: {result.failed}")
                print(f"Message: {result.message}")
                print(f"Elapsed: {result.elapsed_seconds:.1f}s")
                print(f"Party ID: {result.party_id}")
                print(f"Party Name: {result.party_name}")
                
                if result.errors:
                    print(f"\nErrors:")
                    for error in result.errors:
                        print(f"  - {error.error_type}: {error.message}")
                
                if result.success:
                    print("\n[OK] PARTY SHARE SUCCESSFUL")
                else:
                    print("\n[FAILED] PARTY SHARE FAILED OR UNKNOWN")
            
            # Keep browser open for inspection
            print("\nBrowser will remain open for 30 seconds for inspection...")
            page.wait_for_timeout(30000)
        
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        
        except Exception as e:
            print(f"\nFATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            try:
                browser.close()
            except:
                pass


if __name__ == "__main__":
    main()

