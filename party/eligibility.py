"""
Party eligibility checking and classification.

Determines if a listing is eligible for a specific party based on
party guidelines and listing attributes.

CRITICAL: Availability is checked FIRST. Only AVAILABLE listings
can be eligible for parties.
"""

from __future__ import annotations

from scraper.availability import AvailabilityStatus, normalize_text
from party.party_models import (
    PartyType,
    PartyEligibilityStatus,
    PartyGuidelines,
    PoshParty,
    PartyEligibilityResult,
    GuidelineParseConfidence,
)


def classify_party_type(guidelines: PartyGuidelines) -> PartyType:
    """
    Classify party type based on guidelines.
    
    Rules:
    - Brands All + Categories All => UNIVERSAL
    - Brands All + Categories restricted => CATEGORY_LIMITED
    - Brands restricted + Categories All => BRAND_LIMITED
    - Brands restricted + Categories restricted => MIXED
    - Ambiguous/missing rules => UNKNOWN
    
    Args:
        guidelines: Party guidelines to classify
        
    Returns:
        PartyType classification
    """
    if not guidelines:
        return PartyType.UNKNOWN
    
    # Normalize brand and category lists
    brands = [normalize_text(b) for b in guidelines.brands_allowed]
    categories = [normalize_text(c) for c in guidelines.categories_allowed]
    
    # FIXED: Empty means unknown, not unrestricted
    # If both are empty, return UNKNOWN
    if len(brands) == 0 and len(categories) == 0:
        return PartyType.UNKNOWN
    
    # Check if "all" is present (case-insensitive)
    brands_all = "all" in brands
    categories_all = "all" in categories
    
    # Classify based on restrictions
    if brands_all and categories_all:
        return PartyType.UNIVERSAL
    elif brands_all and not categories_all:
        return PartyType.CATEGORY_LIMITED
    elif not brands_all and categories_all:
        return PartyType.BRAND_LIMITED
    elif not brands_all and not categories_all:
        return PartyType.MIXED
    else:
        return PartyType.UNKNOWN


def is_listing_eligible_for_party(
    listing: dict,
    party: PoshParty,
) -> PartyEligibilityResult:
    """
    Check if a listing is eligible for a specific party.
    
    HARD AVAILABILITY RULE:
    Listing MUST be confidently AVAILABLE. If listing is sold, inactive,
    not for sale, unavailable, reserved, draft, or unknown availability,
    return INELIGIBLE immediately. Never continue to party matching.
    
    Then check party guidelines:
    - "All" brand = unrestricted
    - "All" category = unrestricted
    - Normalize text before comparing
    - Compare department/category/subcategory appropriately
    - Compare brand when restricted
    - Size only if guidelines explicitly restrict it
    
    If rules cannot be interpreted confidently, return UNKNOWN.
    
    Args:
        listing: Listing dict with keys: availability, brand, department,
                 category, subcategory, size
        party: PoshParty with guidelines
        
    Returns:
        PartyEligibilityResult with status and reason
    """
    # ========================================================================
    # STEP 1: AVAILABILITY GATE (CRITICAL - CHECK FIRST)
    # ========================================================================
    
    availability = listing.get("availability")
    
    # Only AVAILABLE listings can be eligible
    if availability != AvailabilityStatus.AVAILABLE:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.INELIGIBLE,
            reason=f"Listing is not available for sale (status: {availability})",
        )
    
    # ========================================================================
    # STEP 2: CHECK IF GUIDELINES ARE LOADED
    # ========================================================================
    
    if not party.guidelines:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason="Party guidelines have not been loaded",
        )
    
    guidelines = party.guidelines
    
    # CRITICAL: Do not allow LOW/FAILED confidence to return ELIGIBLE
    confidence = guidelines.parse_confidence
    if confidence in (GuidelineParseConfidence.LOW, GuidelineParseConfidence.FAILED):
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason=f"Party guidelines have {confidence.value} parse confidence; cannot determine eligibility",
        )
    
    # ========================================================================
    # STEP 3: CHECK PARTY TYPE
    # ========================================================================
    
    party_type = classify_party_type(guidelines)
    
    if party_type == PartyType.UNIVERSAL:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.ELIGIBLE,
            reason="Listing is available; universal party allows all items",
        )
    
    if party_type == PartyType.UNKNOWN:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason="Party type cannot be determined from guidelines",
        )
    
    # ========================================================================
    # STEP 4: BRAND CHECK
    # ========================================================================
    
    brands_allowed = [normalize_text(b) for b in guidelines.brands_allowed]
    brands_unrestricted = "all" in brands_allowed
    
    # FIXED: Empty means field absent, return UNKNOWN
    if not brands_unrestricted and len(brands_allowed) == 0:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason="Party brand restrictions could not be determined",
        )
    
    if not brands_unrestricted:
        listing_brand = listing.get("brand", "")
        
        if not listing_brand:
            return PartyEligibilityResult(
                status=PartyEligibilityStatus.UNKNOWN,
                reason="Party restricts brands but listing brand is unknown",
            )
        
        listing_brand_normalized = normalize_text(listing_brand)
        
        if listing_brand_normalized not in brands_allowed:
            return PartyEligibilityResult(
                status=PartyEligibilityStatus.INELIGIBLE,
                reason=f"Listing brand '{listing_brand}' is not in allowed brands: {', '.join(guidelines.brands_allowed)}",
            )
    
    # ========================================================================
    # STEP 5: CATEGORY/DEPARTMENT CHECK
    # ========================================================================
    
    categories_allowed = [normalize_text(c) for c in guidelines.categories_allowed]
    categories_unrestricted = "all" in categories_allowed
    
    # FIXED: Empty means field absent, return UNKNOWN
    if not categories_unrestricted and len(categories_allowed) == 0:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason="Party category restrictions could not be determined",
        )
    
    if not categories_unrestricted:
        # Check department first (Men, Women, Kids)
        listing_department = listing.get("department", "")
        listing_category = listing.get("category", "")
        listing_subcategory = listing.get("subcategory", "")
        
        if not listing_department and not listing_category:
            return PartyEligibilityResult(
                status=PartyEligibilityStatus.UNKNOWN,
                reason="Party restricts categories but listing category/department is unknown",
            )
        
        # Try to match department, category, or subcategory
        matched = False
        matched_field = None
        matched_value = None
        
        if listing_department:
            dept_normalized = normalize_text(listing_department)
            if dept_normalized in categories_allowed:
                matched = True
                matched_field = "department"
                matched_value = listing_department
        
        if not matched and listing_category:
            cat_normalized = normalize_text(listing_category)
            if cat_normalized in categories_allowed:
                matched = True
                matched_field = "category"
                matched_value = listing_category

        if not matched and listing_department and listing_category:
            combined_category = f"{listing_department} {listing_category}"
            combined_normalized = normalize_text(combined_category)
            if combined_normalized in categories_allowed:
                matched = True
                matched_field = "category"
                matched_value = combined_category
        
        if not matched and listing_subcategory:
            subcat_normalized = normalize_text(listing_subcategory)
            if subcat_normalized in categories_allowed:
                matched = True
                matched_field = "subcategory"
                matched_value = listing_subcategory
        
        if not matched:
            return PartyEligibilityResult(
                status=PartyEligibilityStatus.INELIGIBLE,
                reason=f"Listing category/department does not match allowed categories: {', '.join(guidelines.categories_allowed)}",
            )
    
    # ========================================================================
    # STEP 6: SIZE CHECK (if applicable)
    # ========================================================================
    
    if guidelines.sizes_allowed and len(guidelines.sizes_allowed) > 0:
        sizes_allowed = [normalize_text(s) for s in guidelines.sizes_allowed]
        sizes_unrestricted = "all" in sizes_allowed
        
        if not sizes_unrestricted:
            listing_size = listing.get("size", "")
            
            if not listing_size:
                return PartyEligibilityResult(
                    status=PartyEligibilityStatus.UNKNOWN,
                    reason="Party restricts sizes but listing size is unknown",
                )
            
            size_normalized = normalize_text(listing_size)
            
            if size_normalized not in sizes_allowed:
                return PartyEligibilityResult(
                    status=PartyEligibilityStatus.INELIGIBLE,
                    reason=f"Listing size '{listing_size}' is not in allowed sizes: {', '.join(guidelines.sizes_allowed)}",
                )
    
    # ========================================================================
    # STEP 7: OTHER RULES CHECK
    # ========================================================================
    
    if guidelines.other_rules and len(guidelines.other_rules) > 0:
        return PartyEligibilityResult(
            status=PartyEligibilityStatus.UNKNOWN,
            reason="Party contains additional rules that could not be interpreted confidently",
        )
    
    # ========================================================================
    # STEP 8: ELIGIBLE
    # ========================================================================
    
    # Build detailed reason
    reason_parts = ["Listing is available"]
    
    if brands_unrestricted:
        reason_parts.append("all brands allowed")
    else:
        reason_parts.append(f"brand '{listing.get('brand', '')}' is allowed")
    
    if categories_unrestricted:
        reason_parts.append("all categories allowed")
    else:
        if matched_field and matched_value:
            reason_parts.append(f"{matched_field} '{matched_value}' is allowed")
    
    reason = "; ".join(reason_parts) + "."
    
    return PartyEligibilityResult(
        status=PartyEligibilityStatus.ELIGIBLE,
        reason=reason,
    )
