"""
Test Campus Debut Party - Verify Expected Result

Expected:
- theme = "Campus Debut Posh Party"
- brands_allowed = ["All"]
- categories_allowed = ["All"]
- party_type = UNIVERSAL
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
from party.party_models import PartyType


def main():
    """Test Campus Debut party."""
    print("=" * 80)
    print("CAMPUS DEBUT PARTY TEST")
    print("=" * 80)
    
    party_manager = PartyManager()
    
    with sync_playwright() as p:
        try:
            # Open browser
            print("\nOpening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened")
            
            # Discover parties
            print("\n" + "=" * 80)
            print("DISCOVERING PARTIES")
            print("=" * 80)
            
            print("\nNavigating to parties page...")
            page.goto("https://poshmark.com/parties", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            print("\nDiscovering parties...")
            parties = party_manager.discover_parties(page)
            print(f"Discovered {len(parties)} parties")
            
            # Find Campus Debut
            campus_debut = None
            for party in parties:
                if "campus debut" in party.name.lower():
                    campus_debut = party
                    break
            
            if not campus_debut:
                print("\n[ERROR] Campus Debut party not found")
                print("\nAvailable parties:")
                for party in parties[:10]:
                    print(f"  - {party.name}")
                return
            
            print(f"\n[SUCCESS] Found Campus Debut party")
            print(f"  Name: {campus_debut.name}")
            print(f"  URL: {campus_debut.url}")
            print(f"  ID: {campus_debut.party_id}")
            print(f"  is_live (from list): {campus_debut.is_live}")
            
            # Navigate to party detail page for authoritative live check
            print("\n" + "=" * 80)
            print("VERIFYING LIVE STATUS")
            print("=" * 80)
            
            print(f"\nNavigating to party detail page...")
            page.goto(campus_debut.url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            # Check for authoritative live evidence
            live_evidence = page.evaluate("""
                () => {
                    const bodyText = document.body.textContent || '';
                    return {
                        has_ends_in: /ends in/i.test(bodyText),
                        has_live_now: /live now/i.test(bodyText),
                        has_happening_now: /happening now/i.test(bodyText),
                    };
                }
            """)
            
            print(f"\nAuthoritative live evidence:")
            print(f"  'Ends in': {live_evidence['has_ends_in']}")
            print(f"  'Live now': {live_evidence['has_live_now']}")
            print(f"  'Happening now': {live_evidence['has_happening_now']}")
            
            is_actually_live = (live_evidence['has_ends_in'] or 
                               live_evidence['has_live_now'] or 
                               live_evidence['has_happening_now'])
            
            print(f"\nFinal is_live: {is_actually_live}")
            
            # Update party live status
            campus_debut.is_live = is_actually_live
            
            # Load guidelines
            print("\n" + "=" * 80)
            print("LOADING GUIDELINES")
            print("=" * 80)
            
            print("\nLoading guidelines...")
            guidelines = party_manager.load_guidelines(page, campus_debut)
            
            if not guidelines:
                print("\n[ERROR] Failed to load guidelines")
                return
            
            print(f"\n[SUCCESS] Guidelines loaded")
            
            # Verify expected result
            print("\n" + "=" * 80)
            print("VERIFICATION")
            print("=" * 80)
            
            print(f"\nTheme: {guidelines.theme}")
            print(f"Brands Allowed: {guidelines.brands_allowed}")
            print(f"Categories Allowed: {guidelines.categories_allowed}")
            print(f"Departments Allowed: {guidelines.departments_allowed}")
            print(f"Sizes Allowed: {guidelines.sizes_allowed}")
            print(f"Other Rules: {guidelines.other_rules}")
            print(f"Parse Confidence: {guidelines.parse_confidence}")
            print(f"Party Type: {campus_debut.party_type}")
            
            # Check expected values
            print("\n" + "=" * 80)
            print("EXPECTED RESULT CHECK")
            print("=" * 80)
            
            checks = []
            
            # Check theme
            if "campus debut" in guidelines.theme.lower():
                print("\n[PASS] Theme contains 'Campus Debut'")
                checks.append(True)
            else:
                print(f"\n[FAIL] Theme does not contain 'Campus Debut': {guidelines.theme}")
                checks.append(False)
            
            # Check brands
            if guidelines.brands_allowed == ["All"]:
                print("[PASS] Brands Allowed = ['All']")
                checks.append(True)
            else:
                print(f"[FAIL] Brands Allowed != ['All']: {guidelines.brands_allowed}")
                checks.append(False)
            
            # Check categories
            if guidelines.categories_allowed == ["All"]:
                print("[PASS] Categories Allowed = ['All']")
                checks.append(True)
            else:
                print(f"[FAIL] Categories Allowed != ['All']: {guidelines.categories_allowed}")
                checks.append(False)
            
            # Check party type
            if campus_debut.party_type == PartyType.UNIVERSAL:
                print("[PASS] Party Type = UNIVERSAL")
                checks.append(True)
            else:
                print(f"[FAIL] Party Type != UNIVERSAL: {campus_debut.party_type}")
                checks.append(False)
            
            # Final result
            print("\n" + "=" * 80)
            if all(checks):
                print("[SUCCESS] All checks passed!")
            else:
                print(f"[PARTIAL] {sum(checks)}/{len(checks)} checks passed")
            print("=" * 80)
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
