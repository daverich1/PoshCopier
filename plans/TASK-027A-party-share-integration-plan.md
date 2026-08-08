# TASK-027A: PartyManager Integration into share_engine.py

## Overview

Integrate PartyManager into the sharing workflow to enable sharing listings to eligible Poshmark parties in addition to followers.

## Current State Analysis

### Existing Components

1. **share_engine.py** (`PoshmarkShareEngine`)
   - Currently shares listings to followers only
   - Has methods: `share_listing()`, `_find_share_button()`, `_find_share_to_followers_option()`
   - Uses `ShareableListing` dataclass with: listing_id, url, title, available
   - Returns `ShareResult` with success/failure tracking

2. **PartyManager** (`party/party_manager.py`)
   - Discovers parties from parties page
   - Loads party guidelines (cached)
   - Filters for live parties
   - Integrated with `PartyCacheManager`

3. **Eligibility Engine** (`party/eligibility.py`)
   - `is_listing_eligible_for_party()` - checks if listing matches party guidelines
   - Returns `PartyEligibilityResult` with status (ELIGIBLE/INELIGIBLE/UNKNOWN)
   - **CRITICAL**: Only AVAILABLE listings can be eligible
   - **CRITICAL**: Never share if eligibility is UNKNOWN

4. **Party Models** (`party/party_models.py`)
   - `PoshParty` - party metadata + guidelines
   - `PartyGuidelines` - theme, brands, categories, etc.
   - `PartyEligibilityStatus` - ELIGIBLE/INELIGIBLE/UNKNOWN
   - `PartyType` - UNIVERSAL/CATEGORY_LIMITED/BRAND_LIMITED/MIXED/UNKNOWN

### Missing Components

1. **Party Share UI Selectors**
   - Need to discover selectors for party sharing in modal
   - Modal should show party list after clicking share button
   - Need to find party option elements and click them

2. **Listing Data Enrichment**
   - `ShareableListing` only has: listing_id, url, title, available
   - Eligibility engine needs: brand, department, category, subcategory, size
   - Need to load from inventory or scrape from listing page

3. **Share Logging**
   - Need structured logging for party shares
   - Track: listing, party, eligibility, action, result

## Implementation Plan

### Phase 1: Extend ShareableListing Model

**File**: `sharing/share_engine.py`

**Changes**:
```python
@dataclass
class ShareableListing:
    """
    Represents a listing that can be shared.
    
    Attributes:
        listing_id: Unique listing identifier
        url: Full URL to listing
        title: Listing title
        available: Whether listing is available for sale
        
        # Party eligibility fields (optional)
        brand: Brand name
        department: Department (Men/Women/Kids)
        category: Category
        subcategory: Subcategory
        size: Size
        availability: AvailabilityStatus enum
    """
    
    listing_id: str
    url: str
    title: str
    available: bool = True
    
    # Optional fields for party eligibility
    brand: str = ""
    department: str = ""
    category: str = ""
    subcategory: str = ""
    size: str = ""
    availability: AvailabilityStatus | None = None
```

### Phase 2: Add Party Share Methods

**File**: `sharing/share_engine.py`

**New Methods**:

1. **`_find_party_share_options()`**
   - After clicking share button and modal opens
   - Find party options in the modal
   - Return list of party elements with their text/names
   - Use multiple selector strategies (similar to existing methods)

2. **`_select_party_in_modal(party_name: str)`**
   - Find party option by name in modal
   - Click to select it
   - Wait for share to complete
   - Verify success

3. **`share_to_party(listing: ShareableListing, party: PoshParty)`**
   - Navigate to listing
   - Click share button
   - Wait for modal
   - Select party from modal
   - Click share/confirm
   - Verify success
   - Return ShareResult

### Phase 3: Integrate PartyManager

**File**: `sharing/share_engine.py`

**Changes to `__init__`**:
```python
def __init__(
    self,
    page: Page,
    config: ShareConfig,
    progress_callback: Callable[[ShareProgress], None] | None = None,
    party_manager: PartyManager | None = None,  # NEW
) -> None:
    self.page = page
    self.config = config
    self.progress_callback = progress_callback
    self.party_manager = party_manager  # NEW
```

**New Method**: `share_listing_with_parties()`
```python
def share_listing_with_parties(
    self,
    listing: ShareableListing,
    retry: bool = True,
) -> ShareResult:
    """
    Share a single listing to followers AND eligible parties.
    
    Workflow:
    1. Check availability (CRITICAL GATE)
    2. Share to followers (existing logic)
    3. Load party cache
    4. Refresh metadata if stale
    5. Get currently live parties
    6. For each live party:
       a. Run eligibility engine
       b. If ELIGIBLE: share to party
       c. If INELIGIBLE: skip with reason
       d. If UNKNOWN: skip (never share on UNKNOWN)
    7. Log all actions and results
    
    Returns:
        ShareResult with combined stats
    """
```

### Phase 4: Add Logging Infrastructure

**File**: `sharing/share_engine.py`

**New Dataclass**:
```python
@dataclass
class PartyShareLog:
    """Log entry for a party share attempt."""
    
    listing_id: str
    listing_title: str
    party_id: str
    party_name: str
    eligibility_status: PartyEligibilityStatus
    eligibility_reason: str
    action: str  # "shared", "skipped", "failed"
    result: str  # Success message or error
    timestamp: datetime
```

**New Method**: `_log_party_share()`
```python
def _log_party_share(self, log_entry: PartyShareLog) -> None:
    """
    Log party share attempt to console and/or file.
    
    Format:
    [PARTY SHARE] listing_id | party_name | eligibility | action | result
    """
```

### Phase 5: Selector Discovery for Party Sharing

**New File**: `tools/test_party_share_selectors.py`

**Purpose**: Discover selectors for party sharing UI

**Test Script**:
```python
"""
Discover selectors for sharing to parties in the share modal.

Process:
1. Navigate to a listing
2. Click share button
3. Wait for modal
4. Inspect modal structure
5. Find party options
6. Test clicking a party option
"""
```

## Workflow Implementation

### Single Listing Share with Parties

```python
# Pseudocode for share_listing_with_parties()

def share_listing_with_parties(listing, retry=True):
    # STEP 1: Availability gate
    if not listing.available or listing.availability != AvailabilityStatus.AVAILABLE:
        return ShareResult(
            success=False,
            skipped=1,
            message="Listing not available"
        )
    
    # STEP 2: Share to followers (existing logic)
    follower_result = self.share_listing(listing, retry)
    
    if not follower_result.success:
        return follower_result  # Stop if follower share failed
    
    # STEP 3: Party sharing (if PartyManager available)
    if not self.party_manager:
        return follower_result  # No party manager, return follower result
    
    # STEP 4: Load party cache
    cached_parties = self.party_manager.get_cached_parties()
    
    # STEP 5: Refresh metadata if stale (check cache age)
    # For now, use cached parties as-is
    
    # STEP 6: Get live parties
    live_parties = self.party_manager.get_live_parties(cached_parties)
    
    if not live_parties:
        print("  No live parties available")
        return follower_result
    
    # STEP 7: Check eligibility and share
    party_shared = 0
    party_skipped = 0
    party_failed = 0
    
    for party in live_parties:
        # Build listing dict for eligibility check
        listing_dict = {
            "availability": listing.availability,
            "brand": listing.brand,
            "department": listing.department,
            "category": listing.category,
            "subcategory": listing.subcategory,
            "size": listing.size,
        }
        
        # Check eligibility
        eligibility = is_listing_eligible_for_party(listing_dict, party)
        
        # Log eligibility check
        print(f"  Party: {party.name}")
        print(f"    Eligibility: {eligibility.status.value}")
        print(f"    Reason: {eligibility.reason}")
        
        # CRITICAL: Never share if UNKNOWN
        if eligibility.status == PartyEligibilityStatus.UNKNOWN:
            party_skipped += 1
            self._log_party_share(PartyShareLog(
                listing_id=listing.listing_id,
                listing_title=listing.title,
                party_id=party.party_id,
                party_name=party.name,
                eligibility_status=eligibility.status,
                eligibility_reason=eligibility.reason,
                action="skipped",
                result="Unknown eligibility",
                timestamp=datetime.now(),
            ))
            continue
        
        # Skip if ineligible
        if eligibility.status == PartyEligibilityStatus.INELIGIBLE:
            party_skipped += 1
            self._log_party_share(PartyShareLog(
                listing_id=listing.listing_id,
                listing_title=listing.title,
                party_id=party.party_id,
                party_name=party.name,
                eligibility_status=eligibility.status,
                eligibility_reason=eligibility.reason,
                action="skipped",
                result="Not eligible",
                timestamp=datetime.now(),
            ))
            continue
        
        # Share to party
        try:
            party_result = self.share_to_party(listing, party)
            
            if party_result.success:
                party_shared += 1
                action = "shared"
                result = "Success"
            else:
                party_failed += 1
                action = "failed"
                result = party_result.message
            
            self._log_party_share(PartyShareLog(
                listing_id=listing.listing_id,
                listing_title=listing.title,
                party_id=party.party_id,
                party_name=party.name,
                eligibility_status=eligibility.status,
                eligibility_reason=eligibility.reason,
                action=action,
                result=result,
                timestamp=datetime.now(),
            ))
            
        except Exception as e:
            party_failed += 1
            self._log_party_share(PartyShareLog(
                listing_id=listing.listing_id,
                listing_title=listing.title,
                party_id=party.party_id,
                party_name=party.name,
                eligibility_status=eligibility.status,
                eligibility_reason=eligibility.reason,
                action="failed",
                result=f"Exception: {e}",
                timestamp=datetime.now(),
            ))
    
    # STEP 8: Return combined result
    return ShareResult(
        success=True,
        shared=follower_result.shared + party_shared,
        skipped=party_skipped,
        failed=party_failed,
        elapsed_seconds=time.time() - start_time,
        message=f"Shared to followers + {party_shared} parties",
    )
```

## Testing Strategy

### Test 1: Selector Discovery
**File**: `tools/test_party_share_selectors.py`
- Discover party share UI selectors
- Document modal structure
- Test party selection

### Test 2: Single Listing Share
**File**: `tools/test_share_single_with_parties.py`
- Load ONE listing from inventory
- Check availability
- Share to followers
- Load party cache
- Get live parties
- Check eligibility for each party
- Share to eligible parties
- Log all results

### Test 3: Eligibility Edge Cases
- Test with UNIVERSAL party (should be eligible)
- Test with BRAND_LIMITED party (match/no match)
- Test with CATEGORY_LIMITED party (match/no match)
- Test with unavailable listing (should skip all parties)
- Test with UNKNOWN eligibility (should skip)

## Critical Rules (MUST FOLLOW)

1. **NEVER share unavailable listings** - Check availability FIRST
2. **NEVER share to non-live parties** - Filter for is_live=True
3. **NEVER share if eligibility is UNKNOWN** - Only share on ELIGIBLE
4. **DO NOT modify uploader** - This is sharing only
5. **DO NOT modify scraper** - This is sharing only
6. **Start with ONE listing only** - No batch processing yet
7. **Do not build scheduling yet** - Manual execution only

## File Changes Summary

### Modified Files
1. `sharing/share_engine.py`
   - Extend `ShareableListing` dataclass
   - Add `PartyShareLog` dataclass
   - Add `party_manager` to `__init__`
   - Add `share_listing_with_parties()` method
   - Add `share_to_party()` method
   - Add `_find_party_share_options()` method
   - Add `_select_party_in_modal()` method
   - Add `_log_party_share()` method

### New Files
1. `plans/TASK-027A-party-share-integration-plan.md` (this file)
2. `tools/test_party_share_selectors.py` (selector discovery)
3. `tools/test_share_single_with_parties.py` (integration test)

### Not Modified
- `uploader/` - No changes
- `scraper/` - No changes
- `party/` - No changes (already complete)

## Next Steps

1. ✅ Create this implementation plan
2. ⏳ Discover party share UI selectors
3. ⏳ Implement extended `ShareableListing` model
4. ⏳ Implement party share methods
5. ⏳ Integrate PartyManager
6. ⏳ Add logging infrastructure
7. ⏳ Create test script for single listing
8. ⏳ Test with ONE listing
9. ⏳ Validate all critical rules are followed

## Open Questions

1. **How to load listing metadata?**
   - Option A: Load from inventory (listing.json files)
   - Option B: Scrape from listing page
   - **Decision**: Load from inventory for now (faster, already available)

2. **Where to store party share logs?**
   - Option A: Console only
   - Option B: Separate log file (logs/party_shares.log)
   - **Decision**: Console for now, file logging later

3. **How to handle cache refresh?**
   - Option A: Refresh on every share operation
   - Option B: Check cache age, refresh if stale
   - **Decision**: Use cached parties for now, manual refresh

4. **Should we share to ALL eligible parties or limit?**
   - Option A: Share to all eligible parties
   - Option B: Limit to N parties per listing
   - **Decision**: Share to all for now, add limit later if needed

## Success Criteria

- [ ] Can share ONE listing to followers
- [ ] Can load party cache
- [ ] Can get live parties
- [ ] Can check eligibility for each party
- [ ] Can share to eligible parties
- [ ] Never shares unavailable listings
- [ ] Never shares to non-live parties
- [ ] Never shares on UNKNOWN eligibility
- [ ] Logs all actions and results
- [ ] No modifications to uploader
- [ ] No modifications to scraper
