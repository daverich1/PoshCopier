"""
Party Manager for discovering and managing Poshmark parties.

Provides methods to:
- Discover parties from the parties list page
- Load party guidelines (supports both upcoming and live parties)
- Filter for live parties
- Cache management integration

Implements TASK-026B cache architecture.
Does NOT integrate with sharing (separate task).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from party.party_models import (
    PartyType,
    PartyGuidelines,
    PoshParty,
    GuidelineParseConfidence,
)
from party.selectors import (
    PARTY_LINK_SELECTOR,
    GUIDELINES_BUTTON_UPCOMING,
    GUIDELINES_BUTTON_LIVE,
    GUIDELINES_MODAL,
    GUIDELINES_CONTENT,
)
from party.eligibility import classify_party_type
from party.cache import PartyCacheManager


class PartyManager:
    """
    Manages party discovery and guideline extraction with caching.
    
    Usage:
        manager = PartyManager()
        
        # Discover all parties (with cache integration)
        parties = manager.discover_parties(page)
        
        # Load guidelines for a specific party
        guidelines = manager.load_guidelines(page, parties[0])
        
        # Get only live parties
        live_parties = manager.get_live_parties(parties)
        
        # Refresh cache
        manager.refresh_cache(page)
    """
    
    def __init__(self):
        """Initialize PartyManager with cache support."""
        self.cache = PartyCacheManager()
    
    def discover_parties(self, page: Page) -> list[PoshParty]:
        """
        Discover all parties from the parties list page.
        
        Process:
        1. Navigate to https://poshmark.com/parties if needed
        2. Find all unique party links (a[href*="/party/"])
        3. Deduplicate by party URL (one URL = one party)
        4. Extract party metadata from each card
        5. Preserve page display order
        
        Does NOT return nested duplicate DOM elements.
        
        Args:
            page: Playwright page object (should be on parties page)
            
        Returns:
            List of PoshParty objects in display order
        """
        # Navigate to parties page if not already there
        current_url = page.url
        if "/parties" not in current_url:
            try:
                page.goto("https://poshmark.com/parties", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
            except PlaywrightTimeout:
                # Continue anyway - page may have loaded
                pass
        
        # Wait for party links to appear
        try:
            page.wait_for_selector(PARTY_LINK_SELECTOR, timeout=10000)
        except PlaywrightTimeout:
            # No parties found
            return []
        
        # Execute JavaScript to extract party data with diagnostics
        result = page.evaluate("""
            () => {
                // Status/CTA text and section headings to reject as party names
                const REJECT_AS_NAME = [
                    'happening now',
                    'join this party',
                    'view party',
                    'view party details',
                    'live',
                    'upcoming',
                    'party invitations',
                    'shop past parties',
                    'past parties'
                ];
                
                // Find all party links
                const partyLinks = Array.from(document.querySelectorAll('a[href*="/party/"]'));
                
                if (partyLinks.length === 0) {
                    return { success: false, parties: [], diagnostics: [] };
                }
                
                // Deduplicate by URL
                const seenUrls = new Set();
                const uniqueParties = [];
                const diagnostics = [];
                
                for (const link of partyLinks) {
                    const url = link.href;
                    
                    // Skip if already seen
                    if (seenUrls.has(url)) {
                        continue;
                    }
                    seenUrls.add(url);
                    
                    // Find containing card - walk up to find smallest container with THIS party link + time
                    let card = link;
                    let foundCard = false;
                    
                    while (card && card !== document.body) {
                        card = card.parentElement;
                        if (!card) break;
                        
                        const cardText = card.textContent || '';
                        const hasTime = /\\d{1,2}:\\d{2}\\s*(AM|PM)/i.test(cardText);
                        
                        // Check if this card contains ONLY this party link (not multiple)
                        const partyLinksInCard = card.querySelectorAll('a[href*="/party/"]');
                        const thisLinkInCard = Array.from(partyLinksInCard).some(l => l.href === url);
                        
                        // Found card if it contains time, this link, and ideally only this link
                        if (hasTime && thisLinkInCard) {
                            foundCard = true;
                            break;
                        }
                    }
                    
                    if (!foundCard || !card) {
                        card = link.parentElement || link;
                    }
                    
                    const fullText = card.textContent || '';
                    
                    // Collect diagnostic info for first 5 parties
                    const diagnostic = uniqueParties.length < 5 ? {
                        url: url,
                        card_snippet: card.outerHTML ? card.outerHTML.substring(0, 500) : 'N/A',
                        candidate_titles: [],
                        chosen_title: '',
                        candidate_times: [],
                        chosen_time: '',
                        live_evidence: []
                    } : null;
                    
                    // Extract party name - STRICT EXCLUSION of status/CTA text
                    let name = '';
                    const candidateTitles = [];
                    
                    // Strategy 1: Try heading/title elements within THIS card
                    const titleSelectors = ['h1', 'h2', 'h3', 'h4', '[class*="title" i]', '[class*="name" i]'];
                    for (const sel of titleSelectors) {
                        const elements = card.querySelectorAll(sel);
                        for (const el of elements) {
                            const text = el.textContent.trim();
                            if (text && text.length > 3) {
                                candidateTitles.push({source: sel, text: text});
                                
                                const textLower = text.toLowerCase();
                                // Reject status/CTA text
                                if (REJECT_AS_NAME.some(reject => textLower === reject || textLower.startsWith(reject + ' '))) {
                                    continue;
                                }
                                // Reject time-only text
                                if (/^\\d{1,2}:\\d{2}\\s*(AM|PM)$/i.test(text)) {
                                    continue;
                                }
                                // Prefer text containing "Posh Party"
                                if (/posh party/i.test(text)) {
                                    name = text.split('\\n')[0].trim();
                                    break;
                                }
                                // Otherwise use first valid heading
                                if (!name) {
                                    name = text.split('\\n')[0].trim();
                                }
                            }
                        }
                        if (name && /posh party/i.test(name)) break;
                    }
                    
                    // Strategy 2: Find text containing "Posh Party" in card
                    if (!name) {
                        const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
                        for (const line of lines) {
                            if (line.length < 10 || line.length > 200) continue;
                            
                            const lineLower = line.toLowerCase();
                            if (REJECT_AS_NAME.some(reject => lineLower === reject || lineLower.startsWith(reject + ' '))) {
                                continue;
                            }
                            
                            if (/posh party/i.test(line)) {
                                candidateTitles.push({source: 'text-line', text: line});
                                name = line;
                                break;
                            }
                        }
                    }
                    
                    // Strategy 3: Use link text if valid
                    if (!name) {
                        const linkText = link.textContent.trim().split('\\n')[0].trim();
                        const linkTextLower = linkText.toLowerCase();
                        
                        if (linkText &&
                            !REJECT_AS_NAME.some(reject => linkTextLower === reject || linkTextLower.startsWith(reject + ' '))) {
                            candidateTitles.push({source: 'link-text', text: linkText});
                            name = linkText;
                        }
                    }
                    
                    if (diagnostic) {
                        diagnostic.candidate_titles = candidateTitles;
                        diagnostic.chosen_title = name || 'Unknown Party';
                    }
                    
                    // Extract time text from THIS card only
                    const timeMatches = [];
                    const timeMatch1 = fullText.match(/(Today|Tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\s+at\\s+\\d{1,2}:\\d{2}\\s*(AM|PM)/i);
                    const timeMatch2 = fullText.match(/\\d{1,2}:\\d{2}\\s*(AM|PM)/i);
                    
                    if (timeMatch1) timeMatches.push(timeMatch1[0]);
                    if (timeMatch2 && timeMatch2[0] !== timeMatch1?.[0]) timeMatches.push(timeMatch2[0]);
                    
                    const timeText = timeMatch1 ? timeMatch1[0] : (timeMatch2 ? timeMatch2[0] : '');
                    
                    if (diagnostic) {
                        diagnostic.candidate_times = timeMatches;
                        diagnostic.chosen_time = timeText;
                    }
                    
                    // Check if live from THIS card only
                    const liveEvidence = [];
                    if (/ends in/i.test(fullText)) liveEvidence.push('ends in');
                    if (/live now/i.test(fullText)) liveEvidence.push('live now');
                    if (/happening now/i.test(fullText)) liveEvidence.push('happening now');
                    if (/currently live/i.test(fullText)) liveEvidence.push('currently live');
                    
                    const isLive = liveEvidence.length > 0;
                    
                    if (diagnostic) {
                        diagnostic.live_evidence = liveEvidence;
                        diagnostics.push(diagnostic);
                    }
                    
                    uniqueParties.push({
                        name: name || 'Unknown Party',
                        url: url,
                        time_text: timeText,
                        is_live: isLive,
                    });
                }
                
                return { success: true, parties: uniqueParties, diagnostics: diagnostics };
            }
        """)
        
        if not result["success"]:
            return []
        
        # Print diagnostics for first 5 parties
        if result.get("diagnostics"):
            print("\n" + "=" * 80)
            print("PARTY METADATA DIAGNOSTICS (First 5 Parties)")
            print("=" * 80)
            
            for i, diag in enumerate(result["diagnostics"], 1):
                print(f"\n--- Party {i} ---")
                print(f"URL: {diag['url']}")
                print(f"\nCard snippet (first 500 chars):")
                print(f"  {diag['card_snippet'][:200]}...")
                print(f"\nCandidate titles:")
                for ct in diag['candidate_titles']:
                    print(f"  [{ct['source']}] {ct['text']}")
                print(f"\nChosen title: {diag['chosen_title']}")
                print(f"\nCandidate times: {diag['candidate_times']}")
                print(f"Chosen time: {diag['chosen_time']}")
                print(f"\nLive evidence: {diag['live_evidence']}")
        
        # Convert to PoshParty objects
        parties = []
        for party_data in result["parties"]:
            # Extract party ID from URL
            party_id = self._extract_party_id(party_data["url"])
            
            # Parse start time (if possible)
            start_at = self._parse_start_time(party_data["time_text"])
            
            party = PoshParty(
                party_id=party_id,
                name=party_data["name"],
                url=party_data["url"],
                start_time_text=party_data["time_text"],
                start_at=start_at,
                is_live=party_data["is_live"],
                guidelines=None,  # Not loaded yet
                party_type=PartyType.UNKNOWN,  # Will be set after loading guidelines
            )
            parties.append(party)
        
        return parties
    
    def load_guidelines(self, page: Page, party: PoshParty) -> PartyGuidelines | None:
        """
        Load party guidelines from the party detail page.
        
        Supports BOTH UI states:
        
        Upcoming party:
        - Find "Show Posh Party Guidelines" button
        - Click to expand
        - Parse expanded content
        
        Live party:
        - Find "View party details" button/link
        - Click to open modal
        - Wait for modal to appear
        - Parse modal content
        
        Both paths return the same PartyGuidelines model.
        
        Extraction rules:
        - If field says "All": store ["All"]
        - If field is absent: store []
        - If parsing is ambiguous: preserve text in other_rules
        - Do not guess
        
        Args:
            page: Playwright page object
            party: PoshParty to load guidelines for
            
        Returns:
            PartyGuidelines or None if guidelines cannot be loaded
        """
        # Navigate to party page
        try:
            page.goto(party.url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1500)
        except PlaywrightTimeout:
            return None
        
        # UPDATE: Detect live status from party detail page
        live_evidence = page.evaluate("""
            () => {
                const bodyText = document.body.textContent || '';
                return {
                    has_ends_in: /ends in/i.test(bodyText),
                    has_live_now: /live now/i.test(bodyText),
                    has_happening_now: /happening now/i.test(bodyText),
                };
            }
        """)
        
        # Update is_live if we have authoritative evidence
        if live_evidence["has_ends_in"] or live_evidence["has_live_now"] or live_evidence["has_happening_now"]:
            party.is_live = True
        
        # Try to find and click guidelines button
        clicked = False
        button_found = None
        
        print(f"  [DEBUG] Attempting to load guidelines for: {party.name}")
        print(f"  [DEBUG] Party is_live: {party.is_live}")
        
        # Try upcoming party buttons first
        for selector in GUIDELINES_BUTTON_UPCOMING:
            try:
                button = page.locator(selector).first
                if button.count() > 0 and button.is_visible(timeout=1000):
                    print(f"  [DEBUG] Found upcoming button: {selector}")
                    button.click(timeout=3000)
                    page.wait_for_timeout(1000)  # Wait for expansion
                    clicked = True
                    button_found = selector
                    break
            except (PlaywrightTimeout, Exception) as e:
                print(f"  [DEBUG] Upcoming button {selector} failed: {type(e).__name__}")
                continue
        
        # Try live party buttons if upcoming didn't work
        if not clicked:
            for selector in GUIDELINES_BUTTON_LIVE:
                try:
                    button = page.locator(selector).first
                    if button.count() > 0 and button.is_visible(timeout=1000):
                        print(f"  [DEBUG] Found live button: {selector}")
                        button.click(timeout=3000)
                        # Wait for modal to appear
                        for modal_selector in GUIDELINES_MODAL:
                            try:
                                page.wait_for_selector(modal_selector, timeout=3000)
                                print(f"  [DEBUG] Modal appeared: {modal_selector}")
                                clicked = True
                                button_found = selector
                                break
                            except PlaywrightTimeout:
                                print(f"  [DEBUG] Modal {modal_selector} did not appear")
                                continue
                        if clicked:
                            break
                except (PlaywrightTimeout, Exception) as e:
                    print(f"  [DEBUG] Live button {selector} failed: {type(e).__name__}")
                    continue
        
        if not clicked:
            # Could not find or click guidelines button
            print("  [DEBUG] No guidelines button found or clicked")
            
            # Debug: Check what buttons/links are available
            all_buttons = page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    return buttons.slice(0, 20).map(b => ({
                        tag: b.tagName,
                        text: b.textContent.trim().substring(0, 50),
                        visible: b.offsetParent !== null
                    }));
                }
            """)
            print(f"  [DEBUG] Available buttons/links (first 20):")
            for btn in all_buttons:
                if btn['visible']:
                    print(f"    {btn['tag']}: {btn['text']}")
            
            return None
        
        print(f"  [DEBUG] Successfully clicked: {button_found}")
        
        # Wait a moment for modal to fully render
        page.wait_for_timeout(500)
        
        # Extract guidelines content
        guidelines_data = self._extract_guidelines_content(page)
        
        if not guidelines_data:
            return None
        
        # Close the modal if it's still open
        try:
            # Try to find and click close button
            close_selectors = [
                '[role="dialog"] button[aria-label*="close" i]',
                '[role="dialog"] button[title*="close" i]',
                '[class*="modal"] button[aria-label*="close" i]',
                '[class*="modal"] button[title*="close" i]',
                '[role="dialog"] [class*="close" i]',
                '[class*="modal"] [class*="close" i]',
            ]
            
            closed = False
            for selector in close_selectors:
                try:
                    close_btn = page.locator(selector).first
                    if close_btn.count() > 0 and close_btn.is_visible(timeout=500):
                        print(f"  [DEBUG] Closing modal with: {selector}")
                        close_btn.click(timeout=1000)
                        closed = True
                        break
                except:
                    continue
            
            # Fallback: press Escape
            if not closed:
                print("  [DEBUG] Closing modal with Escape key")
                page.keyboard.press("Escape")
            
            # Wait for modal to close
            page.wait_for_timeout(500)
            print("  [DEBUG] Modal closed")
        except Exception as e:
            print(f"  [DEBUG] Modal close failed: {type(e).__name__}")
        
        # Determine parse confidence based on extracted data
        confidence = self._determine_parse_confidence(guidelines_data)
        
        # Create PartyGuidelines object
        guidelines = PartyGuidelines(
            theme=guidelines_data.get("theme", ""),
            brands_allowed=guidelines_data.get("brands_allowed", []),
            categories_allowed=guidelines_data.get("categories_allowed", []),
            departments_allowed=guidelines_data.get("departments_allowed", []),
            sizes_allowed=guidelines_data.get("sizes_allowed", []),
            other_rules=guidelines_data.get("other_rules", []),
            extra_fields=guidelines_data.get("extra_fields", {}),
            parse_confidence=confidence,
            parsed_at=datetime.now(),
        )
        
        # Update party with guidelines and type
        party.guidelines = guidelines
        party.party_type = classify_party_type(guidelines)
        
        return guidelines
    
    def get_live_parties(self, parties: list[PoshParty]) -> list[PoshParty]:
        """
        Filter for parties that are confidently detected as live.
        
        Only returns parties where is_live=True.
        Does not infer live status from current time unless necessary.
        
        Args:
            parties: List of PoshParty objects
            
        Returns:
            List of live parties
        """
        return [party for party in parties if party.is_live]
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _extract_party_id(self, url: str) -> str:
        """
        Extract party ID from party URL.
        
        URL format: https://poshmark.com/party/[party-name-slug]
        
        Args:
            url: Full party URL
            
        Returns:
            Party ID (last segment of URL path)
        """
        # Remove query params and trailing slash
        url = url.split("?")[0].rstrip("/")
        
        # Get last segment
        segments = url.split("/")
        if len(segments) > 0:
            return segments[-1]
        
        return "unknown"
    
    def _parse_start_time(self, time_text: str) -> datetime | None:
        """
        Parse start time from text like "Today at 7:00 PM".
        
        This is a basic implementation. More sophisticated parsing
        can be added later if needed.
        
        Args:
            time_text: Time text from party card
            
        Returns:
            Parsed datetime or None if unparseable
        """
        # For now, return None - parsing can be added later
        # This would require handling "Today", "Tomorrow", day names, etc.
        return None
    
    def _extract_guidelines_content(self, page: Page) -> dict[str, Any] | None:
        """
        Extract guidelines content from the page.
        
        Searches for guidelines container and parses structured fields.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dict with guideline fields or None if extraction fails
        """
        result = page.evaluate("""
            () => {
                // Find guidelines container - SUPPORTS BOTH MODAL AND INLINE EXPANSION
                let container = null;
                let containerSource = '';
                
                // Strategy 1: Look for [role="dialog"] modal (live party)
                const dialogs = document.querySelectorAll('[role="dialog"]');
                for (const dialog of dialogs) {
                    // Check if visible
                    if (dialog.offsetParent === null) continue;
                    
                    const dialogText = dialog.textContent || '';
                    // Must contain guideline fields
                    if (dialogText.includes('Theme') &&
                        (dialogText.includes('Brands Allowed') || dialogText.includes('Categories Allowed'))) {
                        container = dialog;
                        containerSource = 'role=dialog';
                        break;
                    }
                }
                
                // Strategy 2: Look for visible modal by class (live party fallback)
                if (!container) {
                    const modals = document.querySelectorAll('[class*="modal" i]');
                    for (const modal of modals) {
                        // Check if visible
                        if (modal.offsetParent === null) continue;
                        
                        const modalText = modal.textContent || '';
                        if (modalText.includes('Theme') &&
                            (modalText.includes('Brands Allowed') || modalText.includes('Categories Allowed'))) {
                            container = modal;
                            containerSource = 'class=modal';
                            break;
                        }
                    }
                }
                
                // Strategy 3: Look for expanded guidelines section (upcoming party - INLINE EXPANSION)
                if (!container) {
                    const guidelineElements = document.querySelectorAll('[class*="guideline" i]');
                    for (const el of guidelineElements) {
                        // Check if visible
                        if (el.offsetParent === null) continue;
                        
                        const text = el.textContent || '';
                        // Must contain Theme AND at least one other guideline field
                        if (text.includes('Theme') &&
                            (text.includes('Brands Allowed') || text.includes('Categories Allowed'))) {
                            container = el;
                            containerSource = 'guideline-element';
                            break;
                        }
                    }
                }
                
                // Strategy 4: Look for any visible container with guideline content (upcoming party fallback)
                if (!container) {
                    // Search all divs for guideline content
                    const allDivs = document.querySelectorAll('div');
                    for (const div of allDivs) {
                        // Must be visible
                        if (div.offsetParent === null) continue;
                        
                        const text = div.textContent || '';
                        // Must contain Theme AND at least one other guideline field
                        if (text.includes('Theme') &&
                            (text.includes('Brands Allowed') || text.includes('Categories Allowed'))) {
                            // Ensure it's not too large (avoid body/main containers)
                            const textLength = text.length;
                            if (textLength > 100 && textLength < 5000) {
                                container = div;
                                containerSource = 'inline-expanded-div';
                                break;
                            }
                        }
                    }
                }
                
                // Strategy 5: Fallback to party-detail container
                if (!container) {
                    const detailElements = document.querySelectorAll('[class*="party-detail" i], [class*="party-info" i]');
                    for (const el of detailElements) {
                        const text = el.textContent || '';
                        if (text.includes('Theme')) {
                            container = el;
                            containerSource = 'party-detail';
                            break;
                        }
                    }
                }
                
                if (!container) {
                    return {
                        found: false,
                        debug: {
                            dialog_count: document.querySelectorAll('[role="dialog"]').length,
                            modal_count: document.querySelectorAll('[class*="modal" i]').length,
                        }
                    };
                }
                
                // CRITICAL: Exclude sidebar/filter containers
                const containerClass = container.className || '';
                if (containerClass.includes('filter') || containerClass.includes('sidebar')) {
                    return {
                        found: false,
                        debug: { rejected: 'filter/sidebar container' }
                    };
                }
                
                const fullText = container.textContent || '';
                
                // Helper to extract field value
                const extractField = (labels) => {
                    for (const label of labels) {
                        const regex = new RegExp(label + '\\\\s*:?\\\\s*([^\\\\n]+)', 'i');
                        const match = fullText.match(regex);
                        if (match) {
                            return match[1].trim();
                        }
                    }
                    return null;
                };
                
                // Helper to extract list
                const extractList = (labels) => {
                    const value = extractField(labels);
                    if (!value) return [];
                    
                    // Check if "All"
                    if (/^all$/i.test(value.trim())) {
                        return ['All'];
                    }
                    
                    // Split by common delimiters
                    const items = value.split(/[,;]|\\s+and\\s+/)
                        .map(s => s.trim())
                        .filter(Boolean);
                    
                    return items.length > 0 ? items : [];
                };
                
                // Extract fields
                const theme = extractField(['Theme', 'Party Theme']) || '';
                const brands = extractList(['Brands Allowed', 'Brands']);
                const categories = extractList(['Categories Allowed', 'Categories']);
                const departments = extractList(['Departments Allowed', 'Departments']);
                // FIXED: Only match explicit "Sizes Allowed" field
                const sizes = extractList(['Sizes Allowed']);
                
                // Extract other rules - ONLY actual eligibility restrictions
                // Distinguish between informational text and restrictions
                const otherRules = [];
                const lines = fullText.split('\\n').map(l => l.trim()).filter(Boolean);
                
                // Patterns that indicate actual restrictions
                const restrictionPatterns = [
                    /^new with tags only$/i,
                    /^boutique only$/i,
                    /^handmade only$/i,
                    /^beauty only$/i,
                    /^electronics only$/i,
                    /^no replicas$/i,
                    /^no used items$/i,
                    /^no\\s+\\w+$/i,  // "No X" patterns
                    /\\bonly\\s*$/i,  // Lines ending with "only"
                    /^must\\s+/i,     // Lines starting with "must"
                    /^cannot\\s+/i,   // Lines starting with "cannot"
                    /^do not\\s+/i,   // Lines starting with "do not"
                ];
                
                // Patterns to explicitly ignore (informational text)
                const ignorePatterns = [
                    /posh parties are/i,
                    /happy poshing/i,
                    /listings must follow posh party guidelines/i,
                    /cover image/i,
                    /photo credit/i,
                    /image credit/i,
                    /hosted by/i,
                    /party host/i,
                    /posh party$/i,  // Just the party name
                    /^theme:/i,
                    /^brands:/i,
                    /^categories:/i,
                    /^departments:/i,
                    /^sizes:/i,
                    /^allowed$/i,
                    /^all$/i,
                    /^men$/i,
                    /^women$/i,
                    /^kids$/i,
                    /ends in/i,
                    /happening now/i,
                    /view party/i,
                    /share/i,
                    /follow/i,
                ];
                
                for (const line of lines) {
                    // Skip if too short or too long
                    if (line.length < 10 || line.length > 150) continue;
                    
                    // Skip known field labels
                    if (line.includes('Theme') || line.includes('Brands Allowed') ||
                        line.includes('Categories Allowed') || line.includes('Departments Allowed') ||
                        line.includes('Sizes Allowed')) continue;
                    
                    // Skip if matches ignore patterns
                    if (ignorePatterns.some(pattern => pattern.test(line))) continue;
                    
                    // Only include if it matches restriction patterns
                    if (restrictionPatterns.some(pattern => pattern.test(line))) {
                        otherRules.push(line);
                    }
                }
                
                return {
                    found: true,
                    container_source: containerSource,
                    container_tag: container.tagName,
                    container_class: container.className || '',
                    text_sample: fullText.substring(0, 300),
                    theme: theme,
                    // FIXED: Return exactly what was parsed, no defaults
                    brands_allowed: brands,
                    categories_allowed: categories,
                    departments_allowed: departments,
                    sizes_allowed: sizes,
                    other_rules: otherRules.slice(0, 5),  // Limit to 5
                };
            }
        """)
        
        if not result or not result.get("found"):
            print("  [DEBUG] Guideline extraction failed")
            if result and result.get("debug"):
                print(f"    Debug info: {result['debug']}")
            return None
        
        print(f"  [DEBUG] Guidelines extracted from: {result.get('container_source')}")
        print(f"    Container: {result.get('container_tag')} class={result.get('container_class', '')[:50]}")
        print(f"    Theme: {result.get('theme')}")
        print(f"    Brands: {result.get('brands_allowed')}")
        print(f"    Categories: {result.get('categories_allowed')}")
        
        return result
    
    def _determine_parse_confidence(self, guidelines_data: dict[str, Any]) -> GuidelineParseConfidence:
        """
        Determine parse confidence based on extracted guideline data.
        
        Rules:
        - HIGH: Theme present, brands/categories present (even if "All")
        - MEDIUM: Theme present, but brands or categories missing
        - LOW: Theme missing or ambiguous data
        - FAILED: No meaningful data extracted
        
        Args:
            guidelines_data: Extracted guideline data
            
        Returns:
            GuidelineParseConfidence level
        """
        theme = guidelines_data.get("theme", "")
        brands = guidelines_data.get("brands_allowed", [])
        categories = guidelines_data.get("categories_allowed", [])
        
        # FAILED: No meaningful data
        if not theme and len(brands) == 0 and len(categories) == 0:
            return GuidelineParseConfidence.FAILED
        
        # LOW: Theme missing
        if not theme:
            return GuidelineParseConfidence.LOW
        
        # MEDIUM: Theme present but brands or categories missing
        if len(brands) == 0 or len(categories) == 0:
            return GuidelineParseConfidence.MEDIUM
        
        # HIGH: Theme, brands, and categories all present
        return GuidelineParseConfidence.HIGH
    
    def refresh_cache(self, page: Page) -> list[PoshParty]:
        """
        Refresh party cache with latest data.
        
        Process:
        1. Load cached parties
        2. Discover fresh parties from page
        3. Merge fresh metadata with cached guidelines
        4. Load missing guidelines
        5. Save updated cache
        
        Args:
            page: Playwright page object (should be on parties page)
            
        Returns:
            List of refreshed PoshParty objects
        """
        print("[PartyManager] Refreshing party cache...")
        
        # Load cached parties
        cached_parties = self.cache.load()
        
        # Discover fresh parties
        fresh_parties = self.discover_parties(page)
        
        # Merge with cache
        merged_parties = self.cache.merge_fresh_parties(cached_parties, fresh_parties, page)
        
        # Load guidelines for parties that don't have them
        for party in merged_parties:
            if not party.guidelines:
                print(f"[PartyManager] Loading guidelines for: {party.name}")
                self.load_guidelines(page, party)
        
        # Save updated cache
        self.cache.save(merged_parties)
        
        print(f"[PartyManager] Cache refresh complete: {len(merged_parties)} parties")
        return merged_parties
    
    def get_cached_parties(self) -> list[PoshParty]:
        """
        Get parties from cache without refreshing.
        
        Returns:
            List of cached PoshParty objects (may be empty)
        """
        return self.cache.load()
