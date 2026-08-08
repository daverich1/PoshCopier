"""Progress tracking for Poshmark sharing operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ShareStatus(str, Enum):
    """Status of share operation."""
    
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    SHARING = "SHARING"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    
    @property
    def display_label(self) -> str:
        """Get user-friendly display label."""
        labels = {
            ShareStatus.IDLE: "Idle",
            ShareStatus.COLLECTING: "Collecting Listings",
            ShareStatus.SHARING: "Sharing",
            ShareStatus.PAUSED: "Paused",
            ShareStatus.COMPLETE: "Complete",
            ShareStatus.FAILED: "Failed",
        }
        return labels.get(self, "Unknown")


class ShareErrorType(str, Enum):
    """Classification of share errors."""
    
    # Transient - retry may succeed
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    MODAL_NOT_FOUND = "MODAL_NOT_FOUND"
    
    # Listing-specific - skip and continue
    LISTING_DISAPPEARED = "LISTING_DISAPPEARED"
    LISTING_UNAVAILABLE = "LISTING_UNAVAILABLE"
    SHARE_BUTTON_NOT_FOUND = "SHARE_BUTTON_NOT_FOUND"
    
    # Session-level - abort run
    LOGIN_EXPIRED = "LOGIN_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    CHALLENGE = "CHALLENGE"
    
    # Party sharing errors
    PARTY_NOT_LIVE = "PARTY_NOT_LIVE"
    PARTY_NOT_ELIGIBLE = "PARTY_NOT_ELIGIBLE"
    PARTY_DESTINATION_NOT_FOUND = "PARTY_DESTINATION_NOT_FOUND"
    PARTY_SHARE_FAILED = "PARTY_SHARE_FAILED"
    
    # Unknown - log and skip
    UNKNOWN = "UNKNOWN"


@dataclass
class ShareError:
    """Details of a share error."""
    
    error_type: ShareErrorType
    message: str
    listing_id: str = ""
    recoverable: bool = False


@dataclass
class ShareProgress:
    """
    Structured progress data for share operations.
    
    Thread-safe for passing between worker and UI threads.
    """
    
    status: ShareStatus
    current: int = 0
    total: int = 0
    message: str = ""
    listing_id: str = ""
    listing_title: str = ""
    shared: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None


@dataclass
class ShareResult:
    """Result of a share operation."""
    
    success: bool
    shared: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[ShareError] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    message: str = ""
    
    # Party sharing metadata
    party_id: str | None = None
    party_name: str | None = None
    eligibility_status: str | None = None
    eligibility_reason: str | None = None
