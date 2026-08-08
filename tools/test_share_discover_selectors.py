"""
Selector discovery tool for Poshmark Share Modal party destinations.

This script opens a browser to a destination closet page, clicks the share
icon on an AVAILABLE listing, and enumerates all share destinations inside
the modal, specifically identifying Posh Party controls.

Target: https://poshmark.com/closet/dveshop

Usage:
    python tools/test_share_discover_selectors.py

Requirements:
- Only inspects AVAILABLE listings
- Does NOT actually share to parties
- Discovers party destination selectors and attributes

The browser will pause at key points for manual inspection.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright, Page

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE
from scraper.availability import AvailabilityStatus


def safe_str(text: str | None) -> str:
    """Convert text to ASCII-safe string for Windows console."""
    if text is None:
        return "None"
    # Replace non-ASCII characters with '?'
    return text.encode('ascii', errors='replace').decode('ascii')


def print_step(message: str) -> None:
    """Print a step header."""
    print("\n" + "=" * 60)
    print(message)
    print("=" * 60)


def check_listing_availability(page: Page, card_locator) -> tuple[bool, str, dict]:
    """
    Check if a listing card is AVAILABLE.
    
    Returns (is_available, status_text, debug_info).
    
    IMPORTANT: This checks closet card DOM, NOT listing detail pages.
    Looking for explicit status badges like "Sold", "Not For Sale", etc.
    """
    result = card_locator.evaluate("""
        (card) => {
            // Look for explicit status badges/overlays
            // These typically appear as overlays on sold/unavailable items
            const statusBadges = card.querySelectorAll(
                '.badge, .status-badge, [class*="sold"], [class*="unavailable"], ' +
                '[class*="not-for-sale"], [class*="inactive-badge"]'
            );
            
            const badgeTexts = Array.from(statusBadges).map(el => ({
                text: el.textContent.trim(),
                className: el.className,
            }));
            
            // Get the full card text for debugging
            const fullCardText = card.textContent;
            
            // Check for explicit unavailable status text in badges
            const unavailableKeywords = ['sold', 'not for sale', 'unavailable', 'sold out'];
            
            for (const badge of badgeTexts) {
                const lowerText = badge.text.toLowerCase();
                for (const keyword of unavailableKeywords) {
                    if (lowerText === keyword || lowerText === keyword.replace(' ', '')) {
                        return {
                            available: false,
                            status: keyword,
                            reason: 'explicit_badge',
                            badgeText: badge.text,
                            badgeClass: badge.className,
                            cardTextSample: fullCardText.substring(0, 200),
                        };
                    }
                }
            }
            
            // If no explicit badge found, assume available
            // (Do NOT check full card text as it may contain unrelated "inactive" text)
            return {
                available: true,
                status: 'available',
                reason: 'no_unavailable_badge',
                badgeCount: badgeTexts.length,
                cardTextSample: fullCardText.substring(0, 200),
            };
        }
    """)
    
    return result['available'], result['status'], result


def inspect_share_destinations(page: Page) -> dict:
    """
    Enumerate ALL share destinations inside the modal.
    
    Specifically identifies:
    - "To My Followers" destination
    - Posh Party destinations (active parties)
    - External/social destinations
    
    Returns detailed DOM evidence for each destination.
    """
    print(f"\n{'=' * 60}")
    print(f"ENUMERATING SHARE DESTINATIONS IN MODAL")
    print("=" * 60)
    
    result = page.evaluate("""
        () => {
            // Find modal container
            const modal = document.querySelector('[data-test="listing-share-modal-container"]') ||
                         document.querySelector('[role="dialog"]') || 
                         document.querySelector('.modal');
            
            if (!modal) {
                return { error: 'No modal found' };
            }
            
            // Get modal info
            const modalInfo = {
                tag: modal.tagName,
                className: modal.className,
                role: modal.getAttribute('role'),
                dataTest: modal.getAttribute('data-test'),
            };
            
            // Find ALL clickable share destinations (anchors and buttons)
            const allDestinations = [];
            
            // Get all anchors in modal
            const anchors = Array.from(modal.querySelectorAll('a'));
            for (const a of anchors) {
                const text = a.textContent.trim();
                
                // Skip empty or very short text (likely icons only)
                if (text.length < 2) continue;
                
                allDestinations.push({
                    type: 'anchor',
                    tag: a.tagName,
                    text: text,
                    href: a.getAttribute('href'),
                    className: a.className,
                    dataEtName: a.getAttribute('data-et-name'),
                    dataEtProp: a.getAttribute('data-et-prop'),
                    dataEtPropListingId: a.getAttribute('data-et-prop-listing_id'),
                    dataTest: a.getAttribute('data-test'),
                    dataTestId: a.getAttribute('data-testid'),
                    ariaLabel: a.getAttribute('aria-label'),
                    ariaDisabled: a.getAttribute('aria-disabled'),
                    title: a.getAttribute('title'),
                    role: a.getAttribute('role'),
                    tabIndex: a.getAttribute('tabindex'),
                    clickable: true,
                    outerHTML: a.outerHTML,
                });
            }
            
            // Get all buttons in modal (excluding close/cancel/done)
            const buttons = Array.from(modal.querySelectorAll('button'));
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                
                // Skip modal control buttons
                if (text === 'Cancel' || text === 'Done' || text === '' || 
                    btn.className.includes('close')) {
                    continue;
                }
                
                allDestinations.push({
                    type: 'button',
                    tag: btn.tagName,
                    text: text,
                    href: null,
                    className: btn.className,
                    dataEtName: btn.getAttribute('data-et-name'),
                    dataEtProp: btn.getAttribute('data-et-prop'),
                    dataEtPropListingId: btn.getAttribute('data-et-prop-listing_id'),
                    dataTest: btn.getAttribute('data-test'),
                    dataTestId: btn.getAttribute('data-testid'),
                    ariaLabel: btn.getAttribute('aria-label'),
                    ariaDisabled: btn.getAttribute('aria-disabled'),
                    title: btn.getAttribute('title'),
                    role: btn.getAttribute('role'),
                    tabIndex: btn.getAttribute('tabindex'),
                    disabled: btn.disabled,
                    clickable: !btn.disabled,
                    outerHTML: btn.outerHTML,
                });
            }
            
            // Categorize destinations
            const followers = [];
            const parties = [];
            const external = [];
            const other = [];
            
            for (const dest of allDestinations) {
                const textLower = dest.text.toLowerCase();
                const etName = dest.dataEtName || '';
                
                // Identify "To My Followers"
                if (textLower.includes('follower') || etName === 'share_poshmark') {
                    followers.push(dest);
                }
                // Identify party destinations
                // Look for "Party" in text or specific patterns
                else if (textLower.includes('party') || textLower.includes('posh party')) {
                    parties.push(dest);
                }
                // Identify external/social shares
                else if (textLower.includes('facebook') || textLower.includes('twitter') ||
                         textLower.includes('pinterest') || textLower.includes('email') ||
                         textLower.includes('copy link') || textLower.includes('instagram') ||
                         etName.includes('facebook') || etName.includes('twitter') ||
                         etName.includes('pinterest') || etName.includes('email')) {
                    external.push(dest);
                }
                else {
                    other.push(dest);
                }
            }
            
            // Get modal text for analysis
            const modalText = modal.textContent;
            
            return {
                modalInfo,
                totalDestinations: allDestinations.length,
                allDestinations,
                followers,
                parties,
                external,
                other,
                modalTextSample: modalText.substring(0, 800),
            };
        }
    """)
    
    return result


def print_destination(dest: dict, index: int) -> None:
    """Print detailed information about a single share destination."""
    print(f"\n  Destination {index}:")
    print(f"    Type: {safe_str(dest['type'])}")
    print(f"    Tag: {safe_str(dest['tag'])}")
    print(f"    Text: '{safe_str(dest['text'])}'")
    print(f"    href: {safe_str(dest['href'])}")
    print(f"    class: {safe_str(dest['className'][:100])}")
    print(f"    data-et-name: {safe_str(dest['dataEtName'])}")
    print(f"    data-et-prop: {safe_str(dest['dataEtProp'])}")
    print(f"    data-et-prop-listing_id: {safe_str(dest['dataEtPropListingId'])}")
    print(f"    data-test: {safe_str(dest['dataTest'])}")
    print(f"    data-testid: {safe_str(dest['dataTestId'])}")
    print(f"    aria-label: {safe_str(dest['ariaLabel'])}")
    print(f"    aria-disabled: {safe_str(dest['ariaDisabled'])}")
    print(f"    title: {safe_str(dest['title'])}")
    print(f"    role: {safe_str(dest['role'])}")
    print(f"    tabindex: {safe_str(dest['tabIndex'])}")
    print(f"    clickable: {dest['clickable']}")
    if dest['type'] == 'button':
        print(f"    disabled: {dest.get('disabled', False)}")
    print(f"    outerHTML:")
    # Pretty print HTML with indentation
    html = safe_str(dest['outerHTML'])
    for line in html.split('>'):
        if line.strip():
            print(f"      {line.strip()}>")


def print_destinations_inspection(result: dict) -> None:
    """Pretty print share destinations inspection results."""
    if 'error' in result:
        print(f"\n[X] ERROR: {result['error']}")
        return
    
    print(f"\n[MODAL CONTAINER]:")
    m = result['modalInfo']
    print(f"  Tag: {safe_str(m['tag'])}")
    print(f"  Class: {safe_str(m['className'][:100])}")
    print(f"  role: {safe_str(m['role'])}")
    print(f"  data-test: {safe_str(m['dataTest'])}")
    
    print(f"\n[MODAL TEXT SAMPLE]:")
    print(f"  {safe_str(result['modalTextSample'][:400])}")
    
    print(f"\n{'=' * 60}")
    print(f"TOTAL SHARE DESTINATIONS FOUND: {result['totalDestinations']}")
    print("=" * 60)
    
    # Print "To My Followers" destinations
    print(f"\n[TO MY FOLLOWERS DESTINATIONS] ({len(result['followers'])} found):")
    if result['followers']:
        for i, dest in enumerate(result['followers'], 1):
            print_destination(dest, i)
    else:
        print("  (none)")
    
    # Print Posh Party destinations
    print(f"\n{'=' * 60}")
    print(f"[POSH PARTY DESTINATIONS] ({len(result['parties'])} found):")
    print("=" * 60)
    if result['parties']:
        for i, dest in enumerate(result['parties'], 1):
            print_destination(dest, i)
        
        # Analyze party destination patterns
        print(f"\n[PARTY DESTINATION ANALYSIS]:")
        print(f"  Total party destinations: {len(result['parties'])}")
        
        # Check for common attributes
        et_names = [d['dataEtName'] for d in result['parties'] if d['dataEtName']]
        classes = [d['className'] for d in result['parties']]
        hrefs = [d['href'] for d in result['parties'] if d['href']]
        
        print(f"\n  Common attributes:")
        if et_names:
            print(f"    data-et-name values: {set(et_names)}")
        if classes:
            print(f"    Common classes: {set(classes)}")
        if hrefs:
            print(f"    href patterns: {hrefs}")
        
        # Extract party names
        print(f"\n  Party names extracted:")
        for i, dest in enumerate(result['parties'], 1):
            print(f"    Party {i}: '{safe_str(dest['text'])}'")
        
        # Check eligibility indicators
        print(f"\n  Eligibility indicators:")
        for i, dest in enumerate(result['parties'], 1):
            disabled = dest.get('disabled', False) or dest['ariaDisabled'] == 'true'
            print(f"    Party {i}: {'DISABLED/INELIGIBLE' if disabled else 'ELIGIBLE'}")
    else:
        print("  [INFO] NO PARTY DESTINATIONS FOUND")
        print("  This may mean:")
        print("    - No active Posh Party at this time")
        print("    - Selected listing category not eligible for current party")
        print("    - Party destinations shown in different UI location")
    
    # Print external/social destinations
    print(f"\n[EXTERNAL/SOCIAL DESTINATIONS] ({len(result['external'])} found):")
    if result['external']:
        for i, dest in enumerate(result['external'], 1):
            print(f"\n  External {i}:")
            print(f"    Text: '{safe_str(dest['text'])}'")
            print(f"    data-et-name: {safe_str(dest['dataEtName'])}")
            print(f"    href: {safe_str(dest['href'])}")
    else:
        print("  (none)")
    
    # Print other destinations
    if result['other']:
        print(f"\n[OTHER DESTINATIONS] ({len(result['other'])} found):")
        for i, dest in enumerate(result['other'], 1):
            print_destination(dest, i)


def find_available_listing(page: Page, max_attempts: int = 10) -> tuple[bool, any, str]:
    """
    Find an AVAILABLE listing on the page.
    
    Returns (found, card_container, listing_url).
    """
    print_step("FINDING AVAILABLE LISTING")
    
    # Get all listing cards
    listing_links = page.locator('a[href*="/listing/"]').all()
    
    if not listing_links:
        print("[X] ERROR: No listing cards found on page")
        return False, None, ""
    
    print(f"[OK] Found {len(listing_links)} listing cards on page")
    print(f"[INFO] Checking up to {min(max_attempts, len(listing_links))} listings for availability...")
    
    for i, listing_link in enumerate(listing_links[:max_attempts], 1):
        try:
            # Get listing URL
            listing_url = listing_link.get_attribute('href')
            print(f"\n  Checking listing {i}: {listing_url}")
            
            # Get card container
            card_container = listing_link.locator('xpath=ancestor::div[contains(@class, "tile") or contains(@class, "col")]').first
            
            if card_container.count() == 0:
                print(f"    [SKIP] Could not find card container")
                continue
            
            # Check availability
            is_available, status, debug_info = check_listing_availability(page, card_container)
            
            print(f"    Status: {status}")
            
            if is_available:
                print(f"    [OK] AVAILABLE - will use this listing")
                return True, card_container, listing_url
            else:
                print(f"    [SKIP] Not available ({status})")
        
        except Exception as e:
            print(f"    [ERROR] Failed to check: {e}")
            continue
    
    print(f"\n[X] ERROR: No AVAILABLE listings found in first {max_attempts} cards")
    return False, None, ""


def main() -> None:
    """Main discovery function."""
    print("\n" + "=" * 60)
    print("POSHMARK SHARE MODAL PARTY DESTINATIONS DISCOVERY")
    print("=" * 60)
    
    # Check for destination state file
    if not DESTINATION_STATE_FILE.exists():
        print(f"\n[X] ERROR: {DESTINATION_STATE_FILE.name} not found!")
        print("Please run login.py first to save destination account session.")
        sys.exit(1)
    
    print(f"\n[OK] Found {DESTINATION_STATE_FILE.name}")
    
    # Target closet URL
    closet_url = "https://poshmark.com/closet/dveshop"
    print(f"[OK] Target closet: {closet_url}")
    
    with sync_playwright() as playwright:
        try:
            # Open logged-in browser
            print_step("STEP 1: OPENING BROWSER")
            
            browser, context, page = open_logged_in_browser(
                playwright,
                state_file=DESTINATION_STATE_FILE,
            )
            
            print("[OK] Browser opened with destination account session")
            
            # Navigate to closet
            print(f"\nNavigating to: {closet_url}")
            page.goto(closet_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            print("[OK] Closet page loaded")
            
            # Step 2: Find AVAILABLE listing
            print_step("STEP 2: FINDING AVAILABLE LISTING")
            
            found, card_container, listing_url = find_available_listing(page, max_attempts=20)
            
            if not found:
                print("\n[X] ERROR: Could not find any AVAILABLE listings")
                print("[INFO] This is required by HARD AVAILABILITY RULE")
                print("[INFO] Only AVAILABLE listings can be used for share discovery")
                context.close()
                browser.close()
                sys.exit(1)
            
            print(f"\n[OK] Selected AVAILABLE listing: {listing_url}")
            
            # Step 3: Find and click share icon
            print_step("STEP 3: CLICKING SHARE ICON")
            
            # Find share icon within the card
            share_icon = card_container.locator('div.share-v2.cursor--pointer').first
            
            if share_icon.count() == 0:
                print("[X] ERROR: Share icon not found in card")
                print("Trying alternative selector...")
                share_icon = card_container.locator('.share-v2').first
                
                if share_icon.count() == 0:
                    print("[X] ERROR: No share icon found with any selector")
                    context.close()
                    browser.close()
                    sys.exit(1)
            
            print("[OK] Found share icon")
            print(f"  Selector used: div.share-v2.cursor--pointer")
            
            # Click share icon
            share_icon.click()
            print("[OK] Clicked share icon")
            
            # Wait for modal to appear
            print("\nWaiting for modal to appear...")
            page.wait_for_timeout(2000)
            
            # Verify modal is visible
            modal = page.locator('[data-test="listing-share-modal-container"]')
            if modal.count() == 0:
                print("[WARNING] Modal not found with data-test selector, trying alternatives...")
                modal = page.locator('[role="dialog"]')
                if modal.count() == 0:
                    print("[X] ERROR: Share modal did not appear")
                    context.close()
                    browser.close()
                    sys.exit(1)
            
            print("[OK] Share modal is visible")
            
            # Step 4: Enumerate share destinations
            print_step("STEP 4: ENUMERATING SHARE DESTINATIONS")
            
            destinations_result = inspect_share_destinations(page)
            print_destinations_inspection(destinations_result)
            
            # Step 5: Summary and recommendations
            print_step("STEP 5: DISCOVERY SUMMARY")
            
            if 'error' not in destinations_result:
                party_count = len(destinations_result['parties'])
                
                print(f"\n[RESULTS]:")
                print(f"  Total destinations found: {destinations_result['totalDestinations']}")
                print(f"  'To My Followers' destinations: {len(destinations_result['followers'])}")
                print(f"  Posh Party destinations: {party_count}")
                print(f"  External/social destinations: {len(destinations_result['external'])}")
                print(f"  Other destinations: {len(destinations_result['other'])}")
                
                if party_count > 0:
                    print(f"\n[✓] SUCCESS: Found {party_count} Posh Party destination(s)")
                    print(f"\n[RECOMMENDED SELECTOR STRATEGY]:")
                    
                    # Analyze common patterns
                    parties = destinations_result['parties']
                    et_names = [d['dataEtName'] for d in parties if d['dataEtName']]
                    
                    if et_names and len(set(et_names)) == 1:
                        print(f"  Use data-et-name attribute: '{et_names[0]}'")
                        print(f"  Selector: a[data-et-name=\"{et_names[0]}\"]")
                    else:
                        print(f"  Use text-based filtering with 'party' keyword")
                        print(f"  Selector: modal.locator('a').filter(has_text='Party')")
                    
                    print(f"\n[PARTY NAME EXTRACTION]:")
                    print(f"  Extract from element.textContent")
                    print(f"  Party names found:")
                    for i, dest in enumerate(parties, 1):
                        print(f"    {i}. '{safe_str(dest['text'])}'")
                else:
                    print(f"\n[INFO] NO PARTY DESTINATIONS FOUND")
                    print(f"\n[POSSIBLE REASONS]:")
                    print(f"  1. No active Posh Party at this time")
                    print(f"  2. Selected listing category not eligible for current party")
                    print(f"  3. Party destinations may appear in different UI location")
                    print(f"  4. May need to test with different listing category")
            
            # Wait before closing
            print(f"\n[INFO] Keeping browser open for 5 seconds for manual inspection...")
            page.wait_for_timeout(5000)
            
            # Cleanup
            context.close()
            browser.close()
            
            print("\n" + "=" * 60)
            print("DISCOVERY COMPLETE")
            print("=" * 60)
            print("\n[NEXT STEPS]:")
            print("  1. Review party destination DOM evidence above")
            print("  2. Identify stable selector for party destinations")
            print("  3. Determine party name extraction method")
            print("  4. Check eligibility representation (disabled/aria-disabled)")
            print("  5. DO NOT modify share_engine.py yet")
            print("  6. Wait for approval before implementing selectors")
        
        except Exception as error:
            print(f"\n[X] ERROR: {error}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
