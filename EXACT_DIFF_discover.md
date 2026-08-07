# EXACT DIFF FOR scraper/discover.py

## CHANGE 1: Add new helper function after line 299

**Location:** After `_extract_cards_from_page()` function ends (line 299)

**Add this complete function:**

```python
def _count_listing_cards(page: Page) -> int:
    """
    Quickly count the number of listing cards on the page without full extraction.
    This is much faster than _extract_cards_from_page() for dynamic wait checks.
    """
    script = r"""
    () => {
        const anchors = document.querySelectorAll('a[href*="/listing/"]');
        const uniqueUrls = new Set();
        
        for (const anchor of anchors) {
            const href = anchor.href || anchor.getAttribute("href");
            if (href && /\/listing\//i.test(href)) {
                try {
                    const url = new URL(href, window.location.origin);
                    url.hash = "";
                    url.search = "";
                    const normalized = url.toString().replace(/\/$/, "");
                    uniqueUrls.add(normalized);
                } catch {
                    // Skip invalid URLs
                }
            }
        }
        
        return uniqueUrls.size;
    }
    """
    
    try:
        result = page.evaluate(script)
        return int(result) if isinstance(result, (int, float)) else 0
    except Exception:
        return 0
```

**Selector correspondence:**
- `_count_listing_cards()` uses: `document.querySelectorAll('a[href*="/listing/"]')`
- `_extract_cards_from_page()` uses: `document.querySelectorAll('a[href*="/listing/"]')` (line 218-219)
- **Both use the exact same selector** for consistency
- `_count_listing_cards()` only counts unique normalized URLs (fast)
- `_extract_cards_from_page()` extracts full card data (slow)

---

## CHANGE 2: Replace fixed wait with dynamic wait

**Location:** Lines 680-688 in `discover_closet()` function

### EXACT CODE BEING REMOVED (lines 680-688):

```python
        page.evaluate(
            """
            () => window.scrollTo(
                0,
                document.documentElement.scrollHeight
            )
            """
        )
        page.wait_for_timeout(scroll_pause_ms)
```

### EXACT CODE REPLACING IT:

```python
        # Dynamic wait after scroll
        page.evaluate(
            """
            () => window.scrollTo(
                0,
                document.documentElement.scrollHeight
            )
            """
        )
        
        # Dynamic wait parameters
        check_interval_ms = 150
        minimum_wait_ms = 600
        stable_checks_needed = 4
        max_wait_ms = 2500
        
        # Track timing and card growth
        wait_start_time = time.time()
        elapsed_ms = 0
        previous_card_count = _count_listing_cards(page)
        stable_check_count = 0
        
        # Dynamic wait loop
        while elapsed_ms < max_wait_ms:
            page.wait_for_timeout(check_interval_ms)
            elapsed_ms = (time.time() - wait_start_time) * 1000
            
            current_card_count = _count_listing_cards(page)
            
            if current_card_count > previous_card_count:
                # Growth detected, reset stability counter
                previous_card_count = current_card_count
                stable_check_count = 0
            else:
                # No growth detected
                stable_check_count += 1
                
                # Only allow early exit after minimum wait period
                if elapsed_ms >= minimum_wait_ms:
                    if stable_check_count >= stable_checks_needed:
                        # Stable for required checks, exit early
                        break
```

---

## UNCHANGED: Every-5th-scroll recovery logic

**Location:** Lines 690-702 (REMAIN EXACTLY AS-IS)

```python
        if scroll_number % 5 == 0:
            page.evaluate("() => window.scrollBy(0, -500)")
            page.wait_for_timeout(250)

            page.evaluate(
                """
                () => window.scrollTo(
                    0,
                    document.documentElement.scrollHeight
                )
                """
            )
            page.wait_for_timeout(500)
```

**This code is NOT modified and remains in place.**

---

## PARAMETER CONFIRMATION

✅ **minimum_wait_ms = 600**
✅ **check_interval_ms = 150**
✅ **stable_checks_needed = 4**
✅ **max_wait_ms = 2500**

### Behavior:
1. After scrolling, always wait at least 600ms before allowing early exit
2. Check card count every 150ms
3. If card count grows: reset stable_check_count to 0
4. After 600ms minimum: require 4 consecutive no-growth checks (4 × 150ms = 600ms stable)
5. Hard stop at 2500ms even if page keeps changing

---

## NO OTHER DISCOVERY LOGIC CHANGES

✅ **Lines 1-299:** Unchanged (imports, dataclasses, helpers)
✅ **Lines 301-513:** Unchanged (filter application functions)
✅ **Lines 515-679:** Unchanged (discovery loop, incremental sync, boundary detection)
✅ **Lines 690-702:** Unchanged (scroll-back every 5th scroll)
✅ **Lines 704-859:** Unchanged (results processing, saving, main function)

### Preserved functionality:
- ✅ Available Items filter (lines 434-512)
- ✅ Active Items filter (lines 434-512)
- ✅ Incremental boundary detection (lines 558-622)
- ✅ Import limit (lines 600-608)
- ✅ Duplicate detection via `_merge_discovery()` (lines 610-613)
- ✅ Stability detection (lines 663-675)
- ✅ Progress saving (lines 657-661)
- ✅ Return types unchanged
- ✅ No parallelism added

---

## SUMMARY

**Total changes:**
1. Add 1 new function (35 lines) after line 299
2. Replace 9 lines (680-688) with 42 lines of dynamic wait logic
3. Net addition: +68 lines

**Only modified:** Scroll wait timing logic
**Everything else:** Completely unchanged
