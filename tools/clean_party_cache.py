"""
Clean corrupted party cache entries.

Removes parties with invalid names like:
- "Party Invitations" (section heading)
- "Happening Now" (section heading)
- "Shop Past Parties" (section heading)
- Other suspicious entries

Usage:
    python tools/clean_party_cache.py [--auto]
    
    --auto: Automatically clean without confirmation
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from party.cache import PartyCacheManager


# Invalid party names to remove
INVALID_NAMES = [
    "party invitations",
    "happening now",
    "shop past parties",
    "past parties",
    "unknown party",
    "join this party",
    "view party",
    "view party details",
]


def is_valid_party_name(name: str) -> bool:
    """
    Check if party name is valid.
    
    Invalid names:
    - Section headings
    - Status text
    - CTA text
    - Generic placeholders
    
    Args:
        name: Party name to validate
        
    Returns:
        True if valid, False if invalid
    """
    name_lower = name.lower().strip()
    
    # Check against known invalid names
    if name_lower in INVALID_NAMES:
        return False
    
    # Check if it starts with invalid text
    for invalid in INVALID_NAMES:
        if name_lower.startswith(invalid):
            return False
    
    # Valid party names should contain "Posh Party" or be descriptive
    # But we'll be lenient and just reject known bad patterns
    return True


def main():
    """Clean corrupted party cache."""
    print("=" * 80)
    print("PARTY CACHE CLEANUP")
    print("=" * 80)
    
    cache = PartyCacheManager()
    
    # Load current cache
    print("\nLoading cache...")
    parties = cache.load()
    print(f"Found {len(parties)} cached parties")
    
    # Identify invalid entries
    invalid_parties = []
    valid_parties = []
    
    for party in parties:
        if is_valid_party_name(party.name):
            valid_parties.append(party)
        else:
            invalid_parties.append(party)
    
    # Report findings
    print(f"\nValid parties: {len(valid_parties)}")
    print(f"Invalid parties: {len(invalid_parties)}")
    
    if invalid_parties:
        print("\nInvalid parties to be removed:")
        for party in invalid_parties:
            print(f"  - {party.name} (ID: {party.party_id})")
        
        # Check for auto mode
        auto_mode = "--auto" in sys.argv
        
        if auto_mode:
            print("\n[AUTO MODE] Cleaning cache automatically...")
            should_clean = True
        else:
            # Confirm cleanup
            print("\n" + "=" * 80)
            response = input("Remove invalid parties from cache? (yes/no): ").strip().lower()
            should_clean = response in ["yes", "y"]
        
        if should_clean:
            # Save cleaned cache
            success = cache.save(valid_parties)
            
            if success:
                print(f"\n[SUCCESS] Cache cleaned: {len(invalid_parties)} invalid parties removed")
                print(f"[SUCCESS] {len(valid_parties)} valid parties retained")
            else:
                print("\n[ERROR] Failed to save cleaned cache")
        else:
            print("\n[CANCELLED] Cache not modified")
    else:
        print("\n[SUCCESS] No invalid parties found - cache is clean!")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
