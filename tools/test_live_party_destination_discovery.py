"""
TASK-027A.2: Live Eligible Party Destination DOM Discovery

Complete final discovery step before implementing party sharing.
Discovers whether live eligible parties appear in share modal destinations.
"""

from __future__ import annotations

import sys
import re
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE
from party.party_manager import PartyManager
from party.party_models import PartyEligibilityStatus
from party.eligibility import is_listing_eligible_for_party
from scraper.availability import verify_listing_availability, AvailabilityStatus
from scraper.listing_scraper import scrape_listing


def print_section(title):
    """Print section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def print_subsection(title):
    """Print subsection header."""
    print(f"\n--- {title} ---\n")


def phase_1_confirm_live_party(page: Page, party_manager: PartyManager):
    """PHASE 1: Confirm a live party exists."""
    print_section("PHASE 1 - CONFIRM LIVE PARTY")
    
    # Force refresh
    print("Force-refreshing PartyManager...")
    all_parties = party_manager.refresh_cache(page)
    
    # Find live party
    live_parties = [p for p in all_parties if p.is_live]
    
    if not live_parties:
        print("NO LIVE PARTIES FOUND")
        print("Cannot continue without a confirmed live party.")
        return None
    
    # Choose first live party
    party = live_parties[0]
    
    print(f"Found live party: {party.name}")
    print(f"\nNavigating to party detail page: {party.url}")
    
    # Navigate to party page
    try:
        page.goto(party.url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
    except PlaywrightTimeout:
        pass
    
    # Collect authoritative evidence
    evidence = []
    
    try:
        # Look for "Ends in ..." text
        ends_in = page.locator("text=/Ends in/i").first
        if ends_in.is_visible():
            evidence.append(f"'Ends in' text found: {ends_in.text_content()}")
    except:
        pass
    
    try:
        # Look for "View party details" link
        view_details = page.locator("text=/View party details/i").first
        if view_details.is_visible():
            evidence.append("'View party details' link found")
    except:
        pass
    
    try:
        # Check for live party UI indicators
        live_indicators = page.locator("[class*='live'], [class*='current']").all()
        if live_indicators:
            evidence.append(f"Live UI indicators found: {len(live_indicators)} elements")
    except:
        pass
    
    # Print results
    print_subsection("LIVE PARTY CONFIRMATION")
    print(f"party_id: {party.party_id}")
    print(f"party_name: {party.name}")
    print(f"party_url: {party.url}")
    print(f"party_type: {party.party_type}")
    print(f"guidelines: {party.guidelines}")
    print(f"is_live: {party.is_live}")
    print(f"\nLive Evidence:")
    for ev in evidence:
        print(f"  - {ev}")
    
    if not evidence:
        print("\nWARNING: No authoritative evidence found on party page")
        print("Party may not actually be live")
        return None
    
    return party


def phase_2_choose_eligible_listing(page: Page, party):
    """PHASE 2: Choose an eligible listing."""
    print_section("PHASE 2 - CHOOSE ELIGIBLE LISTING")
    
    closet_url = "https://poshmark.com/closet/dveshop"
    print(f"Opening closet: {closet_url}")
    
    try:
        page.goto(closet_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
    except PlaywrightTimeout:
        pass
    
    # Collect listing URLs from closet cards
    print("Collecting listing URLs from closet...")
    listing_links = page.locator("a.tile__covershot").all()
    listing_urls = []
    for link in listing_links:
        href = link.get_attribute("href")
        if href:
            # Convert relative URLs to absolute
            if href.startswith('/'):
                href = f"https://poshmark.com{href}"
            listing_urls.append(href)
    listing_urls = list(set(listing_urls))
    
    print(f"Found {len(listing_urls)} unique listings")
    
    # Test each listing
    for idx, listing_url in enumerate(listing_urls[:20], 1):  # Test first 20
        print(f"\n[{idx}/{min(20, len(listing_urls))}] Testing: {listing_url}")
        
        try:
            # Navigate to listing
            page.goto(listing_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            # Check availability
            availability_result = verify_listing_availability(page)
            print(f"  Availability: {availability_result}")
            
            # Check if available
            if not availability_result.available:
                print(f"  SKIP: Not available")
                continue
            
            # Use the enum value for eligibility checking
            availability = AvailabilityStatus.AVAILABLE
            
            # Assume active if available (skip explicit active check for discovery)
            is_active = True
            print(f"  Active: {is_active} (assumed from availability)")
            
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
                'availability': availability
            }
            
            print(f"  Brand: {eligibility_data['brand']}")
            print(f"  Department: {eligibility_data['department']}")
            print(f"  Category: {eligibility_data['category']}")
            print(f"  Subcategory: {eligibility_data['subcategory']}")
            print(f"  Size: {eligibility_data['size']}")
            
            # Check eligibility
            eligibility = is_listing_eligible_for_party(eligibility_data, party)
            print(f"  Eligibility Status: {eligibility.status}")
            print(f"  Reason: {eligibility.reason}")
            
            if eligibility.status == PartyEligibilityStatus.ELIGIBLE:
                print_subsection("ELIGIBLE LISTING FOUND")
                print(f"Listing URL: {listing_url}")
                print(f"Availability: {availability}")
                print(f"Active: {is_active}")
                print(f"Party: {party.name}")
                print(f"Eligibility Status: {eligibility.status}")
                print(f"Reason: {eligibility.reason}")
                return listing_url, eligibility_data
        
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
    
    print("\nNO ELIGIBLE LISTING FOUND")
    return None, None


def phase_3_open_share_modal(page: Page, listing_url: str):
    """PHASE 3: Open share modal for the listing."""
    print_section("PHASE 3 - OPEN SHARE MODAL")
    
    closet_url = "https://poshmark.com/closet/dveshop"
    print(f"Returning to closet: {closet_url}")
    
    try:
        page.goto(closet_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
    except PlaywrightTimeout:
        pass
    
    # Find the specific listing card
    print(f"Locating closet card for: {listing_url}")
    
    # Extract listing ID from URL
    listing_id = listing_url.split('/')[-1]
    print(f"Listing ID: {listing_id}")
    
    # Find all share buttons
    share_buttons = page.locator("div.share-v2.cursor--pointer").all()
    print(f"Found {len(share_buttons)} share buttons")
    
    # Find the correct share button by checking parent tile
    target_button = None
    for button in share_buttons:
        try:
            # Check if this button's parent tile contains a link to our listing
            parent_tile = button.locator("xpath=ancestor::div[contains(@class, 'tile')]").first
            tile_links = parent_tile.locator("a.tile__covershot").all()
            
            for link in tile_links:
                href = link.get_attribute("href")
                if href and listing_id in href:
                    target_button = button
                    print(f"Found matching share button for listing {listing_id}")
                    break
            
            if target_button:
                break
        except:
            continue
    
    if not target_button:
        print("ERROR: Could not find share button for listing")
        return False
    
    # Click share button
    print("Clicking share button...")
    target_button.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    target_button.click()
    
    # Wait for modal
    print("Waiting for share modal...")
    try:
        page.wait_for_selector("[data-test='listing-share-modal-container']", timeout=10000)
        print("Share modal opened successfully")
        page.wait_for_timeout(2000)  # Let modal fully load
        return True
    except PlaywrightTimeout:
        print("ERROR: Share modal did not appear")
        return False


def phase_4_enumerate_destinations(page: Page):
    """PHASE 4: Enumerate all destinations."""
    print_section("PHASE 4 - ENUMERATE ALL DESTINATIONS")
    
    # Find all clickable destinations
    # Try multiple selectors
    selectors = [
        "button[data-et-name]",
        "a[data-et-name]",
        "[data-test*='share']",
        "button[class*='share']",
        "a[class*='share']"
    ]
    
    all_destinations = []
    for selector in selectors:
        elements = page.locator(selector).all()
        all_destinations.extend(elements)
    
    # Deduplicate
    seen = set()
    unique_destinations = []
    for elem in all_destinations:
        try:
            outer = elem.evaluate("el => el.outerHTML")[:100]
            if outer not in seen:
                seen.add(outer)
                unique_destinations.append(elem)
        except:
            continue
    
    print(f"Found {len(unique_destinations)} unique destinations")
    
    # Enumerate each destination
    destinations_data = []
    for idx, dest in enumerate(unique_destinations, 1):
        try:
            outer_html = dest.evaluate("el => el.outerHTML")
            
            data = {
                'index': idx,
                'tag': dest.evaluate("el => el.tagName.toLowerCase()"),
                'visible_text': dest.text_content().strip() if dest.text_content() else '',
                'class': dest.get_attribute("class") or '',
                'href': dest.get_attribute("href") or '',
                'data_test': dest.get_attribute("data-test") or '',
                'data_testid': dest.get_attribute("data-testid") or '',
                'data_et_name': dest.get_attribute("data-et-name") or '',
                'aria_label': dest.get_attribute("aria-label") or '',
                'aria_disabled': dest.get_attribute("aria-disabled") or '',
                'role': dest.get_attribute("role") or '',
                'disabled': dest.get_attribute("disabled") or '',
                'outer_html': outer_html[:500] if outer_html else ''
            }
            
            # Get all data-et-prop-* attributes
            data_et_props = {}
            prop_matches = re.findall(r'data-et-prop-([^=]+)="([^"]*)"', outer_html)
            for prop_name, prop_value in prop_matches:
                data_et_props[f"data-et-prop-{prop_name}"] = prop_value
            
            data['data_et_props'] = data_et_props
            
            destinations_data.append(data)
            
            # Print destination
            print(f"\n[Destination {idx}]")
            print(f"  tag: {data['tag']}")
            print(f"  visible_text: {data['visible_text']}")
            print(f"  class: {data['class']}")
            print(f"  href: {data['href']}")
            print(f"  data-test: {data['data_test']}")
            print(f"  data-testid: {data['data_testid']}")
            print(f"  data-et-name: {data['data_et_name']}")
            if data_et_props:
                print(f"  data-et-prop-* attributes:")
                for prop, val in data_et_props.items():
                    print(f"    {prop}: {val}")
            print(f"  aria-label: {data['aria_label']}")
            print(f"  aria-disabled: {data['aria_disabled']}")
            print(f"  role: {data['role']}")
            print(f"  disabled: {data['disabled']}")
            print(f"  outerHTML (first 500): {data['outer_html']}")
        
        except Exception as e:
            print(f"\n[Destination {idx}] ERROR: {e}")
    
    return destinations_data


def phase_5_identify_share_types(destinations_data):
    """PHASE 5: Identify share types."""
    print_section("PHASE 5 - IDENTIFY SHARE TYPES")
    
    classified = []
    
    for dest in destinations_data:
        share_type = "UNKNOWN"
        
        text = dest['visible_text'].lower()
        et_name = dest['data_et_name'].lower()
        href = dest['href'].lower()
        outer = dest['outer_html'].lower()
        
        # Classify
        if "posh shows host" in text or "posh show" in text:
            share_type = "POSH_SHOW_HOST"
        elif "followers" in text or "my followers" in text:
            share_type = "FOLLOWERS"
        elif "/party/" in href or "party" in et_name:
            share_type = "POSH_PARTY"
        elif "user" in et_name or "@" in text:
            share_type = "DIRECT_USER"
        elif any(social in text for social in ["facebook", "twitter", "pinterest", "instagram"]):
            share_type = "EXTERNAL"
        
        dest['share_type'] = share_type
        classified.append(dest)
        
        # ASCII-safe output
        safe_text = dest['visible_text'][:50].encode('ascii', 'replace').decode('ascii')
        print(f"[{dest['index']}] {share_type}: {safe_text}")
    
    return classified


def phase_6_match_live_party(classified_destinations, party):
    """PHASE 6: Match live party."""
    print_section("PHASE 6 - MATCH LIVE PARTY")
    
    print(f"Searching for party: {party.name} (ID: {party.party_id})")
    
    matches = []
    
    for dest in classified_destinations:
        match_methods = []
        party_id_present = False
        party_name_present = False
        
        # Check party_id in various attributes
        party_id_str = str(party.party_id)
        
        if party_id_str in dest['href']:
            match_methods.append("href contains party_id")
            party_id_present = True
        
        if party_id_str in dest['outer_html']:
            match_methods.append("outerHTML contains party_id")
            party_id_present = True
        
        for prop, val in dest['data_et_props'].items():
            if party_id_str in str(val):
                match_methods.append(f"{prop} contains party_id")
                party_id_present = True
        
        if party_id_str in dest['data_test'] or party_id_str in dest['data_testid']:
            match_methods.append("data-test/testid contains party_id")
            party_id_present = True
        
        # Check party name in visible text
        if party.name.lower() in dest['visible_text'].lower():
            match_methods.append("visible text contains party name")
            party_name_present = True
        
        # Check if it's a party destination
        if dest['share_type'] == 'POSH_PARTY' and (party_id_present or party_name_present):
            matches.append({
                'destination': dest,
                'match_methods': match_methods,
                'party_id_present': party_id_present,
                'party_name_present': party_name_present
            })
    
    if matches:
        print(f"\nFOUND {len(matches)} MATCHING DESTINATION(S)")
        
        for match in matches:
            dest = match['destination']
            print(f"\n[Matched Destination {dest['index']}]")
            print(f"  Visible Text: {dest['visible_text']}")
            print(f"  Match Methods: {', '.join(match['match_methods'])}")
            print(f"  Party ID Present: {match['party_id_present']}")
            print(f"  Party Name Present: {match['party_name_present']}")
            
            # Recommend stable selector
            print(f"\n  Recommended Stable Selector:")
            if match['party_id_present']:
                if dest['data_et_props']:
                    for prop, val in dest['data_et_props'].items():
                        if str(party.party_id) in str(val):
                            print(f"    1. [{prop}='{val}']")
                            break
                if "/party/" in dest['href']:
                    print(f"    2. a[href*='/party/{party.party_id}']")
                if dest['data_et_name']:
                    print(f"    3. [{dest['data_et_name']}] + party_id filter")
            else:
                print(f"    Fallback: text match on '{dest['visible_text']}'")
    else:
        print("\nNO MATCHING PARTY DESTINATION FOUND")
    
    return matches


def phase_7_modal_scroll(page: Page, party, initial_count):
    """PHASE 7: Scroll modal and check for lazy loading."""
    print_section("PHASE 7 - MODAL SCROLL / LAZY LOAD")
    
    print(f"Initial destination count: {initial_count}")
    
    # Find scrollable container
    try:
        modal = page.locator("[data-test='listing-share-modal-container']").first
        
        # Scroll incrementally
        print("Scrolling modal to bottom...")
        last_height = modal.evaluate("el => el.scrollHeight")
        
        for i in range(5):  # Try 5 scrolls
            modal.evaluate("el => el.scrollTop = el.scrollHeight")
            page.wait_for_timeout(1000)
            
            new_height = modal.evaluate("el => el.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            print(f"  Scroll {i+1}: height = {new_height}")
        
        print("Scroll complete, waiting for lazy load...")
        page.wait_for_timeout(2000)
        
        # Recount destinations
        destinations_data = phase_4_enumerate_destinations(page)
        final_count = len(destinations_data)
        
        print(f"\nFinal destination count: {final_count}")
        
        if final_count > initial_count:
            print(f"LAZY LOADING DETECTED: {final_count - initial_count} new destinations loaded")
            
            # Re-run matching
            classified = phase_5_identify_share_types(destinations_data)
            matches = phase_6_match_live_party(classified, party)
            return destinations_data, matches
        else:
            print("No lazy loading detected")
            return None, None
    
    except Exception as e:
        print(f"ERROR during scroll: {e}")
        return None, None


def phase_8_posh_shows(classified_destinations):
    """PHASE 8: Recognize Posh Shows."""
    print_section("PHASE 8 - POSH SHOWS")
    
    posh_shows = [d for d in classified_destinations if d['share_type'] == 'POSH_SHOW_HOST']
    
    if posh_shows:
        print(f"Found {len(posh_shows)} Posh Shows destination(s)")
        for ps in posh_shows:
            print(f"\n[Posh Shows Destination {ps['index']}]")
            print(f"  Text: {ps['visible_text']}")
            print(f"  data-et-name: {ps['data_et_name']}")
            print(f"  Architecture Note: Separate destination type")
            print(f"  Future Config: share_to_posh_shows = False")
            print(f"  Action: NEVER CLICK")
    else:
        print("No Posh Shows destinations found")
    
    return posh_shows


def phase_9_output(party, listing_url, eligibility_data, initial_destinations, 
                   final_destinations, matches, posh_shows):
    """PHASE 9: Final output."""
    print_section("PHASE 9 - FINAL OUTPUT")
    
    print("1. Live Party Tested:")
    print(f"   {party.name} (ID: {party.party_id})")
    
    print("\n2. Listing Tested:")
    print(f"   {listing_url}")
    
    print("\n3. Eligibility Proof:")
    print(f"   Brand: {eligibility_data.get('brand')}")
    print(f"   Department: {eligibility_data.get('department')}")
    print(f"   Category: {eligibility_data.get('category')}")
    print(f"   Availability: {eligibility_data.get('availability')}")
    print(f"   Status: ELIGIBLE")
    
    print(f"\n4. Total Destinations Initially: {len(initial_destinations)}")
    
    if final_destinations:
        print(f"\n5. Total Destinations After Scroll: {len(final_destinations)}")
    else:
        print(f"\n5. Total Destinations After Scroll: {len(initial_destinations)} (no change)")
    
    # Find specific destination types
    followers = [d for d in initial_destinations if d['share_type'] == 'FOLLOWERS']
    parties = [d for d in initial_destinations if d['share_type'] == 'POSH_PARTY']
    
    print("\n6. Followers Destination DOM:")
    if followers:
        f = followers[0]
        print(f"   Tag: {f['tag']}")
        print(f"   Text: {f['visible_text']}")
        print(f"   data-et-name: {f['data_et_name']}")
    else:
        print("   NOT FOUND")
    
    print("\n7. Posh Shows Destination DOM:")
    if posh_shows:
        ps = posh_shows[0]
        print(f"   Tag: {ps['tag']}")
        print(f"   Text: {ps['visible_text']}")
        print(f"   data-et-name: {ps['data_et_name']}")
    else:
        print("   NOT FOUND")
    
    print("\n8. Party Destination DOM:")
    if matches:
        m = matches[0]['destination']
        print(f"   Tag: {m['tag']}")
        print(f"   Text: {m['visible_text']}")
        print(f"   href: {m['href']}")
        print(f"   data-et-name: {m['data_et_name']}")
        print(f"   data-et-props: {m['data_et_props']}")
    else:
        print("   NOT FOUND")
    
    print(f"\n9. Party ID Exists in DOM: {len(matches) > 0}")
    
    print("\n10. Recommended Production Selector:")
    if matches:
        m = matches[0]
        if m['party_id_present']:
            print(f"    Use party_id in data-et-prop or href")
            print(f"    Example: a[href*='/party/{party.party_id}']")
        else:
            print(f"    Use text match: '{m['destination']['visible_text']}'")
    else:
        print("    N/A - No party destination found")
    
    print(f"\n11. Multiple Party Destinations: {len(parties) > 1}")
    if len(parties) > 1:
        print(f"    Found {len(parties)} party destinations total")
    
    print("\n12. Poshmark Filters Ineligible Parties:")
    if len(parties) > 0:
        print(f"    LIKELY YES - Only {len(parties)} party destination(s) shown")
        print(f"    (Not all parties in system)")
    else:
        print(f"    UNKNOWN - No party destinations found")
    
    print("\n13. FINAL CONCLUSION:")
    if matches:
        print("    PARTY_DESTINATION_FOUND")
        print(f"    The live eligible party '{party.name}' appears in the share modal")
        print(f"    Party sharing is POSSIBLE via web automation")
    else:
        print("    NO_PARTY_DESTINATION_ON_WEB")
        print(f"    The live eligible party '{party.name}' does NOT appear in share modal")
        print(f"    Party sharing may not be available for this listing/party combination")


def main():
    """Main execution."""
    print_section("TASK-027A.2: LIVE ELIGIBLE PARTY DESTINATION DOM DISCOVERY")
    
    with sync_playwright() as p:
        try:
            # Open logged-in browser
            print("Opening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened")
            
            # Initialize PartyManager
            party_manager = PartyManager()
            
            # PHASE 1: Confirm live party
            party = phase_1_confirm_live_party(page, party_manager)
            if not party:
                print("\nSTOPPING: No confirmed live party")
                return
            
            # PHASE 2: Choose eligible listing
            listing_url, eligibility_data = phase_2_choose_eligible_listing(page, party)
            if not listing_url:
                print("\nSTOPPING: No eligible listing found")
                return
            
            # PHASE 3: Open share modal
            if not phase_3_open_share_modal(page, listing_url):
                print("\nSTOPPING: Could not open share modal")
                return
            
            # PHASE 4: Enumerate destinations
            initial_destinations = phase_4_enumerate_destinations(page)
            
            # PHASE 5: Identify share types
            classified_destinations = phase_5_identify_share_types(initial_destinations)
            
            # PHASE 6: Match live party
            matches = phase_6_match_live_party(classified_destinations, party)
            
            # PHASE 7: Scroll and check lazy loading
            final_destinations, new_matches = phase_7_modal_scroll(page, party, len(initial_destinations))
            if new_matches:
                matches = new_matches
                classified_destinations = phase_5_identify_share_types(final_destinations)
            
            # PHASE 8: Posh Shows
            posh_shows = phase_8_posh_shows(classified_destinations)
            
            # PHASE 9: Output
            phase_9_output(party, listing_url, eligibility_data, classified_destinations,
                          final_destinations, matches, posh_shows)
            
            print("\n" + "=" * 80)
            print("DISCOVERY COMPLETE")
            print("=" * 80)
            
            # Keep browser open for inspection
            print("\nBrowser will remain open for 30 seconds for inspection...")
            page.wait_for_timeout(30000)
        
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
