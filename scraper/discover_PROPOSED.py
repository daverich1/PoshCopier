"""
PROPOSED CHANGES TO scraper/discover.py

This file shows the proposed dynamic wait implementation.
Only the sections marked with ### CHANGED ### are modified.

Key changes:
1. Add _count_listing_cards() helper function for cheap card counting
2. Replace fixed scroll_pause_ms wait with dynamic wait logic
3. Preserve all existing filters, boundaries, and duplicate detection
"""

# ============================================================================
# NEW HELPER FUNCTION (add after _extract_cards_from_page)
# ============================================================================

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


# ============================================================================
# MODIFIED SECTION IN discover_closet() function
# Lines 680-702 are replaced with dynamic wait logic
# ============================================================================

        # ### CHANGED ### Dynamic wait after scroll
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
        
        # ### UNCHANGED ### Preserve scroll-back behavior every 5th scroll
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


# ============================================================================
# SUMMARY OF CHANGES
# ============================================================================

"""
Changes made:
1. Added _count_listing_cards() function after line 299 (after _extract_cards_from_page)
2. Replaced lines 680-688 (scroll + fixed wait) with dynamic wait logic
3. Preserved lines 690-702 (scroll-back behavior every 5th scroll)

Behavior:
- Always waits minimum 600ms before allowing early exit
- Checks card count every 150ms during wait
- Resets stability counter when growth detected
- Requires 4 consecutive no-growth checks (600ms stable period) after minimum wait
- Hard timeout at 2500ms to prevent hanging
- Preserves all filters, boundaries, duplicate detection, and return types

Parameters preserved:
✓ Available Items filter (lines 434-512)
✓ Active Items filter (lines 434-512)
✓ Incremental boundary (lines 558-622)
✓ Import limit (lines 600-608)
✓ Duplicate detection via _merge_discovery() (lines 610-613)
✓ No parallelism (single-threaded)
✓ Return types unchanged
"""
