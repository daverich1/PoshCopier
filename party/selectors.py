"""
Production selectors for party discovery and guideline extraction.

Based on confirmed discovery evidence from TASK-025B.
"""

# ============================================================================
# PARTY LIST PAGE SELECTORS
# ============================================================================

# Primary strategy: Find party links by href pattern
# Confirmed from discovery: a[href*="/party/"]
PARTY_LINK_SELECTOR = 'a[href*="/party/"]'

# Alternative: Find party cards by container class
# Use with caution - may include non-party elements
PARTY_CARD_CONTAINER = '[class*="party"]'


# ============================================================================
# PARTY DETAIL PAGE SELECTORS - GUIDELINES BUTTONS
# ============================================================================

# Upcoming party: "Show Posh Party Guidelines" button
GUIDELINES_BUTTON_UPCOMING = [
    'button:has-text("Show Posh Party Guidelines")',
    'button:has-text("Posh Party Guidelines")',
    'a:has-text("Show Posh Party Guidelines")',
    'a:has-text("Posh Party Guidelines")',
]

# Live party: "View party details" button/link
GUIDELINES_BUTTON_LIVE = [
    'button:has-text("View party details")',
    'a:has-text("View party details")',
    'button:has-text("Party details")',
    'a:has-text("Party details")',
]

# Combined selector for any guidelines button
GUIDELINES_BUTTON_ANY = GUIDELINES_BUTTON_UPCOMING + GUIDELINES_BUTTON_LIVE


# ============================================================================
# GUIDELINES CONTENT SELECTORS
# ============================================================================

# Modal container (for live parties)
GUIDELINES_MODAL = [
    '[role="dialog"]',
    '[class*="modal"]',
    '[class*="dialog"]',
]

# Expanded content container (for upcoming parties)
GUIDELINES_CONTENT = [
    '[class*="guideline"]',
    '[class*="party-detail"]',
    '[class*="party-info"]',
]


# ============================================================================
# GUIDELINE FIELD LABELS
# ============================================================================

# Text patterns to search for in guidelines
GUIDELINE_LABELS = {
    'theme': ['Theme', 'Party Theme'],
    'brands': ['Brands Allowed', 'Brands'],
    'categories': ['Categories Allowed', 'Categories'],
    'departments': ['Departments Allowed', 'Departments'],
    'sizes': ['Sizes Allowed', 'Sizes'],
}
