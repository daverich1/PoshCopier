"""
Party cache management for PoshCopier.

Implements persistent caching of party metadata and guidelines with:
- Separate refresh cadences for metadata vs guidelines
- Confidence-based guideline reuse
- Atomic file operations
- Graceful failure handling

Cache file: logs/party_cache.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from party.party_models import (
    PartyType,
    PartyGuidelines,
    PoshParty,
    GuidelineParseConfidence,
)

# Configuration constants
PARTY_LIST_REFRESH_SECONDS = 300  # 5 minutes - party metadata refresh
GUIDELINE_REFRESH_SECONDS = 86400  # 24 hours - guideline data refresh

CACHE_FILE = "logs/party_cache.json"
CACHE_VERSION = "1.0"


class PartyCacheManager:
    """
    Manages persistent caching of party data.
    
    Key features:
    - Keyed by party_id (canonical identity)
    - Separate freshness for metadata vs guidelines
    - Confidence-based guideline reuse
    - Atomic save operations
    - Graceful failure handling
    
    Usage:
        cache = PartyCacheManager()
        
        # Load cache
        cached_parties = cache.load()
        
        # Merge fresh metadata with cached guidelines
        merged = cache.merge_fresh_parties(cached_parties, fresh_parties, page)
        
        # Save updated cache
        cache.save(merged)
    """
    
    def __init__(self, cache_file: str = CACHE_FILE):
        """
        Initialize cache manager.
        
        Args:
            cache_file: Path to cache file (relative to project root)
        """
        self.cache_file = cache_file
        self.cache_dir = os.path.dirname(cache_file)
    
    def load(self) -> list[PoshParty]:
        """
        Load cached parties from disk.
        
        Handles:
        - Missing file: return empty list
        - Invalid JSON: warn and return empty list
        - Unknown schema version: warn and ignore cache
        - Corrupt individual party: skip only that party
        
        Returns:
            List of cached PoshParty objects (may be empty)
        """
        if not os.path.exists(self.cache_file):
            print(f"[PartyCacheManager] Cache file not found: {self.cache_file}")
            return []
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[PartyCacheManager] WARNING: Invalid JSON in cache file: {e}")
            return []
        except Exception as e:
            print(f"[PartyCacheManager] WARNING: Failed to read cache file: {e}")
            return []
        
        # Check schema version
        version = data.get("version")
        if version != CACHE_VERSION:
            print(f"[PartyCacheManager] WARNING: Unknown cache version '{version}', expected '{CACHE_VERSION}'")
            return []
        
        # Deserialize parties
        parties = []
        party_list = data.get("parties", [])
        
        for party_data in party_list:
            try:
                party = self._deserialize_party(party_data)
                parties.append(party)
            except Exception as e:
                print(f"[PartyCacheManager] WARNING: Skipping corrupt party: {e}")
                continue
        
        print(f"[PartyCacheManager] Loaded {len(parties)} parties from cache")
        return parties
    
    def save(self, parties: list[PoshParty]) -> bool:
        """
        Save parties to cache with atomic write.
        
        Process:
        1. Serialize parties to JSON
        2. Write to temporary file
        3. Replace original file
        4. Clean up temp file on failure
        
        Args:
            parties: List of PoshParty objects to cache
            
        Returns:
            True if save succeeded, False otherwise
        """
        # Ensure cache directory exists
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
        
        # Serialize parties
        party_list = []
        for party in parties:
            try:
                party_data = self._serialize_party(party)
                party_list.append(party_data)
            except Exception as e:
                print(f"[PartyCacheManager] WARNING: Failed to serialize party {party.party_id}: {e}")
                continue
        
        # Create cache data
        cache_data = {
            "version": CACHE_VERSION,
            "cached_at": datetime.now().isoformat(),
            "party_count": len(party_list),
            "parties": party_list,
        }
        
        # Atomic write
        temp_file = f"{self.cache_file}.tmp"
        
        try:
            # Write to temp file
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            os.rename(temp_file, self.cache_file)
            
            print(f"[PartyCacheManager] Saved {len(party_list)} parties to cache")
            return True
            
        except Exception as e:
            print(f"[PartyCacheManager] ERROR: Failed to save cache: {e}")
            
            # Clean up temp file
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            
            return False
    
    def merge_fresh_parties(
        self,
        cached_parties: list[PoshParty],
        fresh_parties: list[PoshParty],
        page: Any = None,
    ) -> list[PoshParty]:
        """
        Merge fresh party metadata with cached guidelines.
        
        Strategy:
        1. Index cached parties by party_id
        2. For each fresh party:
           - Always use fresh metadata (name, url, time, is_live)
           - Reuse cached guidelines if valid
           - Otherwise load guidelines (if page provided)
        
        Guideline validity rules:
        - HIGH confidence: reuse if within GUIDELINE_REFRESH_SECONDS
        - MEDIUM confidence: reuse but allow periodic revalidation
        - LOW confidence: retry parsing on refresh
        - FAILED confidence: retry parsing on next refresh
        
        Args:
            cached_parties: Previously cached parties
            fresh_parties: Newly discovered parties
            page: Playwright page for loading guidelines (optional)
            
        Returns:
            List of merged PoshParty objects
        """
        # Index cached parties by party_id
        cached_by_id: dict[str, PoshParty] = {
            party.party_id: party for party in cached_parties
        }
        
        merged_parties = []
        now = datetime.now()
        
        for fresh_party in fresh_parties:
            party_id = fresh_party.party_id
            cached_party = cached_by_id.get(party_id)
            
            # Always use fresh metadata
            merged_party = PoshParty(
                party_id=fresh_party.party_id,
                name=fresh_party.name,
                url=fresh_party.url,
                start_time_text=fresh_party.start_time_text,
                start_at=fresh_party.start_at,
                is_live=fresh_party.is_live,
                guidelines=None,
                party_type=PartyType.UNKNOWN,
            )
            
            # Check if we can reuse cached guidelines
            should_reuse_guidelines = False
            
            if cached_party and cached_party.guidelines:
                guidelines = cached_party.guidelines
                confidence = guidelines.parse_confidence
                parsed_at = guidelines.parsed_at
                
                # Check guideline validity based on confidence
                if confidence == GuidelineParseConfidence.HIGH:
                    # Reuse if within refresh window
                    if parsed_at and (now - parsed_at).total_seconds() < GUIDELINE_REFRESH_SECONDS:
                        should_reuse_guidelines = True
                
                elif confidence == GuidelineParseConfidence.MEDIUM:
                    # Reuse but allow periodic revalidation
                    if parsed_at and (now - parsed_at).total_seconds() < GUIDELINE_REFRESH_SECONDS:
                        should_reuse_guidelines = True
                
                elif confidence == GuidelineParseConfidence.LOW:
                    # Retry parsing on refresh
                    should_reuse_guidelines = False
                
                elif confidence == GuidelineParseConfidence.FAILED:
                    # Retry parsing on next refresh
                    should_reuse_guidelines = False
            
            # Reuse cached guidelines if valid
            if should_reuse_guidelines and cached_party:
                merged_party.guidelines = cached_party.guidelines
                merged_party.party_type = cached_party.party_type
                print(f"[PartyCacheManager] Reusing cached guidelines for: {merged_party.name}")
            
            merged_parties.append(merged_party)
        
        return merged_parties
    
    def is_guidelines_fresh(self, party: PoshParty) -> bool:
        """
        Check if party guidelines are fresh enough to reuse.
        
        Args:
            party: PoshParty to check
            
        Returns:
            True if guidelines are fresh, False otherwise
        """
        if not party.guidelines:
            return False
        
        guidelines = party.guidelines
        confidence = guidelines.parse_confidence
        parsed_at = guidelines.parsed_at
        
        if not parsed_at:
            return False
        
        now = datetime.now()
        age_seconds = (now - parsed_at).total_seconds()
        
        # Check based on confidence
        if confidence == GuidelineParseConfidence.HIGH:
            return age_seconds < GUIDELINE_REFRESH_SECONDS
        elif confidence == GuidelineParseConfidence.MEDIUM:
            return age_seconds < GUIDELINE_REFRESH_SECONDS
        elif confidence == GuidelineParseConfidence.LOW:
            return False  # Always retry
        elif confidence == GuidelineParseConfidence.FAILED:
            return False  # Always retry
        
        return False
    
    # ========================================================================
    # PRIVATE SERIALIZATION METHODS
    # ========================================================================
    
    def _serialize_party(self, party: PoshParty) -> dict[str, Any]:
        """
        Serialize PoshParty to JSON-compatible dict.
        
        Args:
            party: PoshParty to serialize
            
        Returns:
            JSON-compatible dict
        """
        data = {
            "party_id": party.party_id,
            "name": party.name,
            "url": party.url,
            "start_time_text": party.start_time_text,
            "start_at": party.start_at.isoformat() if party.start_at else None,
            "is_live": party.is_live,
            "party_type": party.party_type.value,
            "guidelines": None,
        }
        
        if party.guidelines:
            data["guidelines"] = self._serialize_guidelines(party.guidelines)
        
        return data
    
    def _serialize_guidelines(self, guidelines: PartyGuidelines) -> dict[str, Any]:
        """
        Serialize PartyGuidelines to JSON-compatible dict.
        
        Args:
            guidelines: PartyGuidelines to serialize
            
        Returns:
            JSON-compatible dict
        """
        return {
            "theme": guidelines.theme,
            "brands_allowed": guidelines.brands_allowed,
            "categories_allowed": guidelines.categories_allowed,
            "departments_allowed": guidelines.departments_allowed,
            "sizes_allowed": guidelines.sizes_allowed,
            "other_rules": guidelines.other_rules,
            "extra_fields": guidelines.extra_fields,
            "parse_confidence": guidelines.parse_confidence.value,
            "parsed_at": guidelines.parsed_at.isoformat() if guidelines.parsed_at else None,
        }
    
    def _deserialize_party(self, data: dict[str, Any]) -> PoshParty:
        """
        Deserialize PoshParty from JSON dict.
        
        Args:
            data: JSON dict
            
        Returns:
            PoshParty object
        """
        guidelines = None
        if data.get("guidelines"):
            guidelines = self._deserialize_guidelines(data["guidelines"])
        
        return PoshParty(
            party_id=data["party_id"],
            name=data["name"],
            url=data["url"],
            start_time_text=data["start_time_text"],
            start_at=datetime.fromisoformat(data["start_at"]) if data.get("start_at") else None,
            is_live=data["is_live"],
            guidelines=guidelines,
            party_type=PartyType(data["party_type"]),
        )
    
    def _deserialize_guidelines(self, data: dict[str, Any]) -> PartyGuidelines:
        """
        Deserialize PartyGuidelines from JSON dict.
        
        Args:
            data: JSON dict
            
        Returns:
            PartyGuidelines object
        """
        return PartyGuidelines(
            theme=data["theme"],
            brands_allowed=data["brands_allowed"],
            categories_allowed=data["categories_allowed"],
            departments_allowed=data["departments_allowed"],
            sizes_allowed=data["sizes_allowed"],
            other_rules=data["other_rules"],
            extra_fields=data.get("extra_fields", {}),
            parse_confidence=GuidelineParseConfidence(data.get("parse_confidence", "high")),
            parsed_at=datetime.fromisoformat(data["parsed_at"]) if data.get("parsed_at") else None,
        )
