"""
Comprehensive tests for party cache implementation (TASK-026B).

Tests:
A. Save/load round trip
B. Guidelines exact serialization
C. PartyType exact serialization
D. Fresh/stale detection
E. Corrupt JSON safe failure
F. Missing cache safe failure
G. Upcoming universal party cached
H. Live state changes while guidelines remain cached
I. Fresh metadata updates while valid cached guidelines are reused
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from party.party_models import (
    PartyType,
    PartyGuidelines,
    PoshParty,
    GuidelineParseConfidence,
)
from party.cache import PartyCacheManager


def test_a_save_load_round_trip():
    """Test A: Save/load round trip."""
    print("\n" + "=" * 80)
    print("TEST A: Save/Load Round Trip")
    print("=" * 80)
    
    # Create temporary cache file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Create test parties
        guidelines = PartyGuidelines(
            theme="Test Party",
            brands_allowed=["Nike", "Adidas"],
            categories_allowed=["Shoes", "Athletic"],
            departments_allowed=["Women"],
            sizes_allowed=["8", "9", "10"],
            other_rules=["New with tags only"],
            extra_fields={"Colors Allowed": ["Red", "Blue"]},
            parse_confidence=GuidelineParseConfidence.HIGH,
            parsed_at=datetime.now(),
        )
        
        parties = [
            PoshParty(
                party_id="test-party-1",
                name="Test Party 1",
                url="https://poshmark.com/party/test-party-1",
                start_time_text="Today at 7:00 PM",
                start_at=datetime.now(),
                is_live=True,
                guidelines=guidelines,
                party_type=PartyType.MIXED,
            )
        ]
        
        # Save
        success = cache.save(parties)
        assert success, "Save failed"
        print("[PASS] Save succeeded")
        
        # Load
        loaded_parties = cache.load()
        assert len(loaded_parties) == 1, f"Expected 1 party, got {len(loaded_parties)}"
        print("[PASS] Load succeeded")
        
        # Verify data
        loaded = loaded_parties[0]
        assert loaded.party_id == "test-party-1"
        assert loaded.name == "Test Party 1"
        assert loaded.is_live == True
        assert loaded.party_type == PartyType.MIXED
        print("[PASS] Basic fields match")
        
        # Verify guidelines
        assert loaded.guidelines is not None
        assert loaded.guidelines.theme == "Test Party"
        assert loaded.guidelines.brands_allowed == ["Nike", "Adidas"]
        assert loaded.guidelines.categories_allowed == ["Shoes", "Athletic"]
        assert loaded.guidelines.parse_confidence == GuidelineParseConfidence.HIGH
        assert loaded.guidelines.extra_fields == {"Colors Allowed": ["Red", "Blue"]}
        print("[PASS] Guidelines match")
        
        print("\n[OK] TEST A PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_b_guidelines_exact_serialization():
    """Test B: Guidelines exact serialization."""
    print("\n" + "=" * 80)
    print("TEST B: Guidelines Exact Serialization")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Test all guideline fields
        guidelines = PartyGuidelines(
            theme="Complete Test",
            brands_allowed=["All"],
            categories_allowed=["Shoes", "Bags"],
            departments_allowed=["Women", "Men"],
            sizes_allowed=["S", "M", "L"],
            other_rules=["Rule 1", "Rule 2"],
            extra_fields={
                "Colors Allowed": ["Red", "Blue", "Green"],
                "Brands Excluded": ["Brand X"],
                "Conditions Allowed": ["New", "Like New"],
            },
            parse_confidence=GuidelineParseConfidence.MEDIUM,
            parsed_at=datetime(2026, 8, 8, 12, 0, 0),
        )
        
        party = PoshParty(
            party_id="test-guidelines",
            name="Guidelines Test",
            url="https://poshmark.com/party/test-guidelines",
            start_time_text="Today at 3:00 PM",
            start_at=None,
            is_live=False,
            guidelines=guidelines,
            party_type=PartyType.CATEGORY_LIMITED,
        )
        
        # Save and load
        cache.save([party])
        loaded = cache.load()[0]
        
        # Verify exact match
        g = loaded.guidelines
        assert g.theme == "Complete Test"
        assert g.brands_allowed == ["All"]
        assert g.categories_allowed == ["Shoes", "Bags"]
        assert g.departments_allowed == ["Women", "Men"]
        assert g.sizes_allowed == ["S", "M", "L"]
        assert g.other_rules == ["Rule 1", "Rule 2"]
        assert g.extra_fields == {
            "Colors Allowed": ["Red", "Blue", "Green"],
            "Brands Excluded": ["Brand X"],
            "Conditions Allowed": ["New", "Like New"],
        }
        assert g.parse_confidence == GuidelineParseConfidence.MEDIUM
        assert g.parsed_at == datetime(2026, 8, 8, 12, 0, 0)
        print("[PASS] All guideline fields serialized exactly")
        
        print("\n[OK] TEST B PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_c_party_type_exact_serialization():
    """Test C: PartyType exact serialization."""
    print("\n" + "=" * 80)
    print("TEST C: PartyType Exact Serialization")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Test all party types
        party_types = [
            PartyType.UNIVERSAL,
            PartyType.CATEGORY_LIMITED,
            PartyType.BRAND_LIMITED,
            PartyType.MIXED,
            PartyType.UNKNOWN,
        ]
        
        parties = []
        for i, party_type in enumerate(party_types):
            party = PoshParty(
                party_id=f"test-type-{i}",
                name=f"Type Test {party_type.value}",
                url=f"https://poshmark.com/party/test-type-{i}",
                start_time_text="Today at 7:00 PM",
                start_at=None,
                is_live=False,
                guidelines=None,
                party_type=party_type,
            )
            parties.append(party)
        
        # Save and load
        cache.save(parties)
        loaded_parties = cache.load()
        
        # Verify all types
        for i, party_type in enumerate(party_types):
            assert loaded_parties[i].party_type == party_type
            print(f"[PASS] {party_type.value} serialized correctly")
        
        print("\n[OK] TEST C PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_d_fresh_stale_detection():
    """Test D: Fresh/stale detection."""
    print("\n" + "=" * 80)
    print("TEST D: Fresh/Stale Detection")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        now = datetime.now()
        
        # Create parties with different ages
        parties = []
        
        # Fresh HIGH confidence (1 hour old)
        parties.append(PoshParty(
            party_id="fresh-high",
            name="Fresh High",
            url="https://poshmark.com/party/fresh-high",
            start_time_text="Today at 7:00 PM",
            start_at=None,
            is_live=False,
            guidelines=PartyGuidelines(
                theme="Fresh",
                brands_allowed=["All"],
                categories_allowed=["All"],
                departments_allowed=[],
                sizes_allowed=[],
                other_rules=[],
                parse_confidence=GuidelineParseConfidence.HIGH,
                parsed_at=now - timedelta(hours=1),
            ),
            party_type=PartyType.UNIVERSAL,
        ))
        
        # Stale HIGH confidence (25 hours old)
        parties.append(PoshParty(
            party_id="stale-high",
            name="Stale High",
            url="https://poshmark.com/party/stale-high",
            start_time_text="Today at 7:00 PM",
            start_at=None,
            is_live=False,
            guidelines=PartyGuidelines(
                theme="Stale",
                brands_allowed=["All"],
                categories_allowed=["All"],
                departments_allowed=[],
                sizes_allowed=[],
                other_rules=[],
                parse_confidence=GuidelineParseConfidence.HIGH,
                parsed_at=now - timedelta(hours=25),
            ),
            party_type=PartyType.UNIVERSAL,
        ))
        
        # LOW confidence (always stale)
        parties.append(PoshParty(
            party_id="low-confidence",
            name="Low Confidence",
            url="https://poshmark.com/party/low-confidence",
            start_time_text="Today at 7:00 PM",
            start_at=None,
            is_live=False,
            guidelines=PartyGuidelines(
                theme="Low",
                brands_allowed=["All"],
                categories_allowed=["All"],
                departments_allowed=[],
                sizes_allowed=[],
                other_rules=[],
                parse_confidence=GuidelineParseConfidence.LOW,
                parsed_at=now - timedelta(hours=1),
            ),
            party_type=PartyType.UNIVERSAL,
        ))
        
        # Save
        cache.save(parties)
        
        # Check freshness
        loaded = cache.load()
        
        fresh_high = cache.is_guidelines_fresh(loaded[0])
        stale_high = cache.is_guidelines_fresh(loaded[1])
        low_conf = cache.is_guidelines_fresh(loaded[2])
        
        assert fresh_high == True, "Fresh HIGH should be fresh"
        print("[PASS] Fresh HIGH confidence detected as fresh")
        
        assert stale_high == False, "Stale HIGH should be stale"
        print("[PASS] Stale HIGH confidence detected as stale")
        
        assert low_conf == False, "LOW confidence should always be stale"
        print("[PASS] LOW confidence always stale")
        
        print("\n[OK] TEST D PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_e_corrupt_json_safe_failure():
    """Test E: Corrupt JSON safe failure."""
    print("\n" + "=" * 80)
    print("TEST E: Corrupt JSON Safe Failure")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
        f.write("{ invalid json }")
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Should not crash
        parties = cache.load()
        
        assert parties == [], "Should return empty list for corrupt JSON"
        print("[PASS] Corrupt JSON handled gracefully")
        
        print("\n[OK] TEST E PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_f_missing_cache_safe_failure():
    """Test F: Missing cache safe failure."""
    print("\n" + "=" * 80)
    print("TEST F: Missing Cache Safe Failure")
    print("=" * 80)
    
    # Use non-existent file
    temp_cache = "/tmp/nonexistent_cache_file_12345.json"
    
    cache = PartyCacheManager(cache_file=temp_cache)
    
    # Should not crash
    parties = cache.load()
    
    assert parties == [], "Should return empty list for missing file"
    print("[PASS] Missing cache handled gracefully")
    
    print("\n[OK] TEST F PASSED")


def test_g_upcoming_universal_party_cached():
    """Test G: Upcoming universal party cached."""
    print("\n" + "=" * 80)
    print("TEST G: Upcoming Universal Party Cached")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Campus Debut before it goes live
        party = PoshParty(
            party_id="campus-debut",
            name="Campus Debut Posh Party",
            url="https://poshmark.com/party/campus-debut",
            start_time_text="Today at 7:00 PM",
            start_at=datetime.now() + timedelta(hours=2),
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
        )
        
        # Save
        cache.save([party])
        print("[PASS] Upcoming universal party saved")
        
        # Load
        loaded = cache.load()[0]
        
        assert loaded.party_id == "campus-debut"
        assert loaded.is_live == False
        assert loaded.party_type == PartyType.UNIVERSAL
        assert loaded.guidelines.brands_allowed == ["All"]
        assert loaded.guidelines.categories_allowed == ["All"]
        print("[PASS] Upcoming universal party loaded correctly")
        
        print("\n[OK] TEST G PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_h_live_state_changes_guidelines_cached():
    """Test H: Live state changes while guidelines remain cached."""
    print("\n" + "=" * 80)
    print("TEST H: Live State Changes While Guidelines Remain Cached")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Initial: upcoming party
        cached_party = PoshParty(
            party_id="campus-debut",
            name="Campus Debut Posh Party",
            url="https://poshmark.com/party/campus-debut",
            start_time_text="Today at 7:00 PM",
            start_at=datetime.now() + timedelta(hours=2),
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
        )
        
        cache.save([cached_party])
        print("[PASS] Cached upcoming party")
        
        # Fresh: party is now live
        fresh_party = PoshParty(
            party_id="campus-debut",
            name="Campus Debut Posh Party",  # Same name
            url="https://poshmark.com/party/campus-debut",
            start_time_text="Ends in 2:59",  # Updated time text
            start_at=datetime.now(),
            is_live=True,  # NOW LIVE
            guidelines=None,  # Not loaded yet
            party_type=PartyType.UNKNOWN,
        )
        
        # Merge
        cached_parties = cache.load()
        merged = cache.merge_fresh_parties(cached_parties, [fresh_party])
        
        assert len(merged) == 1
        result = merged[0]
        
        # Metadata should be fresh
        assert result.is_live == True, "is_live should be updated"
        assert result.start_time_text == "Ends in 2:59", "time text should be updated"
        print("[PASS] Metadata updated from fresh party")
        
        # Guidelines should be reused
        assert result.guidelines is not None, "Guidelines should be reused"
        assert result.guidelines.brands_allowed == ["All"]
        assert result.guidelines.categories_allowed == ["All"]
        assert result.party_type == PartyType.UNIVERSAL
        print("[PASS] Guidelines reused from cache")
        
        print("\n[OK] TEST H PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def test_i_fresh_metadata_cached_guidelines():
    """Test I: Fresh metadata updates while valid cached guidelines are reused."""
    print("\n" + "=" * 80)
    print("TEST I: Fresh Metadata Updates While Valid Cached Guidelines Are Reused")
    print("=" * 80)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_cache = f.name
    
    try:
        cache = PartyCacheManager(cache_file=temp_cache)
        
        # Cached party
        cached_party = PoshParty(
            party_id="campus-debut",
            name="Campus Debut Posh Party (Old Name)",
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
        )
        
        cache.save([cached_party])
        
        # Fresh party with updated metadata
        fresh_party = PoshParty(
            party_id="campus-debut",
            name="Campus Debut Posh Party (New Name)",  # Updated name
            url="https://poshmark.com/party/campus-debut",
            start_time_text="Ends in 2:30",  # Updated time
            start_at=datetime.now(),
            is_live=True,  # Updated live status
            guidelines=None,
            party_type=PartyType.UNKNOWN,
        )
        
        # Merge
        cached_parties = cache.load()
        merged = cache.merge_fresh_parties(cached_parties, [fresh_party])
        
        result = merged[0]
        
        # All metadata should be fresh
        assert result.name == "Campus Debut Posh Party (New Name)"
        assert result.start_time_text == "Ends in 2:30"
        assert result.is_live == True
        print("[PASS] All metadata updated from fresh party")
        
        # Guidelines should be reused
        assert result.guidelines is not None
        assert result.guidelines.brands_allowed == ["All"]
        assert result.guidelines.categories_allowed == ["All"]
        assert result.party_type == PartyType.UNIVERSAL
        print("[PASS] Guidelines preserved from cache")
        
        print("\n[OK] TEST I PASSED")
        
    finally:
        if os.path.exists(temp_cache):
            os.remove(temp_cache)


def run_all_tests():
    """Run all unit tests."""
    print("\n" + "=" * 80)
    print("PARTY CACHE UNIT TESTS (TASK-026B)")
    print("=" * 80)
    
    tests = [
        ("A", test_a_save_load_round_trip),
        ("B", test_b_guidelines_exact_serialization),
        ("C", test_c_party_type_exact_serialization),
        ("D", test_d_fresh_stale_detection),
        ("E", test_e_corrupt_json_safe_failure),
        ("F", test_f_missing_cache_safe_failure),
        ("G", test_g_upcoming_universal_party_cached),
        ("H", test_h_live_state_changes_guidelines_cached),
        ("I", test_i_fresh_metadata_cached_guidelines),
    ]
    
    passed = 0
    failed = 0
    
    for test_id, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] TEST {test_id} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
