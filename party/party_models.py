"""
Party data models for Poshmark party management.

Defines the core data structures for representing parties, guidelines,
and eligibility results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PartyType(str, Enum):
    """Classification of party based on eligibility rules."""
    
    UNIVERSAL = "universal"  # All brands, all categories
    CATEGORY_LIMITED = "category_limited"  # All brands, specific categories
    BRAND_LIMITED = "brand_limited"  # Specific brands, all categories
    MIXED = "mixed"  # Both brands and categories restricted
    UNKNOWN = "unknown"  # Cannot determine type confidently


class PartyEligibilityStatus(str, Enum):
    """Result of checking if a listing is eligible for a party."""
    
    ELIGIBLE = "eligible"  # Listing meets all party requirements
    INELIGIBLE = "ineligible"  # Listing does not meet requirements
    UNKNOWN = "unknown"  # Cannot determine eligibility confidently


class GuidelineParseConfidence(str, Enum):
    """Confidence level of guideline parsing."""
    
    HIGH = "high"  # Guidelines parsed successfully with high confidence
    MEDIUM = "medium"  # Guidelines parsed but with some ambiguity
    LOW = "low"  # Guidelines parsed but with low confidence
    FAILED = "failed"  # Guideline parsing failed


@dataclass
class PartyGuidelines:
    """
    Official party guidelines extracted from party detail page.
    
    Fields containing "All" are stored as ["All"].
    Empty/absent fields are stored as [].
    Ambiguous rules are preserved in other_rules.
    
    New fields:
    - extra_fields: Preserves unknown official guideline fields
    - parse_confidence: Confidence level of parsing
    - parsed_at: Timestamp when guidelines were parsed
    """
    
    theme: str
    brands_allowed: list[str]
    categories_allowed: list[str]
    departments_allowed: list[str]
    sizes_allowed: list[str]
    other_rules: list[str]
    extra_fields: dict[str, list[str]] = field(default_factory=dict)
    parse_confidence: GuidelineParseConfidence = GuidelineParseConfidence.HIGH
    parsed_at: datetime | None = None


@dataclass
class PoshParty:
    """
    Represents a Poshmark party with its metadata and guidelines.
    
    party_id: Unique identifier extracted from URL
    name: Display name of the party
    url: Full URL to the party page
    start_time_text: Original time text (e.g., "Today at 7:00 PM")
    start_at: Parsed datetime (None if unparseable)
    is_live: Whether the party is currently happening
    guidelines: Official party guidelines (None if not loaded)
    party_type: Classification based on guidelines
    """
    
    party_id: str
    name: str
    url: str
    start_time_text: str
    start_at: datetime | None
    is_live: bool
    guidelines: PartyGuidelines | None
    party_type: PartyType


@dataclass
class PartyEligibilityResult:
    """
    Result of checking listing eligibility for a party.
    
    status: Whether the listing is eligible
    reason: Human-readable explanation of the decision
    """
    
    status: PartyEligibilityStatus
    reason: str
