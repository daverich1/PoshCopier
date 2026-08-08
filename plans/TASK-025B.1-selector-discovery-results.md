# TASK-025B.1: Closet Card Share Selector Discovery Results

## Target Page
https://poshmark.com/closet/dveshop

## Discovery Date
2026-08-07

## Key Findings

### 1. Card Structure
- **Container**: `DIV` with class `tiles_container m--t--1`
- **Total cards found**: 145 listing cards
- **No buttons** found within individual listing cards (0 buttons)
- **No hover-activated controls** detected

### 2. Share Control Discovery

#### ✅ SHARE ICON FOUND

**Location**: SVG icon within the listing card

**Parent Element**:
- Tag: `DIV`
- Class: `share-v2 d--fl ai--c cursor--pointer share-v2--circle-fill`
- aria-label: None
- title: None
- role: None

**Recommended Selector**:
```python
# Within a card element, find the share icon by class
share_icon = card.locator('.share-v2.cursor--pointer')
# OR more specific:
share_icon = card.locator('div.share-v2.share-v2--circle-fill')
```

### 3. Other Controls Found

#### Like Button
- Parent class: `like-v2 d--fl ai--c cursor--pointer like-v2--circle`
- Also an SVG icon, similar structure to share

### 4. Card Identification

**Listing URL Pattern**:
- Found in anchor href: `/listing/{title-slug}-{listing-id}`
- Example: `/listing/Cougar-CardiffWaterproof-Insulated-WinterBoots-6a761e1d71a003337f5bac56`

**Card Selector**:
```python
# Cards can be identified by:
# 1. Presence of listing link
cards = page.locator('a[href*="/listing/"]').locator('xpath=ancestor::div[contains(@class, "tile")]')
# OR
# 2. By the tile container structure
cards = page.locator('.tiles_container > div')
```

### 5. Parent Container Structure

**Parent**: 
- Tag: `SECTION`
- Class: `main__column col-l19 col-x16`
- Contains 2 buttons (likely page-level controls, not card-level)

**Grandparent**:
- Tag: `DIV`
- Also contains 2 buttons

### 6. Important Notes

1. **No traditional button elements** - The share control is a clickable DIV with SVG, not a `<button>`
2. **No data-test attributes** - Poshmark doesn't use data-test attributes on these elements
3. **No aria-labels** - The share icon lacks accessibility labels
4. **No hover-only controls** - Share icon is visible without hovering
5. **Class-based selection required** - Must use CSS class selectors

### 7. Recommended Implementation Strategy

```python
# Step 1: Get all listing cards
cards = page.locator('a[href*="/listing/"]')

# Step 2: For each card, find the share icon
for card in cards:
    # Navigate up to the card container
    card_container = card.locator('xpath=ancestor::div[contains(@class, "tile")]').first
    
    # Find share icon within card
    share_icon = card_container.locator('div.share-v2.cursor--pointer').first
    
    # Click to share
    share_icon.click()
    
    # Handle share modal (separate discovery needed)
```

### 8. Next Steps

1. ✅ Share icon selector discovered: `.share-v2.cursor--pointer`
2. ⏳ Need to discover share modal selectors (after clicking share icon)
3. ⏳ Need to discover "Share to My Followers" button selector
4. ⏳ Implement in share_engine.py (awaiting approval)

### 9. Exact DOM Evidence

**SVG Parent Element** (Share Icon):
```
Tag: DIV
Class: share-v2 d--fl ai--c cursor--pointer share-v2--circle-fill
Parent aria-label: None
Parent title: None
Parent role: None
```

**Card Container**:
```
Tag: DIV
Class: tiles_container m--t--1
data-test: None
data-testid: None
```

## Conclusion

The share control on closet cards is a **DIV element with class `share-v2`** containing an SVG icon. It is:
- ✅ Visible without hover
- ✅ Clickable
- ✅ Identifiable by unique class name
- ❌ Not a button element
- ❌ No data-test attribute
- ❌ No aria-label

**DO NOT modify share_engine.py yet - awaiting approval.**
