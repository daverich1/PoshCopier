"""
Live cache test for party cache implementation (TASK-026B).

Tests cache with actual party data (no browser interaction).
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from party.party_models import (
    PartyType,
    PartyGuidelines,
    PoshParty,
    GuidelineParseConfidence,
)
from party.cache import PartyCacheManager


def test_live_cache():
    """Test cache with realistic party data."""
    print("\n" + "=" * 80)
    print("LIVE CACHE TEST")
    print("=" * 80)
    
    cache = PartyCacheManager()
    
    # Create realistic test parties
    parties = []
    
    # 1. Campus Debut (upcoming universal party)
    parties.append(PoshParty(
        party_id="campus-debut",
        name="Campus Debut Posh Party",
        url="https://poshmark.com/party/campus-debut",
        start_time_text="Today at 7:00 PM",
        start_at=None,
        is_live=False,
        guidelines=PartyGuidelines(
            theme="Campus Debut",
            brands_allowed=["All"],
            categories_allowed=["All"],
            departments_allowed=[],
            sizes_allowed=[],
            other_rules=[],
            parse_confidence=GuidelineParseConfidence.HIGH,
            parsed_at=datetime.now(),
        ),
        party_type=PartyType.UNIVERSAL,
    ))
    
    # 2. Best in Shoes (category limited)
    parties.append(PoshParty(
        party_id="best-in-shoes",
        name="Best in Shoes Posh Party",
        url="https://poshmark.com/party/best-in-shoes",
        start_time_text="Tomorrow at 3:00 PM",
        start_at=None,
        is_live=False,
        guidelines=PartyGuidelines(
            theme="Best in Shoes",
            brands_allowed=["All"],
            categories_allowed=["Shoes", "Boots", "Sneakers"],
            departments_allowed=["Women", "Men"],
            sizes_allowed=[],
            other_rules=[],
            parse_confidence=GuidelineParseConfidence.HIGH,
            parsed_at=datetime.now(),
        ),
        party_type=PartyType.CATEGORY_LIMITED,
    ))
    
    # 3. Designer Handbags (brand limited)
    parties.append(PoshParty(
        party_id="designer-handbags",
        name="Designer Handbags Posh Party",
        url="https://poshmark.com/party/designer-handbags",
        start_time_text="Today at 10:00 AM",
        start_at=None,
        is_live=True,
        guidelines=PartyGuidelines(
            theme="Designer Handbags",
            brands_allowed=["Louis Vuitton", "Gucci", "Chanel", "Prada"],
            categories_allowed=["All"],
            departments_allowed=["Women"],
            sizes_allowed=[],
            other_rules=[],
            parse_confidence=GuidelineParseConfidence.HIGH,
            parsed_at=datetime.now(),
        ),
        party_type=PartyType.BRAND_LIMITED,
    ))
    
    print(f"\n[STEP 1] Saving {len(parties)} parties to cache...")
    success = cache.save(parties)
    assert success, "Cache save failed"
    print("[PASS] Cache saved successfully")
    
    print("\n[STEP 2] Loading parties from cache...")
    loaded_parties = cache.load()
    assert len(loaded_parties) == len(parties), f"Expected {len(parties)} parties, got {len(loaded_parties)}"
    print(f"[PASS] Loaded {len(loaded_parties)} parties")
    
    print("\n[STEP 3] Verifying party IDs are unique...")
    party_ids = [p.party_id for p in loaded_parties]
    assert len(party_ids) == len(set(party_ids)), "Duplicate party IDs found"
    print("[PASS] All party IDs are unique")
    
    print("\n[STEP 4] Verifying Campus Debut is present...")
    campus_debut = next((p for p in loaded_parties if p.party_id == "campus-debut"), None)
    assert campus_debut is not None, "Campus Debut not found"
    print("[PASS] Campus Debut found")
    
    print("\n[STEP 5] Verifying Campus Debut guidelines are cached...")
    assert campus_debut.guidelines is not None, "Campus Debut guidelines not cached"
    assert campus_debut.guidelines.brands_allowed == ["All"]
    assert campus_debut.guidelines.categories_allowed == ["All"]
    assert campus_debut.party_type == PartyType.UNIVERSAL
    print("[PASS] Campus Debut guidelines cached correctly")
    
    print("\n[STEP 6] Verifying Campus Debut live/upcoming state...")
    assert campus_debut.is_live == False, "Campus Debut should be upcoming"
    print(f"[PASS] Campus Debut is_live={campus_debut.is_live} (upcoming)")
    
    print("\n[STEP 7] Simulating Campus Debut going live...")
    # Fresh metadata: party is now live
    fresh_campus = PoshParty(
        party_id="campus-debut",
        name="Campus Debut Posh Party",
        url="https://poshmark.com/party/campus-debut",
        start_time_text="Ends in 2:45",
        start_at=datetime.now(),
        is_live=True,  # NOW LIVE
        guidelines=None,
        party_type=PartyType.UNKNOWN,
    )
    
    # Merge with cache
    merged = cache.merge_fresh_parties(loaded_parties, [fresh_campus])
    updated_campus = merged[0]
    
    # Verify metadata updated
    assert updated_campus.is_live == True, "is_live should be updated"
    assert updated_campus.start_time_text == "Ends in 2:45", "time text should be updated"
    print("[PASS] Metadata updated (is_live=True)")
    
    # Verify guidelines preserved
    assert updated_campus.guidelines is not None, "Guidelines should be preserved"
    assert updated_campus.guidelines.brands_allowed == ["All"]
    assert updated_campus.party_type == PartyType.UNIVERSAL
    print("[PASS] Guidelines preserved from cache")
    
    print("\n[STEP 8] Displaying cached parties...")
    print("\nCached Parties:")
    print("-" * 80)
    for i, party in enumerate(loaded_parties, 1):
        print(f"\n{i}. {party.name}")
        print(f"   ID: {party.party_id}")
        print(f"   Type: {party.party_type.value}")
        print(f"   Live: {party.is_live}")
        if party.guidelines:
            print(f"   Brands: {party.guidelines.brands_allowed[:3]}{'...' if len(party.guidelines.brands_allowed) > 3 else ''}")
            print(f"   Categories: {party.guidelines.categories_allowed[:3]}{'...' if len(party.guidelines.categories_allowed) > 3 else ''}")
            print(f"   Confidence: {party.guidelines.parse_confidence.value}")
    
    print("\n" + "=" * 80)
    print("[OK] LIVE CACHE TEST PASSED")
    print("=" * 80)
    
    return True


def display_sample_cache_entry():
    """Display a sample cache entry."""
    print("\n" + "=" * 80)
    print("SAMPLE CACHE ENTRY")
    print("=" * 80)
    
    sample = {
        "party_id": "campus-debut",
        "name": "Campus Debut Posh Party",
        "url": "https://poshmark.com/party/campus-debut",
        "start_time_text": "Today at 7:00 PM",
        "start_at": None,
        "is_live": False,
        "party_type": "universal",
        "guidelines": {
            "theme": "Campus Debut",
            "brands_allowed": ["All"],
            "categories_allowed": ["All"],
            "departments_allowed": [],
            "sizes_allowed": [],
            "other_rules": [],
            "extra_fields": {},
            "parse_confidence": "high",
            "parsed_at": "2026-08-08T00:00:00"
        }
    }
    
    import json
    print(json.dumps(sample, indent=2))
    print("=" * 80)


if __name__ == "__main__":
    try:
        success = test_live_cache()
        display_sample_cache_entry()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n[FAIL] Live cache test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
