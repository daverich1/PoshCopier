"""
Party Discovery Tool for Poshmark Parties Page.

This script analyzes the DOM structure of Poshmark's Parties page to:
1. Extract party schedules (today/tomorrow)
2. Discover party card selectors
3. Navigate to party detail pages
4. Extract official party guidelines
5. Propose eligibility rules and data models

Target: https://poshmark.com/parties

Usage:
    python tools/test_party_discovery.py

Requirements:
- Does NOT implement automatic party sharing
- Does NOT modify sharing/share_engine.py
- Only discovers structure and proposes designs

The browser will pause at key points for manual inspection.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout, Locator

from login import open_logged_in_browser
from runtime_paths import DESTINATION_STATE_FILE


@dataclass
class SelectorInfo:
    """Information about a discovered selector."""
    element_type: str  # e.g., "party_card", "guidelines_button"
    recommended_selector: str
    tag: str
    classes: str
    id: str | None
    role: str | None
    aria_label: str | None
    data_test: str | None
    data_testid: str | None
    text_content_sample: str | None


def safe_str(text: str | None) -> str:
    """Convert text to ASCII-safe string for Windows console."""
    if text is None:
        return "None"
    # Replace non-ASCII characters with '?'
    return text.encode('ascii', errors='replace').decode('ascii')


def print_step(message: str) -> None:
    """Print a step header."""
    print("\n" + "=" * 80)
    print(message)
    print("=" * 80)


def print_subsection(message: str) -> None:
    """Print a subsection header."""
    print("\n" + "-" * 80)
    print(message)
    print("-" * 80)


@dataclass
class PartyCardData:
    """Data extracted from a party card on the list page."""
    party_name: str
    party_url: str
    start_time_text: str
    day_label: str  # e.g., "Today", "Tomorrow", or date
    hosts: list[str]
    image_url: str | None
    is_live: bool
    card_index: int
    selector_info: dict  # Selector metadata for this card


@dataclass
class PartyGuidelines:
    """Official party guidelines extracted from detail page."""
    theme: str
    brands_allowed: list[str]
    categories_allowed: list[str]
    departments_allowed: list[str]
    sizes_allowed: list[str]
    other_rules: list[str]


@dataclass
class PoshPartyProposal:
    """Proposed production data model for a Posh Party."""
    party_id: str
    name: str
    url: str
    start_at: str | None  # ISO datetime string
    start_time_text: str
    is_live: bool
    theme: str
    brands_allowed: list[str]
    categories_allowed: list[str]
    departments_allowed: list[str]
    sizes_allowed: list[str]
    other_rules: list[str]
    party_type: str  # UNIVERSAL, CATEGORY_LIMITED, BRAND_LIMITED, MIXED, UNKNOWN
    eligibility_rules: dict  # Structured eligibility metadata


@dataclass
class DiscoveryResults:
    """Complete results from party discovery."""
    parties_discovered: list[dict]
    selectors_discovered: list[dict]
    sample_party_json: dict | None
    guideline_extraction_success: bool
    known_unknowns: list[str]


def extract_party_cards(page: Page) -> tuple[list[PartyCardData], list[SelectorInfo]]:
    """
    Extract all party cards from the parties list page.
    
    Returns (list of PartyCardData, list of SelectorInfo) in display order.
    """
    print_step("PHASE 1: PARTY LIST PAGE - EXTRACTING PARTY CARDS")
    
    # Wait for page to load
    print("\nWaiting for party cards to load...")
    try:
        page.wait_for_selector('[class*="party"], [class*="Party"], article, .card', timeout=10000)
    except PlaywrightTimeout:
        print("WARNING: No party cards found with initial selectors")
    
    # Discover party card structure
    print("\nDiscovering party card selectors...")
    
    result = page.evaluate("""
        () => {
            // Primary strategy: Find all party links and deduplicate by URL
            const partyLinks = Array.from(document.querySelectorAll('a[href*="/party/"]'));
            
            if (partyLinks.length === 0) {
                return {
                    success: false,
                    error: 'No party links found',
                    strategies_tried: ['a[href*="/party/"]'],
                };
            }
            
            // Deduplicate by party URL
            const seenUrls = new Set();
            const uniqueParties = [];
            
            for (const link of partyLinks) {
                const url = link.href;
                
                // Skip if we've already seen this URL
                if (seenUrls.has(url)) {
                    continue;
                }
                seenUrls.add(url);
                
                // Find the containing card (walk up the DOM)
                let card = link;
                while (card && card !== document.body) {
                    // Look for a container that has both the link and other party info
                    const hasImage = card.querySelector('img');
                    const text = card.textContent || '';
                    const hasTime = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(text);
                    
                    if (hasImage || hasTime) {
                        break;  // Found a good container
                    }
                    card = card.parentElement;
                }
                
                uniqueParties.push({ link, card });
            }
            
            // Extract data from each unique party
            const parties = uniqueParties.map((item, index) => {
                const { link, card } = item;
                const url = link.href;
                
                // Find party name/title
                const titleSelectors = [
                    'h1', 'h2', 'h3', 'h4',
                    '[class*="title" i]',
                    '[class*="name" i]',
                    '[class*="heading" i]',
                ];
                let title = null;
                for (const sel of titleSelectors) {
                    const el = card.querySelector(sel);
                    if (el && el.textContent.trim()) {
                        title = el.textContent.trim();
                        break;
                    }
                }
                
                // If no title found, try link text
                if (!title && link) {
                    title = link.textContent.trim().split('\\n')[0];
                }
                
                // Find time text
                const fullText = card.textContent || '';
                const timeMatch = fullText.match(/(Today|Tomorrow|\\w+day)\\s+at\\s+\\d{1,2}:\\d{2}\\s*(AM|PM)/i) ||
                                 fullText.match(/\\d{1,2}:\\d{2}\\s*(AM|PM)/i);
                const timeText = timeMatch ? timeMatch[0] : '';
                
                // Determine day label
                let dayLabel = '';
                if (/Today/i.test(fullText)) {
                    dayLabel = 'Today';
                } else if (/Tomorrow/i.test(fullText)) {
                    dayLabel = 'Tomorrow';
                } else {
                    const dayMatch = fullText.match(/(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)/i);
                    dayLabel = dayMatch ? dayMatch[0] : '';
                }
                
                // Check if live
                const isLive = /live/i.test(fullText) || /happening now/i.test(fullText);
                
                // Find hosts
                const hosts = [];
                const hostElements = card.querySelectorAll('[class*="host" i], [class*="Host"]');
                hostElements.forEach(el => {
                    const hostText = el.textContent.trim();
                    if (hostText && !hosts.includes(hostText)) {
                        hosts.push(hostText);
                    }
                });
                
                // Find image
                const img = card.querySelector('img');
                const imageUrl = img ? (img.src || img.getAttribute('data-src')) : null;
                
                // Get card attributes for selector analysis
                const cardClasses = card.className;
                const cardTag = card.tagName.toLowerCase();
                const cardId = card.id;
                const cardRole = card.getAttribute('role');
                const cardDataTest = card.getAttribute('data-test');
                const cardDataTestId = card.getAttribute('data-testid');
                
                // Get link attributes
                const linkTag = link ? link.tagName.toLowerCase() : null;
                const linkClasses = link ? link.className : null;
                const linkDataTest = link ? link.getAttribute('data-test') : null;
                const linkDataTestId = link ? link.getAttribute('data-testid') : null;
                
                return {
                    party_name: title || 'Unknown',
                    party_url: url,
                    start_time_text: timeText,
                    day_label: dayLabel,
                    hosts: hosts,
                    image_url: imageUrl,
                    is_live: isLive,
                    card_index: index,
                    // Selector info
                    selector_info: {
                        card_tag: cardTag,
                        card_classes: cardClasses,
                        card_id: cardId,
                        card_role: cardRole,
                        card_data_test: cardDataTest,
                        card_data_testid: cardDataTestId,
                        link_tag: linkTag,
                        link_classes: linkClasses,
                        link_data_test: linkDataTest,
                        link_data_testid: linkDataTestId,
                        full_text_sample: fullText.substring(0, 200),
                    },
                };
            });
            
            return {
                success: true,
                strategy_used: 'party-link-deduplication',
                selector_used: 'a[href*="/party/"]',
                party_count: parties.length,
                parties: parties,
            };
        }
    """)
    
    if not result['success']:
        print(f"\nERROR: {result['error']}")
        print(f"Strategies tried: {', '.join(result['strategies_tried'])}")
        return [], []
    
    print(f"\n[OK] Strategy used: {result['strategy_used']}")
    print(f"[OK] Selector: {result['selector_used']}")
    print(f"[OK] Found {result['party_count']} party cards")
    
    # Create selector info for the card container
    card_selector = SelectorInfo(
        element_type="party_card_container",
        recommended_selector=result['selector_used'],
        tag="varies",
        classes="varies",
        id=None,
        role=None,
        aria_label=None,
        data_test=None,
        data_testid=None,
        text_content_sample=None,
    )
    
    selectors = [card_selector]
    
    # Convert to PartyCardData objects
    parties = []
    for p in result['parties']:
        party = PartyCardData(
            party_name=p['party_name'],
            party_url=p['party_url'],
            start_time_text=p['start_time_text'],
            day_label=p['day_label'],
            hosts=p['hosts'],
            image_url=p['image_url'],
            is_live=p['is_live'],
            card_index=p['card_index'],
            selector_info=p['selector_info'],
        )
        parties.append(party)
        
        print(f"\n  Party {p['card_index'] + 1}:")
        print(f"    Name: {safe_str(party.party_name)}")
        print(f"    Time: {safe_str(party.start_time_text)}")
        print(f"    Day: {safe_str(party.day_label)}")
        print(f"    Live: {party.is_live}")
        print(f"    URL: {party.party_url}")
        print(f"    Hosts: {', '.join(party.hosts) if party.hosts else 'None'}")
        
        # Print selector info
        si = p['selector_info']
        print(f"    Selector - Card Tag: {si['card_tag']}")
        print(f"    Selector - Card ID: {si['card_id'] or 'None'}")
        print(f"    Selector - Card data-test: {si['card_data_test'] or 'None'}")
        print(f"    Selector - Card data-testid: {si['card_data_testid'] or 'None'}")
        print(f"    Selector - Link data-test: {si['link_data_test'] or 'None'}")
        print(f"    Selector - Link data-testid: {si['link_data_testid'] or 'None'}")
    
    return parties, selectors


def extract_party_guidelines(page: Page, party_url: str) -> tuple[PartyGuidelines | None, list[SelectorInfo]]:
    """
    Navigate to a party detail page and extract official guidelines.
    
    Returns (PartyGuidelines or None, list of SelectorInfo).
    """
    print_step("PHASE 2: PARTY DETAIL PAGE - EXTRACTING GUIDELINES")
    
    selectors = []
    
    print(f"\nNavigating to: {party_url}")
    try:
        page.goto(party_url, wait_until='domcontentloaded', timeout=15000)
        page.wait_for_load_state('networkidle', timeout=10000)
    except PlaywrightTimeout:
        print("WARNING: Page load timeout, continuing anyway...")
    
    print("\nSearching for 'Show Posh Party Guidelines' button...")
    
    # Discover the guidelines toggle button (support both upcoming and live parties)
    result = page.evaluate("""
        () => {
            // Search for guidelines button/link
            // Upcoming parties: "Show Posh Party Guidelines"
            // Live parties: "View party details"
            const searchStrings = [
                'Show Posh Party Guidelines',
                'Posh Party Guidelines',
                'View party details',
                'Party Guidelines',
                'Guidelines',
            ];
            
            let guidelinesButton = null;
            let buttonType = null;
            
            for (const searchStr of searchStrings) {
                // Try button elements
                const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (const btn of buttons) {
                    if (btn.textContent.includes(searchStr)) {
                        guidelinesButton = btn;
                        buttonType = searchStr;
                        break;
                    }
                }
                if (guidelinesButton) break;
            }
            
            if (!guidelinesButton) {
                return {
                    success: false,
                    error: 'Guidelines button not found',
                };
            }
            
            // Extract button attributes
            return {
                success: true,
                buttonType: buttonType,
                button: {
                    tag: guidelinesButton.tagName.toLowerCase(),
                    text: guidelinesButton.textContent.trim(),
                    className: guidelinesButton.className,
                    id: guidelinesButton.id,
                    role: guidelinesButton.getAttribute('role'),
                    ariaLabel: guidelinesButton.getAttribute('aria-label'),
                    ariaExpanded: guidelinesButton.getAttribute('aria-expanded'),
                    dataTest: guidelinesButton.getAttribute('data-test'),
                    dataTestId: guidelinesButton.getAttribute('data-testid'),
                },
            };
        }
    """)
    
    if not result['success']:
        print(f"\nERROR: {result['error']}")
        print("Guidelines button not found on this party page.")
        return None, selectors
    
    btn = result['button']
    print(f"\n[OK] Found guidelines button:")
    print(f"  Tag: {btn['tag']}")
    print(f"  Text: {safe_str(btn['text'])}")
    print(f"  Class: {safe_str(btn['className'][:100])}")
    print(f"  ID: {btn['id'] or 'None'}")
    print(f"  Role: {btn['role'] or 'None'}")
    print(f"  aria-label: {btn['ariaLabel'] or 'None'}")
    print(f"  aria-expanded: {btn['ariaExpanded'] or 'None'}")
    print(f"  data-test: {btn['dataTest'] or 'None'}")
    print(f"  data-testid: {btn['dataTestId'] or 'None'}")
    
    print(f"\n  Recommended selector: button:has-text('Posh Party Guidelines')")
    
    # Click the button
    print("\nClicking guidelines button...")
    try:
        page.click("button:has-text('Guidelines'), a:has-text('Guidelines')", timeout=5000)
        page.wait_for_timeout(1000)  # Wait for animation
    except PlaywrightTimeout:
        print("WARNING: Could not click guidelines button")
        return None
    
    # Extract guidelines content
    print("\nExtracting guidelines content...")
    
    guidelines_result = page.evaluate("""
        () => {
            // Look for guidelines content container
            const containers = Array.from(document.querySelectorAll(
                '[class*="guideline" i], [class*="modal" i], [class*="dialog" i], ' +
                '[role="dialog"], [class*="content" i]'
            ));
            
            let guidelinesContainer = null;
            for (const container of containers) {
                const text = container.textContent || '';
                if (text.includes('Theme') || text.includes('Brands') || 
                    text.includes('Categories') || text.includes('Departments')) {
                    guidelinesContainer = container;
                    break;
                }
            }
            
            if (!guidelinesContainer) {
                return {
                    success: false,
                    error: 'Guidelines content not found',
                };
            }
            
            const fullText = guidelinesContainer.textContent || '';
            
            // Extract structured fields
            const extractField = (label) => {
                const regex = new RegExp(label + '\\\\s*:?\\\\s*([^\\\\n]+)', 'i');
                const match = fullText.match(regex);
                return match ? match[1].trim() : null;
            };
            
            const extractList = (label) => {
                const value = extractField(label);
                if (!value) return [];
                
                // Split by common delimiters
                const items = value.split(/[,;]|\\s+and\\s+/).map(s => s.trim()).filter(Boolean);
                return items;
            };
            
            const theme = extractField('Theme') || extractField('Party Theme') || '';
            const brands = extractList('Brands Allowed') || extractList('Brands');
            const categories = extractList('Categories Allowed') || extractList('Categories');
            const departments = extractList('Departments Allowed') || extractList('Departments');
            const sizes = extractList('Sizes Allowed') || extractList('Sizes');
            
            // Extract any other rules
            const otherRules = [];
            const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
            for (const line of lines) {
                if (line.length > 10 && line.length < 200 &&
                    !line.includes('Theme') && !line.includes('Brands') &&
                    !line.includes('Categories') && !line.includes('Departments') &&
                    !line.includes('Sizes')) {
                    otherRules.push(line);
                }
            }
            
            return {
                success: true,
                guidelines: {
                    theme: theme,
                    brands_allowed: brands.length > 0 ? brands : ['All'],
                    categories_allowed: categories.length > 0 ? categories : ['All'],
                    departments_allowed: departments,
                    sizes_allowed: sizes,
                    other_rules: otherRules.slice(0, 5),  // Limit to 5 rules
                },
                raw_text: fullText.substring(0, 500),
            };
        }
    """)
    
    if not guidelines_result['success']:
        print(f"\nERROR: {guidelines_result['error']}")
        return None, selectors
    
    g = guidelines_result['guidelines']
    print(f"\n[OK] Extracted guidelines:")
    print(f"  Theme: {safe_str(g['theme'])}")
    print(f"  Brands Allowed: {', '.join(g['brands_allowed'])}")
    print(f"  Categories Allowed: {', '.join(g['categories_allowed'])}")
    print(f"  Departments Allowed: {', '.join(g['departments_allowed']) if g['departments_allowed'] else 'None'}")
    print(f"  Sizes Allowed: {', '.join(g['sizes_allowed']) if g['sizes_allowed'] else 'None'}")
    print(f"  Other Rules: {len(g['other_rules'])} rules")
    
    print(f"\n  Raw text sample:")
    print(f"  {safe_str(guidelines_result['raw_text'][:200])}")
    
    guidelines = PartyGuidelines(
        theme=g['theme'],
        brands_allowed=g['brands_allowed'],
        categories_allowed=g['categories_allowed'],
        departments_allowed=g['departments_allowed'],
        sizes_allowed=g['sizes_allowed'],
        other_rules=g['other_rules'],
    )
    
    return guidelines, selectors


def classify_party_type(guidelines: PartyGuidelines) -> str:
    """
    Classify party type based on guidelines.
    
    Returns: UNIVERSAL, CATEGORY_LIMITED, BRAND_LIMITED, MIXED, or UNKNOWN
    """
    brands = [b.lower() for b in guidelines.brands_allowed]
    categories = [c.lower() for c in guidelines.categories_allowed]
    
    brands_all = 'all' in brands or len(brands) == 0
    categories_all = 'all' in categories or len(categories) == 0
    
    if brands_all and categories_all:
        return 'UNIVERSAL'
    elif brands_all and not categories_all:
        return 'CATEGORY_LIMITED'
    elif not brands_all and categories_all:
        return 'BRAND_LIMITED'
    elif not brands_all and not categories_all:
        return 'MIXED'
    else:
        return 'UNKNOWN'


def print_proposals() -> None:
    """Print proposed data models and eligibility algorithm."""
    print_step("PHASE 3-5: PROPOSALS")
    
    print_subsection("PARTY TYPE CLASSIFICATION")
    print("""
Party types based on guidelines:

1. UNIVERSAL
   - Brands Allowed = All
   - Categories Allowed = All
   - Example: Campus Debut

2. CATEGORY_LIMITED
   - Brands Allowed = All
   - Categories restricted (e.g., Men, Women, Kids)
   - Example: Men's Style Posh Party

3. BRAND_LIMITED
   - Brands restricted to specific list
   - Categories = All
   - Example: Designer Party (hypothetical)

4. MIXED
   - Both brands AND categories restricted
   - Example: Luxury Handbags (specific brands + accessories category)

5. UNKNOWN
   - Rules exist that cannot be confidently parsed
   - Requires manual review
""")
    
    print_subsection("ELIGIBILITY ALGORITHM PROPOSAL")
    print("""
Function: is_listing_eligible_for_party(listing, party) -> (status, reason)

Returns: (PartyEligibilityStatus, str)

PartyEligibilityStatus:
- ELIGIBLE: Listing meets all party requirements
- INELIGIBLE: Listing does not meet requirements
- UNKNOWN: Cannot determine eligibility confidently

Algorithm:

1. AVAILABILITY GATE (CRITICAL)
   if listing.availability != AvailabilityStatus.AVAILABLE:
       return (INELIGIBLE, "Listing is not available for sale")
   
   Only AVAILABLE listings may be shared to parties.
   Sold, Not For Sale, Inactive, Unavailable, or Unknown: SKIP.

2. PARTY TYPE CHECK
   party_type = classify_party_type(party.guidelines)
   
   if party_type == UNIVERSAL:
       return (ELIGIBLE, "Universal party - all items allowed")

3. BRAND CHECK
   if party.brands_allowed != ['All']:
       listing_brand_normalized = listing.brand.lower().strip()
       allowed_brands_normalized = [b.lower().strip() for b in party.brands_allowed]
       
       if listing_brand_normalized not in allowed_brands_normalized:
           return (INELIGIBLE, f"Brand '{listing.brand}' not in allowed list")

4. CATEGORY CHECK
   if party.categories_allowed != ['All']:
       # Check department first (Men, Women, Kids)
       if listing.department:
           dept_normalized = listing.department.lower().strip()
           allowed_cats_normalized = [c.lower().strip() for c in party.categories_allowed]
           
           if dept_normalized not in allowed_cats_normalized:
               return (INELIGIBLE, f"Department '{listing.department}' not allowed")
       
       # Then check category/subcategory
       if listing.category:
           cat_normalized = listing.category.lower().strip()
           if cat_normalized not in allowed_cats_normalized:
               return (INELIGIBLE, f"Category '{listing.category}' not allowed")

5. SIZE CHECK (if applicable)
   if party.sizes_allowed:
       if not listing.size:
           return (UNKNOWN, "Party has size restrictions but listing size unknown")
       
       size_normalized = listing.size.lower().strip()
       allowed_sizes_normalized = [s.lower().strip() for s in party.sizes_allowed]
       
       if size_normalized not in allowed_sizes_normalized:
           return (INELIGIBLE, f"Size '{listing.size}' not allowed")

6. OTHER RULES CHECK
   if party.other_rules:
       # Cannot confidently parse arbitrary rules
       return (UNKNOWN, "Party has additional rules requiring manual review")

7. DEFAULT
   return (ELIGIBLE, "Listing meets all party requirements")

Examples:

Listing: Men's Nike Shirt, Size L, AVAILABLE
Party: Men's Style (Categories: Men)
Result: ELIGIBLE - "All brands allowed; listing department Men is allowed"

Listing: Women's Dress, AVAILABLE
Party: Men's Style (Categories: Men)
Result: INELIGIBLE - "Department 'Women' does not match allowed category 'Men'"

Listing: Men's Shirt, SOLD
Party: Men's Style (Categories: Men)
Result: INELIGIBLE - "Listing is not available for sale"

Listing: Designer Bag, AVAILABLE
Party: Luxury Party (Brands: Gucci, Prada, Louis Vuitton)
Result: INELIGIBLE - "Brand 'Designer' not in allowed list"
""")
    
    print_subsection("DATA MODEL PROPOSAL")
    print("""
@dataclass
class PoshParty:
    '''Production data model for a Posh Party.'''
    party_id: str              # Extracted from URL
    name: str                  # Party name/title
    url: str                   # Full party URL
    start_at: datetime | None  # Parsed datetime (None if unparseable)
    start_time_text: str       # Original text: "Today at 7:00 PM"
    is_live: bool              # Whether party is currently happening
    theme: str                 # Party theme from guidelines
    brands_allowed: list[str]  # ['All'] or specific brands
    categories_allowed: list[str]  # ['All'] or specific categories
    departments_allowed: list[str]  # Usually empty or ['Men', 'Women', etc.]
    sizes_allowed: list[str]   # Usually empty unless size-specific party
    other_rules: list[str]     # Additional rules as text
    party_type: str            # UNIVERSAL, CATEGORY_LIMITED, etc.

@dataclass
class PartyEligibilityResult:
    '''Result of eligibility check.'''
    status: PartyEligibilityStatus  # ELIGIBLE, INELIGIBLE, UNKNOWN
    reason: str                     # Human-readable explanation
    party_name: str                 # For logging
    listing_id: str                 # For logging

enum PartyEligibilityStatus:
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"

Storage:
- Store parties in DESTINATION_STATE_FILE alongside followers/following
- Update daily or on-demand
- Cache guidelines to avoid repeated detail page visits
""")


def main():
    """Main execution."""
    print_step("POSHMARK PARTY DISCOVERY TOOL")
    print(f"\nTarget: https://poshmark.com/parties")
    print(f"State file: {DESTINATION_STATE_FILE}")
    print(f"\nThis tool will:")
    print("  1. Extract party schedules from list page")
    print("  2. Discover party card selectors")
    print("  3. Navigate to ONE party detail page")
    print("  4. Extract official guidelines")
    print("  5. Output structured JSON data")
    print("\nStarting browser...")
    
    all_selectors = []
    
    with sync_playwright() as p:
        browser, context, page = open_logged_in_browser(
            p,
            DESTINATION_STATE_FILE,
        )
        
        try:
            # Navigate to parties page
            print("\nNavigating to parties page...")
            page.goto('https://poshmark.com/parties', wait_until='domcontentloaded', timeout=15000)
            page.wait_for_timeout(2000)
            
            # Phase 1: Extract party cards
            parties, card_selectors = extract_party_cards(page)
            all_selectors.extend(card_selectors)
            
            if not parties:
                print("\nERROR: No parties found. Cannot proceed.")
                browser.close()
                return
            
            # Phase 2: Extract guidelines from first party
            print(f"\n\nNavigating to first party for guideline extraction...")
            page.wait_for_timeout(1000)
            
            first_party = parties[0]
            guidelines, guideline_selectors = extract_party_guidelines(page, first_party.party_url)
            all_selectors.extend(guideline_selectors)
            
            sample_party_json = None
            
            if guidelines:
                party_type = classify_party_type(guidelines)
                print(f"\n[OK] Party Type: {party_type}")
                
                # Determine eligibility rules
                brands_restricted = guidelines.brands_allowed != ['All'] and len(guidelines.brands_allowed) > 0
                categories_restricted = guidelines.categories_allowed != ['All'] and len(guidelines.categories_allowed) > 0
                
                eligibility_rules = {
                    "brand_restricted": brands_restricted,
                    "category_restricted": categories_restricted,
                    "size_restricted": len(guidelines.sizes_allowed) > 0,
                    "has_other_rules": len(guidelines.other_rules) > 0,
                }
                
                # Create sample JSON
                sample_party = PoshPartyProposal(
                    party_id=first_party.party_url.split('/')[-1],
                    name=first_party.party_name,
                    url=first_party.party_url,
                    start_at=None,  # Would parse from start_time_text
                    start_time_text=first_party.start_time_text,
                    is_live=first_party.is_live,
                    theme=guidelines.theme,
                    brands_allowed=guidelines.brands_allowed,
                    categories_allowed=guidelines.categories_allowed,
                    departments_allowed=guidelines.departments_allowed,
                    sizes_allowed=guidelines.sizes_allowed,
                    other_rules=guidelines.other_rules,
                    party_type=party_type,
                    eligibility_rules=eligibility_rules,
                )
                
                sample_party_json = asdict(sample_party)
                
                print_subsection("STRUCTURED JSON OUTPUT")
                print(json.dumps(sample_party_json, indent=2))
            
            # Create complete discovery results
            parties_json = []
            for party in parties:
                parties_json.append({
                    "party_name": party.party_name,
                    "party_url": party.party_url,
                    "start_time_text": party.start_time_text,
                    "day_label": party.day_label,
                    "is_live": party.is_live,
                    "hosts": party.hosts,
                    "image_url": party.image_url,
                    "selector_info": party.selector_info,
                })
            
            selectors_json = []
            for selector in all_selectors:
                selectors_json.append(asdict(selector))
            
            known_unknowns = [
                "Time parsing - need to handle 'Today at 7:00 PM' -> datetime",
                "Party ID extraction - may need better logic than URL split",
                "Guidelines parsing - may vary by party type",
                "Size matching - need to normalize size strings",
                "Brand matching - need fuzzy matching for brand names",
                "Category hierarchy - subcategories vs main categories",
                "Live party detection - may need real-time status check",
                "Party schedule updates - how often to refresh",
            ]
            
            results = DiscoveryResults(
                parties_discovered=parties_json,
                selectors_discovered=selectors_json,
                sample_party_json=sample_party_json,
                guideline_extraction_success=guidelines is not None,
                known_unknowns=known_unknowns,
            )
            
            # Save results to file
            results_file = PROJECT_DIR / "plans" / "TASK-025B.3-party-discovery-results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(results), f, indent=2)
            
            print_subsection("COMPLETE RESULTS SAVED")
            print(f"\n[OK] Results saved to: {results_file}")
            print(f"[OK] Parties discovered: {len(parties)}")
            print(f"[OK] Selectors discovered: {len(all_selectors)}")
            print(f"[OK] Guideline extraction: {'Success' if guidelines else 'Failed'}")
            
            # Phase 3-5: Print proposals
            print_proposals()
            
            # Summary
            print_step("SUMMARY")
            print(f"\n[OK] Parties discovered: {len(parties)}")
            print(f"[OK] Party detail page tested: {first_party.party_url}")
            print(f"[OK] Guidelines extracted: {'Yes' if guidelines else 'No'}")
            print(f"[OK] JSON output saved: {results_file}")
            
            print("\n\nNEXT STEPS:")
            print("  1. Review JSON output and selector reliability")
            print("  2. Test with multiple party types (if available)")
            print("  3. Implement production parser in sharing/ module")
            print("  4. Implement eligibility checker")
            print("  5. Integrate with share_engine.py")
            print("  6. Add party schedule caching")
            print("  7. Add automatic party sharing feature")
            
            print("\n\nClosing browser in 3 seconds...")
            page.wait_for_timeout(3000)
            
        except Exception as e:
            print(f"\n\nERROR: {e}")
            import traceback
            traceback.print_exc()
            print("\nClosing browser...")
        finally:
            browser.close()


if __name__ == '__main__':
    main()
