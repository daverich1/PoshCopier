# TASK-025B.2: Share Modal and Followers Selector Discovery Results

## Discovery Date
2026-08-07

## Execution Summary

✅ Successfully clicked share icon on first listing card  
✅ Share modal appeared  
✅ "To My Followers" control discovered  

## Modal Container

### Modal Selector

**Element Type**: `DIV`

**Exact Selector**:
```python
modal = page.locator('[data-test="listing-share-modal-container"]')
# OR
modal = page.locator('.modal.simple-modal')
```

**DOM Evidence**:
```
Tag: DIV
Class: modal simple-modal modal--in
role: None
aria-label: None
data-test: listing-share-modal-container  ← RECOMMENDED
data-testid: None
```

**Recommended**: Use `data-test="listing-share-modal-container"` for stability.

## "To My Followers" Control Discovery

### ✅ CONTROL FOUND

**Element Type**: `<a>` (Anchor/Link, not a button)

**Text Content**: `"To My Followers"`

**Exact Selector Options**:

1. **By text (RECOMMENDED)**:
   ```python
   followers_link = modal.locator('a.internal-share__link').filter(has_text="To My Followers")
   # OR
   followers_link = modal.get_by_text("To My Followers")
   ```

2. **By class and data attribute**:
   ```python
   followers_link = modal.locator('a[data-et-name="share_poshmark"]')
   ```

3. **By class only**:
   ```python
   followers_link = modal.locator('a.internal-share__link').first
   ```

### DOM Evidence

**Full outerHTML**:
```html
<a data-et-name="share_poshmark" 
   data-et-prop-listing_id="6a1b558939a1f6c9a0c84b60" 
   class="internal-share__link">
  <div class="share-wrapper-container">
    <div class="share-wrapper__icon-container">
      <i class="icon pm-logo-white"></i>
    </div>
    <span class="share-wrapper__share-title caption">To My Followers</span>
  </div>
</a>
```

**Key Attributes**:
- Tag: `A` (anchor)
- Class: `internal-share__link`
- data-et-name: `share_poshmark` ← Unique identifier
- Text: `To My Followers`
- href: `None` (JavaScript click handler)
- aria-label: None
- data-test: None
- role: None
- tabindex: None
- **Clickable**: ✅ Yes

### Text Stability

**Modal text contains**:
- ✅ "follower" (lowercase)
- ❌ "share to my" (not found)
- ✅ Exact text: "To My Followers"

**Text is stable**: The text "To My Followers" appears consistently in the modal.

## Modal Structure

### Buttons in Modal (3 found)

1. **Close Button**:
   - data-test: `listing-share-modal-close-btn`
   - Class: `btn btn--close modal__close-btn simple-modal-close`
   - Type: `button`

2. **Cancel Button**:
   - Text: "Cancel"
   - Class: `btn btn--tertiary`

3. **Done Button**:
   - Text: "Done"
   - Class: `btn btn--primary m--l--4`
   - Type: `button`

### Other Share Options

The modal contains multiple share options:
- **To My Followers** ← Target control
- Share to Posh Shows Host
- Direct share to users (list of usernames)
- External shares (Facebook, Twitter, Pinterest, Email, Copy Link)

## Recommended Production Selectors

### Complete Share Flow

```python
# 1. Find listing card
card = page.locator('a[href*="/listing/"]').first

# 2. Get card container
card_container = card.locator('xpath=ancestor::div[contains(@class, "tile")]').first

# 3. Click share icon
share_icon = card_container.locator('div.share-v2.cursor--pointer').first
share_icon.click()

# 4. Wait for modal
modal = page.locator('[data-test="listing-share-modal-container"]')
modal.wait_for(state="visible", timeout=5000)

# 5. Click "To My Followers"
followers_link = modal.locator('a[data-et-name="share_poshmark"]')
followers_link.click()

# 6. Wait for share to complete
page.wait_for_timeout(1000)

# 7. Close modal (optional)
close_btn = modal.locator('[data-test="listing-share-modal-close-btn"]')
close_btn.click()
```

## Selector Stability Analysis

### Most Stable Selectors

1. **Modal**: `[data-test="listing-share-modal-container"]` ✅ Excellent
   - Has dedicated data-test attribute
   - Unlikely to change

2. **Followers Link**: `a[data-et-name="share_poshmark"]` ✅ Good
   - Has analytics tracking attribute
   - Stable for tracking purposes
   - Alternative: Text-based selector `has_text="To My Followers"`

3. **Close Button**: `[data-test="listing-share-modal-close-btn"]` ✅ Excellent
   - Has dedicated data-test attribute

### Selector Recommendations

**Primary (RECOMMENDED)**:
```python
modal = page.locator('[data-test="listing-share-modal-container"]')
followers_link = modal.locator('a[data-et-name="share_poshmark"]')
```

**Fallback**:
```python
modal = page.locator('.modal.simple-modal')
followers_link = modal.get_by_text("To My Followers")
```

## Key Findings Summary

| Element | Type | Selector | Stability |
|---------|------|----------|-----------|
| Modal | DIV | `[data-test="listing-share-modal-container"]` | ✅ Excellent |
| Followers Control | A (anchor) | `a[data-et-name="share_poshmark"]` | ✅ Good |
| Close Button | BUTTON | `[data-test="listing-share-modal-close-btn"]` | ✅ Excellent |

## Important Notes

1. **Not a button**: The "To My Followers" control is an `<a>` element, not a `<button>`
2. **No href**: The anchor has no href attribute (uses JavaScript click handler)
3. **No data-test**: The followers link lacks a data-test attribute
4. **Analytics tracking**: Uses `data-et-name="share_poshmark"` for event tracking
5. **Text-based selection**: Text "To My Followers" is stable and can be used
6. **Modal appears quickly**: ~1-2 second wait is sufficient

## Next Steps

1. ✅ Modal selector discovered: `[data-test="listing-share-modal-container"]`
2. ✅ Followers control discovered: `a[data-et-name="share_poshmark"]`
3. ⏳ Implement in share_engine.py (awaiting approval)
4. ⏳ Test complete share flow
5. ⏳ Add error handling and retries

## Status

**DO NOT modify share_engine.py yet - awaiting approval.**

All selectors have been discovered and documented. Ready for implementation upon approval.
