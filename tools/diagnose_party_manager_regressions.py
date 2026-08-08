"""
Diagnose PartyManager Regressions

Issues to investigate:
1. Live party disappeared (was 22, now 0)
2. "Party Invitations" being cached as party name
3. Upcoming guideline extraction failing
4. Cache merge potentially overwriting fresh live status
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


def main():
    """Diagnose party manager issues."""
    print("=" * 80)
    print("PARTY MANAGER REGRESSION DIAGNOSIS")
    print("=" * 80)
    
    party_manager = PartyManager()
    
    with sync_playwright() as p:
        try:
            # Open browser
            print("\nOpening browser...")
            browser, context, page = open_logged_in_browser(p, DESTINATION_STATE_FILE)
            print("[SUCCESS] Browser opened")
            
            # ISSUE 1: Check cached parties before refresh
            print("\n" + "=" * 80)
            print("ISSUE 1: LIVE PARTY DISAPPEARED")
            print("=" * 80)
            
            print("\nLoading cached parties...")
            cached_parties = party_manager.get_cached_parties()
            print(f"Found {len(cached_parties)} cached parties")
            
            cached_live = [p for p in cached_parties if p.is_live]
            print(f"Cached live parties: {len(cached_live)}")
            
            for party in cached_live[:5]:
                print(f"\n  Cached Live Party:")
                print(f"    ID: {party.party_id}")
                print(f"    Name: {party.name}")
                print(f"    URL: {party.url}")
                print(f"    is_live: {party.is_live}")
            
            # ISSUE 2: Check for "Party Invitations" in cache
            print("\n" + "=" * 80)
            print("ISSUE 2: SUSPICIOUS CACHE ENTRIES")
            print("=" * 80)
            
            suspicious = [p for p in cached_parties if "invitation" in p.name.lower() or 
                         "happening now" in p.name.lower() or
                         "shop past" in p.name.lower()]
            
            if suspicious:
                print(f"\n[ERROR] Found {len(suspicious)} suspicious cache entries:")
                for party in suspicious:
                    print(f"  - {party.name} (ID: {party.party_id})")
            else:
                print("\n[SUCCESS] No suspicious cache entries found")
            
            # Fresh discovery
            print("\n" + "=" * 80)
            print("FRESH PARTY DISCOVERY")
            print("=" * 80)
            
            print("\nNavigating to parties page...")
            page.goto("https://poshmark.com/parties", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            
            print("\nDiscovering fresh parties...")
            fresh_parties = party_manager.discover_parties(page)
            print(f"Discovered {len(fresh_parties)} fresh parties")
            
            # Check fresh live status
            fresh_live = [p for p in fresh_parties if p.is_live]
            print(f"Fresh live parties: {len(fresh_live)}")
            
            print("\nFresh party live status:")
            for party in fresh_parties[:10]:
                print(f"\n  {party.name}")
                print(f"    ID: {party.party_id}")
                print(f"    is_live: {party.is_live}")
                print(f"    URL: {party.url}")
            
            # ISSUE 4: Verify live status directly
            print("\n" + "=" * 80)
            print("ISSUE 4: VERIFY LIVE STATUS DIRECTLY")
            print("=" * 80)
            
            # Check first party that might be live
            if fresh_parties:
                test_party = fresh_parties[0]
                print(f"\nTesting party: {test_party.name}")
                print(f"  Fresh is_live: {test_party.is_live}")
                
                print(f"\nNavigating to party page: {test_party.url}")
                page.goto(test_party.url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                
                # Check for "Ends in" evidence
                page_text = page.evaluate("() => document.body.textContent")
                has_ends_in = "ends in" in page_text.lower()
                has_live_now = "live now" in page_text.lower()
                has_happening_now = "happening now" in page_text.lower()
                
                print(f"\n  Authoritative evidence from party page:")
                print(f"    'Ends in': {has_ends_in}")
                print(f"    'Live now': {has_live_now}")
                print(f"    'Happening now': {has_happening_now}")
                
                if has_ends_in or has_live_now or has_happening_now:
                    print(f"\n  [ERROR] Party IS live but is_live={test_party.is_live}")
                    print(f"  Fresh discovery is not detecting live status correctly")
                else:
                    print(f"\n  [INFO] Party is not currently live")
            
            # Cache merge analysis
            print("\n" + "=" * 80)
            print("CACHE MERGE ANALYSIS")
            print("=" * 80)
            
            print("\nMerging fresh parties with cache...")
            merged_parties = party_manager.cache.merge_fresh_parties(
                cached_parties,
                fresh_parties,
                page
            )
            
            print(f"Merged {len(merged_parties)} parties")
            
            # Compare live status before/after merge
            print("\nLive status comparison:")
            for fresh_party in fresh_parties[:5]:
                party_id = fresh_party.party_id
                
                # Find in cached
                cached_party = next((p for p in cached_parties if p.party_id == party_id), None)
                
                # Find in merged
                merged_party = next((p for p in merged_parties if p.party_id == party_id), None)
                
                if cached_party or merged_party:
                    print(f"\n  {fresh_party.name[:50]}")
                    print(f"    party_id: {party_id}")
                    print(f"    Fresh is_live: {fresh_party.is_live}")
                    if cached_party:
                        print(f"    Cached is_live: {cached_party.is_live}")
                    if merged_party:
                        print(f"    Merged is_live: {merged_party.is_live}")
                    
                    # Check if merge overwrote fresh live status
                    if merged_party and fresh_party.is_live != merged_party.is_live:
                        print(f"    [ERROR] Merge changed is_live from {fresh_party.is_live} to {merged_party.is_live}")
            
            # ISSUE 3: Test upcoming guideline extraction
            print("\n" + "=" * 80)
            print("ISSUE 3: UPCOMING GUIDELINE EXTRACTION")
            print("=" * 80)
            
            # Find an upcoming party
            upcoming_parties = [p for p in fresh_parties if not p.is_live and not p.guidelines]
            
            if upcoming_parties:
                test_upcoming = upcoming_parties[0]
                print(f"\nTesting upcoming party: {test_upcoming.name}")
                print(f"  URL: {test_upcoming.url}")
                
                print("\nAttempting to load guidelines...")
                guidelines = party_manager.load_guidelines(page, test_upcoming)
                
                if guidelines:
                    print(f"\n[SUCCESS] Guidelines loaded:")
                    print(f"  Theme: {guidelines.theme}")
                    print(f"  Brands: {guidelines.brands_allowed}")
                    print(f"  Categories: {guidelines.categories_allowed}")
                else:
                    print(f"\n[ERROR] Guidelines extraction failed")
                    print(f"  This is the regression - upcoming parties should parse")
            
            print("\n" + "=" * 80)
            print("DIAGNOSIS COMPLETE")
            print("=" * 80)
            
        finally:
            browser.close()


if __name__ == "__main__":
    main()
