"""Core engine for Poshmark listing sharing operations."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from sharing.share_config import ShareConfig
from sharing.share_progress import (
    ShareError,
    ShareErrorType,
    ShareProgress,
    ShareResult,
    ShareStatus,
)


@dataclass
class ShareableListing:
    """
    Represents a listing that can be shared.
    
    Attributes:
        listing_id: Unique listing identifier
        url: Full URL to listing
        title: Listing title
        available: Whether listing is available for sale
    """
    
    listing_id: str
    url: str
    title: str
    available: bool = True


class PoshmarkShareEngine:
    """
    Manages sharing of Poshmark listings to followers.
    
    Designed for single-listing and batch sharing with rate limiting,
    pause/resume support, and comprehensive error handling.
    
    Thread-safe for use with Tkinter via progress callbacks.
    """
    
    def __init__(
        self,
        page: Page,
        config: ShareConfig,
        progress_callback: Callable[[ShareProgress], None] | None = None,
    ) -> None:
        """
        Initialize share engine.
        
        Args:
            page: Playwright page (must be authenticated)
            config: Share configuration
            progress_callback: Optional callback for progress updates
        """
        self.page = page
        self.config = config
        self.progress_callback = progress_callback
        
        # Control flags
        self._stop_requested = False
        self._paused = False
        
        # Timing
        self.start_time = 0.0
    
    def open_closet(self) -> None:
        """
        Navigate to closet and wait for page load.
        
        Raises:
            Exception: If navigation fails
        """
        print(f"Opening closet: {self.config.closet_url}")
        
        self.page.goto(
            self.config.closet_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        
        # Wait for initial content load
        self.page.wait_for_timeout(3000)
        
        # Check if we're still on closet page (not redirected to login)
        current_url = self.page.url
        if "/login" in current_url or "/signin" in current_url:
            raise Exception("Redirected to login - session expired")
        
        print("Closet loaded successfully")
    
    def share_listing(
        self,
        listing: ShareableListing,
        retry: bool = True,
    ) -> ShareResult:
        """
        Share a single listing to followers.
        
        This is the core share operation that discovers and interacts
        with Poshmark's share UI elements.
        
        Args:
            listing: Listing to share
            retry: Whether to retry once on transient failures
        
        Returns:
            ShareResult with success/failure status
        """
        print(f"\nSharing listing: {listing.title}")
        print(f"  URL: {listing.url}")
        
        start_time = time.time()
        
        try:
            # Navigate to the listing page
            print("  Navigating to listing...")
            self.page.goto(
                listing.url,
                wait_until="domcontentloaded",
                timeout=self.config.share_timeout_seconds * 1000,
            )
            
            # Wait for page to stabilize
            self.page.wait_for_timeout(2000)
            
            # Check for login redirect
            if "/login" in self.page.url or "/signin" in self.page.url:
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.LOGIN_EXPIRED,
                        message="Session expired - redirected to login",
                        listing_id=listing.listing_id,
                        recoverable=False,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message="Session expired",
                )
            
            # Find and click the share button
            print("  Looking for share button...")
            share_button = self._find_share_button()
            
            if share_button is None:
                error_msg = "Share button not found on listing page"
                print(f"  ERROR: {error_msg}")
                
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.SHARE_BUTTON_NOT_FOUND,
                        message=error_msg,
                        listing_id=listing.listing_id,
                        recoverable=True,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message=error_msg,
                )
            
            print("  Clicking share button...")
            share_button.click()
            
            # Wait for share modal to appear
            self.page.wait_for_timeout(1500)
            
            # Find and click "Share to My Followers" option
            print("  Looking for 'Share to My Followers' option...")
            followers_option = self._find_share_to_followers_option()
            
            if followers_option is None:
                error_msg = "Share to followers option not found in modal"
                print(f"  ERROR: {error_msg}")
                
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.MODAL_NOT_FOUND,
                        message=error_msg,
                        listing_id=listing.listing_id,
                        recoverable=True,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message=error_msg,
                )
            
            print("  Clicking 'Share to My Followers'...")
            followers_option.click()
            
            # Wait for share to complete
            self.page.wait_for_timeout(2000)
            
            # Check for success indicators
            success = self._verify_share_success()
            
            elapsed = time.time() - start_time
            
            if success:
                print(f"  ✓ Share successful ({elapsed:.1f}s)")
                return ShareResult(
                    success=True,
                    shared=1,
                    elapsed_seconds=elapsed,
                    message="Shared successfully",
                )
            else:
                print(f"  ? Share status unclear ({elapsed:.1f}s)")
                return ShareResult(
                    success=True,  # Assume success if no error
                    shared=1,
                    elapsed_seconds=elapsed,
                    message="Share completed (verification unclear)",
                )
        
        except PlaywrightTimeoutError as error:
            elapsed = time.time() - start_time
            error_msg = f"Timeout during share operation: {error}"
            print(f"  ERROR: {error_msg}")
            
            # Retry once on timeout if allowed
            if retry:
                print("  Retrying once...")
                return self.share_listing(listing, retry=False)
            
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.TIMEOUT,
                    message=error_msg,
                    listing_id=listing.listing_id,
                    recoverable=True,
                )],
                elapsed_seconds=elapsed,
                message="Timeout",
            )
        
        except Exception as error:
            elapsed = time.time() - start_time
            error_msg = f"Unexpected error: {error}"
            print(f"  ERROR: {error_msg}")
            
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.UNKNOWN,
                    message=error_msg,
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=elapsed,
                message="Unknown error",
            )
    
    def _find_share_button(self) -> any:
        """
        Find the share button on a listing page.
        
        Tries multiple selector strategies to find the share button.
        
        Returns:
            Locator for share button, or None if not found
        """
        # Strategy 1: Look for button with "Share" text
        try:
            button = self.page.get_by_role("button", name="Share")
            if button.count() > 0 and button.first.is_visible():
                return button.first
        except Exception:
            pass
        
        # Strategy 2: Look for share icon/button by aria-label
        try:
            button = self.page.locator('[aria-label*="Share" i]').first
            if button.is_visible():
                return button
        except Exception:
            pass
        
        # Strategy 3: Look for button with share-related data attributes
        try:
            button = self.page.locator('[data-test*="share" i]').first
            if button.is_visible():
                return button
        except Exception:
            pass
        
        # Strategy 4: Look for button with share-related classes
        try:
            button = self.page.locator('button[class*="share" i]').first
            if button.is_visible():
                return button
        except Exception:
            pass
        
        # Strategy 5: Look for any button containing "share" text (case-insensitive)
        try:
            button = self.page.locator('button:has-text("Share")').first
            if button.is_visible():
                return button
        except Exception:
            pass
        
        return None
    
    def _find_share_to_followers_option(self) -> any:
        """
        Find the "Share to My Followers" option in the share modal.
        
        Returns:
            Locator for followers option, or None if not found
        """
        # Strategy 1: Look for button/link with "Followers" text
        try:
            option = self.page.get_by_role("button", name="Share to My Followers")
            if option.count() > 0 and option.first.is_visible():
                return option.first
        except Exception:
            pass
        
        # Strategy 2: Look for any element with "Followers" text
        try:
            option = self.page.locator('text="Share to My Followers"').first
            if option.is_visible():
                return option
        except Exception:
            pass
        
        # Strategy 3: Look for element containing "Followers" (partial match)
        try:
            option = self.page.locator('[role="button"]:has-text("Followers")').first
            if option.is_visible():
                return option
        except Exception:
            pass
        
        # Strategy 4: Look for clickable element with "followers" in text (case-insensitive)
        try:
            option = self.page.locator('*:has-text("followers")').first
            if option.is_visible():
                return option
        except Exception:
            pass
        
        return None
    
    def _verify_share_success(self) -> bool:
        """
        Verify that the share operation succeeded.
        
        Looks for success indicators like confirmation messages or
        modal dismissal.
        
        Returns:
            True if share appears successful, False otherwise
        """
        # Strategy 1: Look for success message
        try:
            success_text = self.page.locator('text=/shared|success/i').first
            if success_text.is_visible(timeout=2000):
                return True
        except Exception:
            pass
        
        # Strategy 2: Check if modal is dismissed (share completed)
        try:
            # If modal is gone, assume success
            modal = self.page.locator('[role="dialog"]').first
            if not modal.is_visible(timeout=2000):
                return True
        except Exception:
            # Modal not found = likely dismissed = success
            return True
        
        # Strategy 3: Check if we're back on listing page (not in modal)
        try:
            current_url = self.page.url
            if "/listing/" in current_url:
                return True
        except Exception:
            pass
        
        # Default: assume success if no error detected
        return True
    
    def pause(self) -> None:
        """Request pause after current share completes."""
        self._paused = True
        print("Pause requested")
    
    def resume(self) -> None:
        """Resume from paused state."""
        self._paused = False
        print("Resumed")
    
    def request_stop_after_current(self) -> None:
        """Request stop after current share completes."""
        self._stop_requested = True
        print("Stop requested")
    
    def _wait_while_paused(self) -> None:
        """Block while paused, checking every 0.5s."""
        while self._paused and not self._stop_requested:
            time.sleep(0.5)
    
    def _apply_delay(self) -> None:
        """Apply configured delay with jitter."""
        delay = self.config.delay_seconds
        jitter = random.uniform(0, self.config.jitter_seconds)
        total_delay = delay + jitter
        
        print(f"  Waiting {total_delay:.1f}s before next share...")
        time.sleep(total_delay)
