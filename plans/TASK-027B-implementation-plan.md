# TASK-027B: Production Party Share Integration - Implementation Plan

## Overview
Implement party sharing in `sharing/share_engine.py` using the confirmed selector from TASK-027A.2 discovery.

## Files to Modify

### 1. `sharing/share_config.py`
**Purpose**: Add party sharing configuration options

**New Fields**:
```python
@dataclass
class ShareConfig:
    # ... existing fields ...
    
    # Party sharing configuration
    share_to_parties: bool = False
    share_to_posh_shows: bool = False
    party_share_limit: int | None = 1  # Safety: limit party shares per run
```

**Estimated Changes**: +3 lines, validation in `__post_init__`

---

### 2. `sharing/share_engine.py`
**Purpose**: Add party sharing capability alongside existing follower sharing

**New Method Signature**:
```python
def share_listing_to_party(
    self,
    listing: ShareableListing,
    party: PoshParty,
    retry: bool = True,
) -> ShareResult:
    """
    Share a single listing to a specific Posh Party.
    
    HARD GATES:
    - listing must be AVAILABLE
    - listing must be ACTIVE
    - party must be is_live == True
    - listing must be ELIGIBLE for party
    
    Args:
        listing: Listing to share (must include availability, active status)
        party: Live party to share to
        retry: Whether to retry once on transient failures
    
    Returns:
        ShareResult with success/failure status
    """
```

**New Helper Methods**:
```python
def _open_share_modal_from_closet(
    self,
    listing_id: str
) -> bool:
    """
    Open share modal from closet card.
    
    Returns:
        True if modal opened successfully, False otherwise
    """

def _find_party_destination(
    self,
    party_id: str,
    party_name: str
) -> Locator | None:
    """
    Find party destination in share modal.
    
    Selector strategy:
    1. Primary: a[data-et-name="share_to_party"][data-et-prop-party_id="{party_id}"]
    2. Fallback: a[data-et-name="share_to_party"] + verify party_id attribute
    3. Last resort: text match on party_name
    
    Returns:
        Locator for party destination, or None if not found
    """

def _detect_posh_shows_destination(self) -> bool:
    """
    Detect if Posh Shows Host destination is present.
    
    Returns:
        True if Posh Shows destination found, False otherwise
    """

def _verify_party_destination(
    self,
    element: Locator,
    party_name: str
) -> bool:
    """
    Verify party destination before clicking.
    
    Checks:
    - Element is visible
    - Party name matches (case-insensitive)
    - Not disabled
    
    Returns:
        True if safe to click, False otherwise
    """

def _detect_share_success(self) -> tuple[bool, str]:
    """
    Detect if share was successful after clicking destination.
    
    Checks:
    - Modal closed
    - Success toast/message
    - Other UI state changes
    
    Returns:
        (success: bool, message: str)
    """
```

**Estimated Changes**: +250-300 lines

---

### 3. `sharing/share_progress.py`
**Purpose**: Add party-specific error types and result tracking

**New Error Types**:
```python
class ShareErrorType(str, Enum):
    # ... existing types ...
    
    # Party sharing errors
    PARTY_NOT_LIVE = "party_not_live"
    PARTY_NOT_ELIGIBLE = "party_not_eligible"
    PARTY_DESTINATION_NOT_FOUND = "party_destination_not_found"
    PARTY_SHARE_FAILED = "party_share_failed"
```

**Enhanced ShareResult**:
```python
@dataclass
class ShareResult:
    # ... existing fields ...
    
    # Party sharing metadata
    party_id: str | None = None
    party_name: str | None = None
    eligibility_status: str | None = None
    eligibility_reason: str | None = None
```

**Estimated Changes**: +15-20 lines

---

## Implementation Strategy

### Phase 1: Configuration (share_config.py)
1. Add `share_to_parties` flag (default: False)
2. Add `share_to_posh_shows` flag (default: False)  
3. Add `party_share_limit` (default: 1 for safety)
4. Add validation in `__post_init__`

### Phase 2: Error Types (share_progress.py)
1. Add party-specific error types
2. Enhance ShareResult with party metadata fields

### Phase 3: Core Implementation (share_engine.py)

#### Step 1: Modal Opening from Closet
```python
def _open_share_modal_from_closet(self, listing_id: str) -> bool:
    # Navigate to closet
    # Find listing card by listing_id
    # Click share button: div.share-v2.cursor--pointer
    # Wait for modal: [data-test="listing-share-modal-container"]
    # Return success/failure
```

#### Step 2: Party Destination Discovery
```python
def _find_party_destination(self, party_id: str, party_name: str) -> Locator | None:
    # Scope to modal
    modal = self.page.locator('[data-test="listing-share-modal-container"]')
    
    # Primary selector
    selector = f'a[data-et-name="share_to_party"][data-et-prop-party_id="{party_id}"]'
    element = modal.locator(selector)
    
    if element.count() > 0:
        return element.first
    
    # Fallback: verify party_id in attributes
    elements = modal.locator('a[data-et-name="share_to_party"]').all()
    for elem in elements:
        if elem.get_attribute('data-et-prop-party_id') == party_id:
            return elem
    
    return None
```

#### Step 3: Posh Shows Detection
```python
def _detect_posh_shows_destination(self) -> bool:
    modal = self.page.locator('[data-test="listing-share-modal-container"]')
    posh_shows = modal.locator('a:has-text("Share to Posh Shows Host")')
    
    if posh_shows.count() > 0:
        print("  [INFO] Posh Shows Host destination detected (will not click)")
        return True
    
    return False
```

#### Step 4: Destination Verification
```python
def _verify_party_destination(self, element: Locator, party_name: str) -> bool:
    # Check visible
    if not element.is_visible():
        return False
    
    # Check party name (case-insensitive)
    text = element.text_content() or ""
    if party_name.lower() not in text.lower():
        print(f"  [WARN] Party name mismatch: expected '{party_name}', got '{text}'")
        return False
    
    # Check not disabled
    if element.get_attribute('aria-disabled') == 'true':
        return False
    
    return True
```

#### Step 5: Success Detection
```python
def _detect_share_success(self) -> tuple[bool, str]:
    # Wait briefly for UI response
    self.page.wait_for_timeout(1500)
    
    # Check if modal closed
    modal = self.page.locator('[data-test="listing-share-modal-container"]')
    if modal.count() == 0:
        return (True, "Modal closed after share")
    
    # Check for success toast/message
    success_indicators = [
        'text=/shared/i',
        'text=/success/i',
        '[class*="success"]',
        '[class*="toast"]'
    ]
    
    for selector in success_indicators:
        if self.page.locator(selector).count() > 0:
            return (True, "Success indicator found")
    
    # No reliable signal
    return (False, "UNKNOWN - no success indicator detected")
```

#### Step 6: Main Party Share Method
```python
def share_listing_to_party(
    self,
    listing: ShareableListing,
    party: PoshParty,
    retry: bool = True,
) -> ShareResult:
    """Share listing to party with full validation."""
    
    print(f"\nSharing listing to party: {listing.title}")
    print(f"  Listing URL: {listing.url}")
    print(f"  Party: {party.name} (ID: {party.party_id})")
    
    start_time = time.time()
    
    # GATE 1: Availability
    if not listing.available:
        return ShareResult(
            success=False,
            failed=1,
            errors=[ShareError(
                error_type=ShareErrorType.LISTING_UNAVAILABLE,
                message="Listing is not available",
                listing_id=listing.listing_id,
                recoverable=False,
            )],
            elapsed_seconds=time.time() - start_time,
            message="Listing not available",
        )
    
    # GATE 2: Party is live
    if not party.is_live:
        return ShareResult(
            success=False,
            failed=1,
            errors=[ShareError(
                error_type=ShareErrorType.PARTY_NOT_LIVE,
                message=f"Party '{party.name}' is not currently live",
                listing_id=listing.listing_id,
                recoverable=False,
            )],
            elapsed_seconds=time.time() - start_time,
            message="Party not live",
            party_id=party.party_id,
            party_name=party.name,
        )
    
    # GATE 3: Eligibility (requires listing data with brand, category, etc.)
    # Note: This requires ShareableListing to be enhanced with eligibility data
    # For now, log warning if eligibility data not available
    
    try:
        # Open share modal from closet
        print("  Opening share modal from closet...")
        if not self._open_share_modal_from_closet(listing.listing_id):
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.MODAL_NOT_FOUND,
                    message="Could not open share modal",
                    listing_id=listing.listing_id,
                    recoverable=True,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Modal not found",
            )
        
        # Detect Posh Shows (log only)
        if self.config.share_to_posh_shows:
            print("  [WARN] share_to_posh_shows is True but not implemented")
        
        self._detect_posh_shows_destination()
        
        # Find party destination
        print(f"  Looking for party destination: {party.name}...")
        party_dest = self._find_party_destination(party.party_id, party.name)
        
        if party_dest is None:
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_DESTINATION_NOT_FOUND,
                    message=f"Party destination not found in modal",
                    listing_id=listing.listing_id,
                    recoverable=True,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Party destination not found",
                party_id=party.party_id,
                party_name=party.name,
            )
        
        # Verify destination
        print("  Verifying party destination...")
        if not self._verify_party_destination(party_dest, party.name):
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_DESTINATION_NOT_FOUND,
                    message="Party destination verification failed",
                    listing_id=listing.listing_id,
                    recoverable=True,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Destination verification failed",
                party_id=party.party_id,
                party_name=party.name,
            )
        
        # Click party destination
        print(f"  Clicking party destination...")
        party_dest.click()
        
        # Detect success
        success, success_msg = self._detect_share_success()
        
        elapsed = time.time() - start_time
        
        if success:
            print(f"  SUCCESS: {success_msg}")
            return ShareResult(
                success=True,
                shared=1,
                elapsed_seconds=elapsed,
                message=success_msg,
                party_id=party.party_id,
                party_name=party.name,
            )
        else:
            print(f"  UNKNOWN: {success_msg}")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_SHARE_FAILED,
                    message=success_msg,
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=elapsed,
                message=success_msg,
                party_id=party.party_id,
                party_name=party.name,
            )
    
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"Unexpected error: {str(e)}"
        print(f"  ERROR: {error_msg}")
        
        return ShareResult(
            success=False,
            failed=1,
            errors=[ShareError(
                error_type=ShareErrorType.UNKNOWN,
                message=error_msg,
                listing_id=listing.listing_id,
                recoverable=True,
            )],
            elapsed_seconds=elapsed,
            message=error_msg,
            party_id=party.party_id,
            party_name=party.name,
        )
```

---

## Selector Strategy

### Primary Selector (Recommended)
```python
selector = f'a[data-et-name="share_to_party"][data-et-prop-party_id="{party.party_id}"]'
```

**Advantages**:
- Most specific
- Uses stable data attributes
- Directly targets party by ID

### Fallback Selector
```python
# Find all party destinations
elements = modal.locator('a[data-et-name="share_to_party"]').all()

# Filter by party_id attribute
for elem in elements:
    if elem.get_attribute('data-et-prop-party_id') == party.party_id:
        return elem
```

### Last Resort (Text Match)
```python
selector = f'a[data-et-name="share_to_party"]:has-text("{party.name}")'
```

**Note**: Less stable due to potential text variations

---

## Success Detection Strategy

### Approach 1: Modal Closure (Primary)
```python
modal = self.page.locator('[data-test="listing-share-modal-container"]')
if modal.count() == 0:
    return (True, "Modal closed")
```

### Approach 2: Success Toast/Message
```python
success_selectors = [
    'text=/shared/i',
    'text=/success/i',
    '[class*="success"]',
    '[class*="toast"]'
]
```

### Approach 3: UNKNOWN Result
If no reliable signal detected, return `UNKNOWN` status and do NOT retry automatically.

---

## Single-Share Safety Guard

### Configuration
```python
party_share_limit: int | None = 1  # Default: only 1 party share per run
```

### Implementation
```python
def share_batch_to_party(self, listings: list[ShareableListing], party: PoshParty):
    """Share multiple listings to party (respects party_share_limit)."""
    
    if self.config.party_share_limit is not None:
        listings = listings[:self.config.party_share_limit]
        print(f"[SAFETY] Limited to {self.config.party_share_limit} party share(s)")
    
    for listing in listings:
        result = self.share_listing_to_party(listing, party)
        # ... handle result ...
```

---

## Logging Requirements

### Per-Share Log Output
```
Sharing listing to party: <listing_title>
  Listing ID: <listing_id>
  Listing URL: <listing_url>
  Party: <party_name> (ID: <party_id>)
  Availability: AVAILABLE
  Active: True
  Eligibility: ELIGIBLE (reason: <reason>)
  Opening share modal from closet...
  [INFO] Posh Shows Host destination detected (will not click)
  Looking for party destination: <party_name>...
  Verifying party destination...
  Clicking party destination...
  SUCCESS: Modal closed after share
  Elapsed: 5.2s
```

---

## Estimated Diff Size

- `sharing/share_config.py`: +10 lines
- `sharing/share_progress.py`: +20 lines
- `sharing/share_engine.py`: +280 lines
- **Total**: ~310 lines added

---

## Testing Strategy

### Test Tool
Create `tools/test_party_share_single.py`:
- Use confirmed live party
- Use confirmed eligible listing
- Set `party_share_limit = 1`
- Log all steps
- Do NOT bulk share

### Success Criteria
1. Modal opens from closet
2. Party destination found
3. Posh Shows detected and logged (not clicked)
4. Party destination clicked
5. Success detected OR UNKNOWN returned
6. No crashes or exceptions
7. Respects single-share limit

---

## Approval Required

Before implementation, confirm:
1. ✓ Files to modify are correct
2. ✓ Method signatures are acceptable
3. ✓ Selector strategy is sound
4. ✓ Success detection approach is reasonable
5. ✓ Single-share safety guard is sufficient
6. ✓ Logging is comprehensive
7. ✓ Estimated diff size is acceptable

**Ready to proceed with implementation?**
