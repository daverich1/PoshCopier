"""Configuration for Poshmark sharing operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShareConfig:
    """
    Configuration for share operations.
    
    Attributes:
        closet_url: URL of closet to share from
        delay_seconds: Base delay between shares (default: 5.0)
        jitter_seconds: Random jitter 0-N seconds (default: 2.0)
        max_shares: Maximum shares per run, None = unlimited (default: None)
        stop_on_failures: Stop after N consecutive failures (default: 5)
        share_timeout_seconds: Timeout for single share operation (default: 15.0)
        modal_timeout_seconds: Timeout for modal interactions (default: 10.0)
    """
    
    closet_url: str
    delay_seconds: float = 5.0
    jitter_seconds: float = 2.0
    max_shares: int | None = None
    stop_on_failures: int = 5
    share_timeout_seconds: float = 15.0
    modal_timeout_seconds: float = 10.0
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds must be non-negative")
        
        if self.max_shares is not None and self.max_shares < 1:
            raise ValueError("max_shares must be at least 1 or None")
        
        if self.stop_on_failures < 1:
            raise ValueError("stop_on_failures must be at least 1")
        
        if self.share_timeout_seconds <= 0:
            raise ValueError("share_timeout_seconds must be positive")
        
        if self.modal_timeout_seconds <= 0:
            raise ValueError("modal_timeout_seconds must be positive")
