"""
Test Party Manager functionality.

Tests:
A. Discover unique parties (verify no duplicate URLs)
B. Load Men's Style live guidelines
C. Classify Men's Style => CATEGORY_LIMITED
D. Eligibility examples:
   - Available Men's listing => ELIGIBLE
   - Available Women's listing => INELIGIBLE
   - Unavailable Men's listing => INELIGIBLE
E. Universal party example (Brands All + Categories All) => UNIVERSAL

Usage:
    python tools/test_party_manager.py
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
from scraper.availability import AvailabilityStatus
from party import (
    PartyManager,
    PartyType,
    PartyEligibilityStatus,
    PartyGuidelines,
    classify_party_type,
    is_listing_eligible_for_party,
)


def print_header(text: str) -> None:
    """Print a test section header."""
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80)


def print_result(test_name: str, passed: bool, details: str = "") -> None:
    """Print test result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  {details}")


def test_discover_unique_parties(manager: PartyManager, page) -> bool:
    """
    Test A: Discover unique parties (verify no duplicate URLs).
    """
    print_header("TEST A: DISCOVER UNIQUE PARTIES")
    
    print("\nNavigating to parties page...")
    parties = manager.discover_parties(page)
    
    print(f"Discovered {len(parties)} parties")
    
    # Check for duplicates
    urls = [party.url for party in parties]
    unique_urls = set(urls)
    
    has_duplicates = len(urls) != len(unique_urls)
    
    if has_duplicates:
        print("\n[FAIL] DUPLICATE URLs FOUND:")
        seen = set()
        for url in urls:
            if url in seen:
                print(f"  - {url}")
            seen.add(url)
        return False
    
    print("\n[PASS] All party URLs are unique")
    
    # Print sample parties
    print("\nSample parties:")
    for i, party in enumerate(parties[:5]):
        print(f"\n  Party {i + 1}:")
        print(f"    Name: {party.name}")
        print(f"    URL: {party.url}")
        print(f"    Time: {party.start_time_text}")
        print(f"    Live: {party.is_live}")
        print(f"    ID: {party.party_id}")
    
    return True


def test_load_mens_style_guidelines(manager: PartyManager, page, parties) -> tuple[bool, PartyGuidelines | None]:
    """
    Test B: Load Men's Style live guidelines.
    Expected: Theme="Men's Style Posh Party", Brands=["All"], Categories=["Men"]
    """
    print_header("TEST B: LOAD MEN'S STYLE GUIDELINES")
    
    # Find Men's Style party
    mens_party = None
    for party in parties:
        if "men" in party.name.lower() and "style" in party.name.lower():
            mens_party = party
            break
    
    if not mens_party:
        print("\n[FAIL] Men's Style party not found in party list")
        print("Available parties:")
        for party in parties:
            print(f"  - {party.name}")
        return False, None
    
    print(f"\nFound party: {mens_party.name}")
    print(f"URL: {mens_party.url}")
    print(f"Live (before loading guidelines): {mens_party.is_live}")
    
    # Load guidelines
    print("\nLoading guidelines...")
    guidelines = manager.load_guidelines(page, mens_party)
    
    # Check live status after loading guidelines
    print(f"Live (after loading guidelines): {mens_party.is_live}")
    
    if not guidelines:
        print("\n[FAIL] Failed to load guidelines")
        return False, None
    
    print("\n[PASS] Guidelines loaded successfully")
    print(f"\n  Theme: {guidelines.theme}")
    print(f"  Brands Allowed: {guidelines.brands_allowed}")
    print(f"  Categories Allowed: {guidelines.categories_allowed}")
    print(f"  Departments Allowed: {guidelines.departments_allowed if guidelines.departments_allowed else []}")
    print(f"  Sizes Allowed: {guidelines.sizes_allowed if guidelines.sizes_allowed else []}")
    print(f"  Other Rules: {len(guidelines.other_rules)} rules")
    
    # Show exact parsed values for verification
    print("\n  EXACT PARSED VALUES:")
    print(f"    brands_allowed = {repr(guidelines.brands_allowed)}")
    print(f"    categories_allowed = {repr(guidelines.categories_allowed)}")
    print(f"    departments_allowed = {repr(guidelines.departments_allowed)}")
    print(f"    sizes_allowed = {repr(guidelines.sizes_allowed)}")
    
    # Verify expected values
    expected_checks = []
    
    # Check theme contains "Men's Style"
    theme_ok = "men" in guidelines.theme.lower() and "style" in guidelines.theme.lower()
    expected_checks.append(("Theme contains 'Men's Style'", theme_ok))
    
    # Check brands = ["All"]
    brands_ok = guidelines.brands_allowed == ["All"] or (len(guidelines.brands_allowed) == 1 and guidelines.brands_allowed[0].lower() == "all")
    expected_checks.append(("Brands = ['All']", brands_ok))
    
    # Check categories = ["Men"]
    categories_ok = guidelines.categories_allowed == ["Men"] or (len(guidelines.categories_allowed) == 1 and guidelines.categories_allowed[0].lower() == "men")
    expected_checks.append(("Categories = ['Men']", categories_ok))
    
    # Check sizes = [] (empty, no restriction)
    sizes_ok = len(guidelines.sizes_allowed) == 0
    expected_checks.append(("Sizes = [] (no restriction)", sizes_ok))
    
    # Check departments = [] (empty, field absent)
    departments_ok = len(guidelines.departments_allowed) == 0
    expected_checks.append(("Departments = [] (field absent)", departments_ok))
    
    print("\nValidation:")
    all_ok = True
    for check_name, check_result in expected_checks:
        status = "[OK]" if check_result else "[X]"
        print(f"  {status} {check_name}")
        if not check_result:
            all_ok = False
    
    return all_ok, guidelines


def test_classify_mens_style(guidelines: PartyGuidelines) -> bool:
    """
    Test C: Classify Men's Style => CATEGORY_LIMITED
    """
    print_header("TEST C: CLASSIFY MEN'S STYLE PARTY TYPE")
    
    party_type = classify_party_type(guidelines)
    
    print(f"\nClassified as: {party_type.value}")
    
    expected = PartyType.CATEGORY_LIMITED
    passed = party_type == expected
    
    if passed:
        print(f"[PASS] Correct classification (expected: {expected.value})")
    else:
        print(f"[FAIL] Incorrect classification (expected: {expected.value}, got: {party_type.value})")
    
    return passed


def test_eligibility_examples(mens_party) -> bool:
    """
    Test D: Eligibility examples.
    """
    print_header("TEST D: ELIGIBILITY EXAMPLES")
    
    all_passed = True
    
    # Example 1: Available Men's listing => ELIGIBLE
    print("\n--- Example 1: Available Men's listing ---")
    listing1 = {
        "availability": AvailabilityStatus.AVAILABLE,
        "brand": "Nike",
        "department": "Men",
        "category": "Shirts",
        "subcategory": "T-Shirts",
        "size": "L",
    }
    
    result1 = is_listing_eligible_for_party(listing1, mens_party)
    
    print(f"Status: {result1.status.value}")
    print(f"Reason: {result1.reason}")
    
    expected1 = PartyEligibilityStatus.ELIGIBLE
    passed1 = result1.status == expected1
    
    if passed1:
        print("[PASS] Available Men's listing is ELIGIBLE")
    else:
        print(f"[FAIL] Expected {expected1.value}, got {result1.status.value}")
        all_passed = False
    
    # Example 2: Available Women's listing => INELIGIBLE
    print("\n--- Example 2: Available Women's listing ---")
    listing2 = {
        "availability": AvailabilityStatus.AVAILABLE,
        "brand": "Zara",
        "department": "Women",
        "category": "Dresses",
        "subcategory": "Maxi Dresses",
        "size": "M",
    }
    
    result2 = is_listing_eligible_for_party(listing2, mens_party)
    
    print(f"Status: {result2.status.value}")
    print(f"Reason: {result2.reason}")
    
    expected2 = PartyEligibilityStatus.INELIGIBLE
    passed2 = result2.status == expected2
    
    if passed2:
        print("[PASS] Available Women's listing is INELIGIBLE")
    else:
        print(f"[FAIL] Expected {expected2.value}, got {result2.status.value}")
        all_passed = False
    
    # Example 3: Unavailable Men's listing => INELIGIBLE
    print("\n--- Example 3: Unavailable Men's listing ---")
    listing3 = {
        "availability": AvailabilityStatus.SOLD,
        "brand": "Adidas",
        "department": "Men",
        "category": "Shoes",
        "subcategory": "Sneakers",
        "size": "10",
    }
    
    result3 = is_listing_eligible_for_party(listing3, mens_party)
    
    print(f"Status: {result3.status.value}")
    print(f"Reason: {result3.reason}")
    
    expected3 = PartyEligibilityStatus.INELIGIBLE
    passed3 = result3.status == expected3
    
    if passed3:
        print("[PASS] Unavailable Men's listing is INELIGIBLE")
    else:
        print(f"[FAIL] Expected {expected3.value}, got {result3.status.value}")
        all_passed = False
    
    return all_passed


def test_universal_party() -> bool:
    """
    Test E: Universal party example (Brands All + Categories All) => UNIVERSAL
    """
    print_header("TEST E: UNIVERSAL PARTY CLASSIFICATION")
    
    # Create universal party guidelines
    universal_guidelines = PartyGuidelines(
        theme="Campus Debut",
        brands_allowed=["All"],
        categories_allowed=["All"],
        departments_allowed=[],
        sizes_allowed=[],
        other_rules=[],
    )
    
    party_type = classify_party_type(universal_guidelines)
    
    print(f"\nGuidelines:")
    print(f"  Brands: {', '.join(universal_guidelines.brands_allowed)}")
    print(f"  Categories: {', '.join(universal_guidelines.categories_allowed)}")
    print(f"\nClassified as: {party_type.value}")
    
    expected = PartyType.UNIVERSAL
    passed = party_type == expected
    
    if passed:
        print(f"[PASS] Correct classification (expected: {expected.value})")
    else:
        print(f"[FAIL] Expected {expected.value}, got {party_type.value}")
    
    return passed


def main():
    """Run all tests."""
    print_header("PARTY MANAGER TEST SUITE")
    print("\nThis test suite validates:")
    print("  A. Party discovery (no duplicates)")
    print("  B. Guidelines loading (Men's Style)")
    print("  C. Party type classification")
    print("  D. Eligibility checking")
    print("  E. Universal party classification")
    
    print("\nStarting browser...")
    
    test_results = []
    
    with sync_playwright() as p:
        browser, context, page = open_logged_in_browser(
            p,
            DESTINATION_STATE_FILE,
        )
        
        try:
            manager = PartyManager()
            
            # Test A: Discover parties
            test_a_passed = test_discover_unique_parties(manager, page)
            test_results.append(("A. Discover unique parties", test_a_passed))
            
            # Get parties for subsequent tests
            parties = manager.discover_parties(page)
            
            if not parties:
                print("\n[ERROR] No parties discovered. Cannot continue tests.")
                browser.close()
                return
            
            # Test B: Load Men's Style guidelines
            test_b_passed, mens_guidelines = test_load_mens_style_guidelines(manager, page, parties)
            test_results.append(("B. Load Men's Style guidelines", test_b_passed))
            
            if not mens_guidelines:
                print("\n[ERROR] Could not load Men's Style guidelines. Skipping remaining tests.")
                browser.close()
                return
            
            # Test C: Classify Men's Style
            test_c_passed = test_classify_mens_style(mens_guidelines)
            test_results.append(("C. Classify Men's Style", test_c_passed))
            
            # Find Men's party object for eligibility tests
            mens_party = None
            for party in parties:
                if "men" in party.name.lower() and "style" in party.name.lower():
                    mens_party = party
                    break
            
            if mens_party and mens_party.guidelines:
                # Test D: Eligibility examples
                test_d_passed = test_eligibility_examples(mens_party)
                test_results.append(("D. Eligibility examples", test_d_passed))
            else:
                print("\n[ERROR] Men's party not available for eligibility tests")
                test_results.append(("D. Eligibility examples", False))
            
            # Test E: Universal party (no browser needed)
            test_e_passed = test_universal_party()
            test_results.append(("E. Universal party classification", test_e_passed))
            
            # Print summary
            print_header("TEST SUMMARY")
            
            passed_count = sum(1 for _, passed in test_results if passed)
            total_count = len(test_results)
            
            print(f"\nResults: {passed_count}/{total_count} tests passed\n")
            
            for test_name, passed in test_results:
                status = "[PASS]" if passed else "[FAIL]"
                print(f"  {status}: {test_name}")
            
            # Print live detection evidence
            if mens_party:
                print("\n" + "=" * 80)
                print("LIVE DETECTION EVIDENCE")
                print("=" * 80)
                print(f"\nMen's Style Party:")
                print(f"  is_live: {mens_party.is_live}")
                print(f"  start_time_text: {mens_party.start_time_text}")
                print(f"  DOM evidence: Live status detected from party detail page")
                print(f"    (Checked for: 'Ends in', 'Live now', 'Happening now')")
            
            if passed_count == total_count:
                print("\n*** All tests passed! ***")
            else:
                print(f"\n*** WARNING: {total_count - passed_count} test(s) failed ***")
            
            print("\nClosing browser in 3 seconds...")
            page.wait_for_timeout(3000)
            
        except Exception as e:
            print(f"\n\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
