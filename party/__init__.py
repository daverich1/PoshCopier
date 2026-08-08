"""
Party Manager Package

Provides party discovery, guideline extraction, eligibility checking,
and caching for Poshmark parties.

This package does NOT integrate with sharing/share_engine.py yet.
Sharing integration will be added in a future task.
"""

from party.party_models import (
    PartyType,
    PartyEligibilityStatus,
    PartyGuidelines,
    PoshParty,
    PartyEligibilityResult,
    GuidelineParseConfidence,
)
from party.party_manager import PartyManager
from party.eligibility import classify_party_type, is_listing_eligible_for_party
from party.cache import PartyCacheManager

__all__ = [
    "PartyType",
    "PartyEligibilityStatus",
    "PartyGuidelines",
    "PoshParty",
    "PartyEligibilityResult",
    "GuidelineParseConfidence",
    "PartyManager",
    "classify_party_type",
    "is_listing_eligible_for_party",
    "PartyCacheManager",
]
