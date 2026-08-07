# TASK-023D: Duplicate Publishing After Verification Failure — Root Cause Analysis

**SEVERITY:** CRITICAL  
**STATUS:** Analysis Complete — Awaiting Approval for Implementation

---

## EXECUTIVE SUMMARY

A critical bug allows ONE source listing to create TWO destination listings when post-publish verification fails. The root cause is that **the entire publish operation (including duplicate check, form filling, and Publish button click) is wrapped in a retry loop**, treating publish as an idempotent operation when it is fundamentally **NON-IDEMPOTENT**.

---

## PART A: EXACT FAILURE TRACE

### 1. Function Wrapped by retry_operation()

**File:** [`run_single_listing.py:178-194`](run_single_listing.py:178)

```python
result = retry_operation(
    lambda: process_destination_listing(
        page,
        listing_file,
        destination_urls,
        publish=publish,
    ),
    attempts=retries,
    delay_seconds=retry_delay,
    page=page,
    stage=(
        "selected_listing_publish"
        if publish
        else "selected_listing_dry_run"
    ),
    listing_id=listing_id,
)
```

The **entire** [`process_destination_listing()`](run_pipeline.py:478) function is wrapped.

---

### 2. Exact Retry Boundary

**File:** [`run_pipeline.py:478-556`](run_pipeline.py:478)

The retry boundary includes:

```
RETRY START
├─ Load listing from file
├─ Check if already copied (database)
├─ Get image paths
├─ Validate listing
├─ **Duplicate check** (find_existing_duplicate)
├─ If duplicate found → return "already_exists"
├─ If not publish mode → return "would_upload"
├─ **Fill listing form** (fill_listing_form)
│  ├─ Navigate to create-listing page
│  ├─ Upload images
│  ├─ Fill title, description, price, brand, category, size, condition, colors
│  └─ Form complete
├─ **Publish listing** (publish_listing)
│  ├─ Click Next button
│  ├─ Click final Publish button
│  └─ **Verify publication** (find_published_listing)
├─ Record completion (mark_database_copied, mark_local_copied)
├─ Add to destination_urls cache
└─ Return "uploaded"
RETRY END
```

**CRITICAL FLAW:** If verification fails at the end, the **ENTIRE** operation retries, including:
- Duplicate check (with stale cache)
- Form filling
- **Publish button click** (creates SECOND listing)

---

### 3. Exact Publish Verification Implementation

**File:** [`uploader/publisher.py:172-229`](uploader/publisher.py:172)

```python
def publish_listing(page: Page, listing_title: str) -> str:
    click_next(page)
    
    publish_button = find_publish_button(page)
    if publish_button is None:
        raise RuntimeError("Could not find the final publish button.")
    
    print("\nThe listing is ready for publishing.")
    print("Clicking the final publish button...")
    
    publish_button.scroll_into_view_if_needed()
    publish_button.click()  # ← PUBLISH HAPPENS HERE
    
    print("Final publish button clicked.")
    page.wait_for_timeout(8000)
    
    current_url = page.url
    
    # Case 1: Direct redirect to new listing
    if "/listing/" in current_url:
        print("Listing published successfully.")
        print("Destination URL:", current_url)
        return current_url
    
    # Case 2: Redirect to closet
    if "/closet/" in current_url:
        print("Redirected to the closet. Searching for the published listing.")
        
        destination_url = find_published_listing(page, listing_title)
        
        if destination_url:
            print("Listing published successfully.")
            print("Destination URL:", destination_url)
            return destination_url
    
    # Case 3: Verification failed
    raise RuntimeError(
        "The final button was clicked, but the "
        "published listing could not be verified. "
        f"Current URL: {current_url}"
    )
```

**Verification Logic:**
1. Click Publish button
2. Wait 8 seconds
3. Check if redirected to `/listing/` (new listing page) → SUCCESS
4. Check if redirected to `/closet/` → call [`find_published_listing()`](uploader/publisher.py:122)
5. If neither → **raise RuntimeError** → triggers retry

---

### 4. Why Only 48 Links Checked

**File:** [`uploader/publisher.py:122-169`](uploader/publisher.py:122)

```python
def find_published_listing(page: Page, expected_title: str) -> str | None:
    expected = normalize_text(expected_title)
    
    listing_links = collect_listing_links(page)  # ← Collects links from CURRENT page
    
    print(f"Checking {len(listing_links)} closet listing links for the new listing.")
    
    # The newest listings should appear first,
    # so only inspect the first several.
    for listing_url in listing_links[:15]:  # ← Only checks first 15
        # ... title matching logic ...
```

**File:** [`uploader/publisher.py:100-119`](uploader/publisher.py:100)

```python
def collect_listing_links(page: Page) -> list[str]:
    page.wait_for_timeout(4000)
    
    links = page.locator('a[href*="/listing/"]').evaluate_all(
        """
        elements => [
            ...new Set(
                elements
                    .map(element => element.href)
                    .filter(Boolean)
            )
        ]
        """
    )
    
    return links
```

**ROOT CAUSE:** After Poshmark redirects to `/closet/dveshop`, the page shows only the **initially loaded listings** (typically 48 on first render). The verification:
- Does NOT scroll to load more listings
- Does NOT refresh the page
- Does NOT wait for dynamic content
- Only checks the first 15 of whatever is visible

If the new listing hasn't propagated to the visible DOM yet, verification fails even though the listing was successfully published.

---

### 5. destination_urls Caching Interaction

**File:** [`run_single_listing.py:165-170`](run_single_listing.py:165)

```python
destination_urls = collect_destination_listing_urls(
    page,
    DESTINATION_CLOSET_URL,
)
```

**File:** [`uploader/duplicate_detector.py:103-194`](uploader/duplicate_detector.py:103)

The `destination_urls` list is collected **ONCE** before processing begins:
1. Navigate to destination closet
2. Scroll up to 35 times to load listings
3. Extract all listing URLs
4. Cache in memory as a list

**CRITICAL FLAW:** This cache is **NOT refreshed** between retry attempts. When the retry happens:
- The newly published listing (from attempt 1) is NOT in `destination_urls`
- Duplicate check uses stale cache
- Reports "no duplicate found"
- Proceeds to publish AGAIN

---

### 6. Why Attempt 2 Duplicate Detection Failed

**Sequence:**

**Attempt 1:**
1. `destination_urls` cached (does not include listing X)
2. Duplicate check: "no similar titles found" ✓
3. Form filled ✓
4. Publish clicked → **Listing X created** ✓
5. Verification: only 48 links visible, listing X not found ✗
6. **RuntimeError raised** → retry triggered

**Attempt 2:**
1. `destination_urls` **STILL STALE** (does not include listing X)
2. Duplicate check: "no similar titles found" ✓ (WRONG!)
3. Form filled ✓
4. Publish clicked → **Listing X-duplicate created** ✗
5. Verification: finds X-duplicate ✓
6. Success reported

**Why duplicate check failed:**
- [`find_existing_duplicate()`](uploader/duplicate_detector.py:478) only checks URLs in the `destination_urls` list
- The list is passed by reference but never refreshed
- Listing X was published but not added to the cache before retry
- The cache update happens in [`process_destination_listing()`](run_pipeline.py:548) **AFTER** successful verification
- Since verification failed, the cache was never updated

---

### 7. Destination Listing Cache Staleness

**Cache Update Location:** [`run_pipeline.py:548-551`](run_pipeline.py:548)

```python
add_destination_url(
    destination_urls,
    destination_url,
)
```

This happens **AFTER** successful verification. If verification fails:
- Cache is NOT updated
- Retry uses stale cache
- Duplicate check fails to find the just-published listing

**Additional Issue:** Even if we updated the cache after publish but before verification, the duplicate detector uses **title similarity matching** which requires:
- Navigating to each candidate URL
- Extracting title, brand, size, price
- Calculating similarity score

This is **too slow** for post-publish verification and doesn't help if the listing hasn't propagated yet.

---

## PART B: REQUIRED SAFETY DESIGN

### Core Principle

**Publishing is NON-IDEMPOTENT.** Once the Publish button is clicked, we must NEVER automatically click it again for the same source listing, regardless of verification outcome.

### Two-Phase Operation Model

#### PHASE 1: PRE-PUBLISH (Safe to Retry)
- Navigation
- Duplicate check
- Opening create-listing page
- Image upload
- Form field filling
- Next button click

#### PHASE 2: POST-PUBLISH (NOT Safe to Retry)
- **Final Publish button click**
- Verification

### Post-Publish Verification Strategy

After Publish button is clicked:

```
Publish clicked
↓
Wait for redirect/response
↓
Attempt verification #1
├─ Direct URL from redirect? → SUCCESS
├─ Visible in closet page? → SUCCESS
└─ Not found → Continue
↓
Refresh/reload destination page
↓
Attempt verification #2
├─ Visible after refresh? → SUCCESS
└─ Not found → Continue
↓
Navigate to closet, scroll to load fresh data
↓
Attempt verification #3
├─ Found in fresh scan? → SUCCESS
└─ Not found → Continue
↓
Return PUBLISH_UNVERIFIED
(Do NOT retry publish)
```

### Result States

Introduce new result classification:

1. **PUBLISH_CONFIRMED** — Listing verified successfully
2. **PUBLISH_UNVERIFIED** — Publish clicked but verification uncertain
3. **PRE_PUBLISH_FAILURE** — Failed before Publish button clicked (safe to retry)
4. **ALREADY_EXISTS** — Duplicate found
5. **WOULD_UPLOAD** — Dry run mode

---

## PART C: FRESH VERIFICATION DESIGN

### Requirements

1. **Do not rely on pre-publish cached `destination_urls`** after publishing
2. **Refresh/reload destination data** after Publish
3. **Use strongest evidence available** in priority order:
   - A. Direct newly-created listing URL from redirect/network/page state
   - B. Fresh destination closet scan sorted newest-first
   - C. Exact or high-confidence listing match using title + brand + price + size
   - D. Existing duplicate detector using FRESH destination data

### Proposed Verification Flow

```python
def verify_published_listing(
    page: Page,
    listing_title: str,
    listing_brand: str,
    listing_price: str,
    listing_size: str,
) -> tuple[bool, str | None]:
    """
    Verify listing publication with multiple strategies.
    
    Returns:
        (verified, destination_url or None)
    """
    
    # Strategy 1: Check current URL (direct redirect)
    current_url = page.url
    if "/listing/" in current_url:
        return (True, current_url)
    
    # Strategy 2: Check visible listings on current page
    if "/closet/" in current_url:
        url = find_in_visible_listings(page, listing_title)
        if url:
            return (True, url)
    
    # Strategy 3: Refresh and check again
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    url = find_in_visible_listings(page, listing_title)
    if url:
        return (True, url)
    
    # Strategy 4: Navigate to closet and scan fresh
    page.goto(DESTINATION_CLOSET_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    
    # Scroll to load newest listings
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
    
    url = find_in_visible_listings(page, listing_title)
    if url:
        return (True, url)
    
    # Strategy 5: Deep match with metadata
    url = find_by_metadata_match(
        page,
        listing_title,
        listing_brand,
        listing_price,
        listing_size,
    )
    if url:
        return (True, url)
    
    # Verification uncertain
    return (False, None)
```

### Why Only 48 Links

The issue is that [`collect_listing_links()`](uploader/publisher.py:100) in publisher.py:
- Waits only 4 seconds
- Does NOT scroll
- Only captures what's in the initial DOM

The separate [`collect_destination_listing_urls()`](uploader/duplicate_detector.py:103) in duplicate_detector.py:
- Scrolls up to 35 times
- Loads 1600+ listings
- But is only called ONCE at the start

**Solution:** Post-publish verification must use a fresh scan with scrolling, not the stale initial page load.

---

## PART D: RETRY CLASSIFICATION

### Failure Type Enum

```python
class PublishPhase(str, Enum):
    PRE_PUBLISH = "pre_publish"
    POST_PUBLISH = "post_publish"

class PublishResult(str, Enum):
    UPLOADED = "uploaded"
    ALREADY_EXISTS = "already_exists"
    WOULD_UPLOAD = "would_upload"
    ALREADY_RECORDED = "already_recorded"
    PUBLISH_UNVERIFIED = "publish_unverified"
    PRE_PUBLISH_FAILED = "pre_publish_failed"
```

### Exception Classification

```python
class PublishException(Exception):
    def __init__(self, message: str, phase: PublishPhase):
        super().__init__(message)
        self.phase = phase

class PrePublishException(PublishException):
    def __init__(self, message: str):
        super().__init__(message, PublishPhase.PRE_PUBLISH)

class PostPublishException(PublishException):
    def __init__(self, message: str):
        super().__init__(message, PublishPhase.POST_PUBLISH)
```

### Retry Logic

```python
def retry_publish_operation(operation, attempts, delay_seconds, page, listing_id):
    publish_clicked = False
    last_error = None
    
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        
        except PublishException as error:
            last_error = error
            
            # If publish was clicked, NEVER retry
            if error.phase == PublishPhase.POST_PUBLISH:
                print(f"Post-publish verification failed: {error}")
                print("Publish button was clicked. Will NOT retry publish.")
                raise  # Do not retry
            
            # Pre-publish failures are safe to retry
            if attempt < attempts:
                print(f"Pre-publish failure (attempt {attempt}/{attempts}): {error}")
                time.sleep(delay_seconds)
                continue
            else:
                raise
        
        except Exception as error:
            # Unknown error type - treat as pre-publish for safety
            last_error = error
            if attempt < attempts:
                time.sleep(delay_seconds)
            else:
                raise
    
    raise last_error
```

---

## PART E: QUEUE SAFETY

### Current Queue Status

**File:** [`inventory/upload_queue.py:24-33`](inventory/upload_queue.py:24)

```python
class QueueStatus(str, Enum):
    WAITING = "waiting"
    PENDING = "pending"
    RUNNING = "running"
    UPLOADED = "uploaded"
    ALREADY_EXISTS = "already_exists"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
```

### Proposed Addition

Add new status:

```python
PUBLISH_UNVERIFIED = "publish_unverified"
```

**Meaning:** The Publish button was clicked, but the system could not verify the listing appeared in the destination closet. Manual verification required.

### Queue Processor Handling

**File:** [`pipeline/upload_queue_processor.py:454-508`](pipeline/upload_queue_processor.py:454)

Update `_parse_outcome()` to recognize `PUBLISH_UNVERIFIED`:

```python
def _parse_outcome(self, exit_code, stdout, stderr):
    status = self._parse_status_lines(stdout)
    
    # Check for PUBLISH_UNVERIFIED
    if "PUBLISH_UNVERIFIED" in stdout:
        return QueueStatus.PUBLISH_UNVERIFIED, "Publish clicked but verification uncertain"
    
    # ... existing logic ...
```

### Manual Recovery

Items marked `PUBLISH_UNVERIFIED` should:
1. NOT be automatically retried
2. Appear in a special "Needs Verification" section in the dashboard
3. Allow manual verification:
   - User checks destination closet
   - If found: mark as UPLOADED with destination URL
   - If not found: reset to PENDING for retry

---

## PART F: CRASH SAFETY

### Current Risk

```
Publish clicked
↓
Listing created on Poshmark
↓
App crashes before mark_listing_copied()
↓
On restart: listing_already_copied() returns False
↓
Duplicate check runs with stale cache
↓
Publishes AGAIN → duplicate
```

### Solution

Before attempting to publish, check destination FIRST:

```python
def process_destination_listing_safe(page, listing_file, destination_urls, publish):
    listing = load_listing(listing_file)
    listing_id = listing["listing_id"]
    
    # ALWAYS check database first
    if listing_already_copied(listing_id):
        return "already_recorded"
    
    # ALWAYS run fresh duplicate check before publish
    # (even if we think we haven't published yet)
    existing_url = find_existing_duplicate_fresh(
        page,
        listing,
        force_refresh=True,  # Don't trust cache
    )
    
    if existing_url:
        # Found existing - record and skip
        record_completion(listing, existing_url)
        return "already_exists"
    
    # Safe to proceed with publish
    # ...
```

### Persistent Publish State

Consider adding a "publish intent" marker:

```python
# Before clicking Publish
mark_publish_intent(listing_id)

# Click Publish
publish_button.click()

# After verification
clear_publish_intent(listing_id)
```

On restart, check for pending publish intents and verify destination first.

---

## PART G: TEST REQUIREMENTS

### Test Plan

1. **Dry Run — 1 item**
   - Verify no publish occurs
   - Verify result is "would_upload"

2. **Simulated verification failure after Publish**
   - Mock verification to always fail
   - Verify Publish clicked exactly ONCE
   - Verify result is PUBLISH_UNVERIFIED
   - Verify NO retry of publish

3. **Verification refresh/retry**
   - Simulate delayed listing propagation
   - Verify refresh strategies work
   - Verify eventual success

4. **Existing listing detection**
   - Publish listing manually
   - Run pipeline
   - Verify duplicate detected
   - Verify no second publish

5. **One real Live Publish listing**
   - Publish one real listing
   - Verify success
   - Check destination closet
   - Confirm exactly ONE copy exists

6. **Crash recovery**
   - Simulate crash after publish
   - Restart
   - Verify no duplicate publish

---

## ROOT CAUSE SUMMARY

**Primary Root Cause:**  
The entire publish operation (duplicate check + form fill + publish click + verification) is wrapped in [`retry_operation()`](run_pipeline.py:181), treating it as idempotent when the Publish button click is fundamentally non-idempotent.

**Contributing Factors:**

1. **Stale Cache:** `destination_urls` is not refreshed between retries
2. **Weak Verification:** Only checks 48 visible listings without scrolling/refreshing
3. **No Phase Separation:** Pre-publish and post-publish operations are not distinguished
4. **Verification Timing:** Poshmark may need time to propagate the listing to the closet view
5. **No Publish Tracking:** No persistent marker that publish was attempted

---

## EXACT FILES TO MODIFY

### Core Changes

1. **[`uploader/publisher.py`](uploader/publisher.py)**
   - Split `publish_listing()` into two functions:
     - `click_publish_button()` — clicks and returns immediately
     - `verify_published_listing()` — multi-strategy verification
   - Add fresh verification with refresh/scroll
   - Return verification status separately from publish action

2. **[`run_pipeline.py`](run_pipeline.py)**
   - Modify `process_destination_listing()` to separate phases
   - Add phase-aware exception handling
   - Update retry logic to never retry after publish click
   - Add PUBLISH_UNVERIFIED result handling

3. **[`run_single_listing.py`](run_single_listing.py)**
   - Update retry wrapper to handle phase-aware exceptions
   - Add PUBLISH_UNVERIFIED result handling

4. **[`inventory/upload_queue.py`](inventory/upload_queue.py)**
   - Add `PUBLISH_UNVERIFIED` status to `QueueStatus` enum
   - Add `mark_publish_unverified()` method

5. **[`pipeline/upload_queue_processor.py`](pipeline/upload_queue_processor.py)**
   - Update `_parse_outcome()` to recognize PUBLISH_UNVERIFIED
   - Handle PUBLISH_UNVERIFIED status appropriately

### New Files

6. **`uploader/publish_phases.py`** (NEW)
   - Define `PublishPhase` enum
   - Define `PublishResult` enum
   - Define phase-aware exception classes
   - Define verification strategies

### Supporting Changes

7. **[`uploader/duplicate_detector.py`](uploader/duplicate_detector.py)**
   - Add `find_existing_duplicate_fresh()` that forces cache refresh
   - Add option to bypass cache for post-publish verification

8. **[`data/database/database.py`](data/database/database.py)** (if needed)
   - Add publish intent tracking (optional, for crash safety)

---

## ESTIMATED DIFF SIZE

### Lines Changed by File

| File | Lines Added | Lines Modified | Lines Deleted | Total Impact |
|------|-------------|----------------|---------------|--------------|
| `uploader/publisher.py` | ~150 | ~50 | ~20 | ~220 |
| `run_pipeline.py` | ~80 | ~40 | ~10 | ~130 |
| `run_single_listing.py` | ~30 | ~20 | ~5 | ~55 |
| `inventory/upload_queue.py` | ~20 | ~5 | ~0 | ~25 |
| `pipeline/upload_queue_processor.py` | ~30 | ~15 | ~0 | ~45 |
| `uploader/publish_phases.py` (NEW) | ~120 | ~0 | ~0 | ~120 |
| `uploader/duplicate_detector.py` | ~40 | ~10 | ~0 | ~50 |
| **TOTAL** | **~470** | **~140** | **~35** | **~645** |

### Complexity Assessment

- **High Risk Areas:** Retry logic, verification flow
- **Testing Required:** Extensive (see Part G)
- **Backward Compatibility:** Minimal impact (new result states)
- **Rollback Plan:** Revert to current retry logic if issues arise

---

## IMPLEMENTATION PRIORITY

### Phase 1: Critical Safety (Immediate)
1. Split publish and verification in `publisher.py`
2. Add phase-aware exceptions
3. Update retry logic to never retry after publish click
4. Add PUBLISH_UNVERIFIED result state

### Phase 2: Enhanced Verification (High Priority)
1. Implement multi-strategy verification
2. Add fresh cache refresh
3. Add scroll/reload logic

### Phase 3: Crash Safety (Medium Priority)
1. Add publish intent tracking
2. Add startup verification check

### Phase 4: Queue Integration (Medium Priority)
1. Add PUBLISH_UNVERIFIED queue status
2. Update queue processor
3. Add manual verification UI

---

## APPROVAL REQUIRED

This analysis is complete. Awaiting approval to proceed with implementation.

**Recommended Next Steps:**
1. Review this analysis
2. Approve implementation plan
3. Implement Phase 1 (Critical Safety) first
4. Test thoroughly with dry runs
5. Test with one real listing
6. Deploy remaining phases

**DO NOT run Live Publish until Phase 1 is implemented and tested.**
