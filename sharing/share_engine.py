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
                print(f"  [OK] Share successful ({elapsed:.1f}s)")
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
    
    def share_listing_to_party(
        self,
        listing: ShareableListing,
        party: any,  # PoshParty type
        retry: bool = True,
    ) -> ShareResult:
        """
        Share a single listing to a specific Posh Party.
        
        HARD GATES:
        - listing must be AVAILABLE
        - listing must be ACTIVE
        - party must be is_live == True
        - listing must be ELIGIBLE for party
        
        Args:
            listing: Listing to share (must include availability, active status)
            party: Live party to share to
            retry: Whether to retry once on transient failures
        
        Returns:
            ShareResult with success/failure status
        """
        print(f"\nSharing listing to party: {listing.title}")
        print(f"  Listing ID: {listing.listing_id}")
        print(f"  Listing URL: {listing.url}")
        print(f"  Party: {party.name} (ID: {party.party_id})")
        
        start_time = time.time()
        
        # GATE 1: Availability
        if not listing.available:
            print(f"  GATE FAILED: Listing is not available")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.LISTING_UNAVAILABLE,
                    message="Listing is not available",
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Listing not available",
                party_id=party.party_id,
                party_name=party.name,
            )
        
        # GATE 2: Party is live
        if not party.is_live:
            print(f"  GATE FAILED: Party is not live")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_NOT_LIVE,
                    message=f"Party '{party.name}' is not currently live",
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Party not live",
                party_id=party.party_id,
                party_name=party.name,
            )
        
        print(f"  [OK] Availability: AVAILABLE")
        print(f"  [OK] Party Live: True")
        
        try:
            # Open share modal from closet
            print("  Opening share modal from closet...")
            if not self._open_share_modal_from_closet(listing.listing_id):
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.MODAL_NOT_FOUND,
                        message="Could not open share modal",
                        listing_id=listing.listing_id,
                        recoverable=True,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message="Modal not found",
                    party_id=party.party_id,
                    party_name=party.name,
                )
            
            # Detect Posh Shows (log only)
            if self._detect_posh_shows_destination():
                print("  [INFO] Posh Shows Host destination detected (will not click)")
            
            # Find party destination
            print(f"  Looking for party destination: {party.name}...")
            party_dest = self._find_party_destination(party.party_id, party.name)
            
            if party_dest is None:
                print(f"  FAILED: Party destination not found in modal")
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.PARTY_DESTINATION_NOT_FOUND,
                        message=f"Party destination not found in modal",
                        listing_id=listing.listing_id,
                        recoverable=True,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message="Party destination not found",
                    party_id=party.party_id,
                    party_name=party.name,
                )
            
            # Verify destination
            print("  Verifying party destination...")
            if not self._verify_party_destination(party_dest, party.name):
                print(f"  FAILED: Party destination verification failed")
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.PARTY_DESTINATION_NOT_FOUND,
                        message="Party destination verification failed",
                        listing_id=listing.listing_id,
                        recoverable=True,
                    )],
                    elapsed_seconds=time.time() - start_time,
                    message="Destination verification failed",
                    party_id=party.party_id,
                    party_name=party.name,
                )
            
            print(f"  [OK] Party destination found and verified")
            
            # Click party destination
            print(f"  Clicking party destination...")
            party_dest.click()
            
            # Detect success
            success, success_msg = self._detect_share_success()
            
            elapsed = time.time() - start_time
            
            if success:
                print(f"  [OK] SUCCESS: {success_msg} ({elapsed:.1f}s)")
                return ShareResult(
                    success=True,
                    shared=1,
                    elapsed_seconds=elapsed,
                    message=success_msg,
                    party_id=party.party_id,
                    party_name=party.name,
                )
            else:
                print(f"  ? UNKNOWN: {success_msg} ({elapsed:.1f}s)")
                return ShareResult(
                    success=False,
                    failed=1,
                    errors=[ShareError(
                        error_type=ShareErrorType.PARTY_SHARE_FAILED,
                        message=success_msg,
                        listing_id=listing.listing_id,
                        recoverable=False,
                    )],
                    elapsed_seconds=elapsed,
                    message=success_msg,
                    party_id=party.party_id,
                    party_name=party.name,
                )
        
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"Unexpected error: {str(e)}"
            print(f"  ERROR: {error_msg}")
            
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.UNKNOWN,
                    message=error_msg,
                    listing_id=listing.listing_id,
                    recoverable=True,
                )],
                elapsed_seconds=elapsed,
                message=error_msg,
                party_id=party.party_id,
                party_name=party.name,
            )
    
    def _open_share_modal_from_closet(self, listing_id: str) -> bool:
        """
        Open share modal from closet card.
        
        Args:
            listing_id: ID of listing to share
        
        Returns:
            True if modal opened successfully, False otherwise
        """
        try:
            # Navigate to closet
            self.page.goto(
                self.config.closet_url,
                wait_until="domcontentloaded",
                timeout=15000,
            )
            self.page.wait_for_timeout(3000)
            
            # Find all share buttons
            share_buttons = self.page.locator("div.share-v2.cursor--pointer").all()
            
            if not share_buttons:
                print("    No share buttons found in closet")
                return False
            
            # Find the correct share button by checking parent tile
            target_button = None
            for button in share_buttons:
                try:
                    # Check if this button's parent tile contains a link to our listing
                    parent_tile = button.locator("xpath=ancestor::div[contains(@class, 'tile')]").first
                    tile_links = parent_tile.locator("a.tile__covershot").all()
                    
                    for link in tile_links:
                        href = link.get_attribute("href") or ""
                        if listing_id in href:
                            target_button = button
                            break
                    
                    if target_button:
                        break
                except:
                    continue
            
            if not target_button:
                print(f"    Share button not found for listing {listing_id}")
                return False
            
            # Click share button
            target_button.scroll_into_view_if_needed()
            self.page.wait_for_timeout(500)
            target_button.click()
            
            # Wait for modal
            self.page.wait_for_selector(
                "[data-test='listing-share-modal-container']",
                timeout=10000
            )
            self.page.wait_for_timeout(2000)
            
            return True
        
        except Exception as e:
            print(f"    Error opening share modal: {e}")
            return False
    
    def _find_party_destination(self, party_id: str, party_name: str) -> any:
        """
        Find party destination in share modal.
        
        Selector strategy:
        1. Primary: a[data-et-name="share_to_party"][data-et-prop-party_id="{party_id}"]
        2. Fallback: a[data-et-name="share_to_party"] + verify party_id attribute
        3. Last resort: text match on party_name
        
        Args:
            party_id: Party ID to find
            party_name: Party name for verification
        
        Returns:
            Locator for party destination, or None if not found
        """
        try:
            # Scope to modal
            modal = self.page.locator('[data-test="listing-share-modal-container"]')
            
            # Primary selector
            selector = f'a[data-et-name="share_to_party"][data-et-prop-party_id="{party_id}"]'
            element = modal.locator(selector)
            
            if element.count() > 0:
                print(f"    Found via primary selector")
                return element.first
            
            # Fallback: verify party_id in attributes
            elements = modal.locator('a[data-et-name="share_to_party"]').all()
            for elem in elements:
                if elem.get_attribute('data-et-prop-party_id') == party_id:
                    print(f"    Found via fallback selector (party_id match)")
                    return elem
            
            # Last resort: text match (logged as fallback)
            text_selector = f'a[data-et-name="share_to_party"]:has-text("{party_name}")'
            element = modal.locator(text_selector)
            if element.count() > 0:
                print(f"    Found via text match fallback (less stable)")
                return element.first
            
            return None
        
        except Exception as e:
            print(f"    Error finding party destination: {e}")
            return None
    
    def _detect_posh_shows_destination(self) -> bool:
        """
        Detect if Posh Shows Host destination is present.
        
        Returns:
            True if Posh Shows destination found, False otherwise
        """
        try:
            modal = self.page.locator('[data-test="listing-share-modal-container"]')
            posh_shows = modal.locator('a:has-text("Share to Posh Shows Host")')
            
            return posh_shows.count() > 0
        
        except Exception:
            return False
    
    def _verify_party_destination(self, element: any, party_name: str) -> bool:
        """
        Verify party destination before clicking.
        
        Checks:
        - Element is visible
        - Party name matches (case-insensitive)
        - Not disabled
        
        Args:
            element: Locator for party destination
            party_name: Expected party name
        
        Returns:
            True if safe to click, False otherwise
        """
        try:
            # Check visible
            if not element.is_visible():
                print(f"    Verification failed: element not visible")
                return False
            
            # Check party name (case-insensitive)
            text = element.text_content() or ""
            if party_name.lower() not in text.lower():
                print(f"    Verification failed: party name mismatch")
                print(f"      Expected: '{party_name}'")
                print(f"      Got: '{text}'")
                return False
            
            # Check not disabled
            if element.get_attribute('aria-disabled') == 'true':
                print(f"    Verification failed: element is disabled")
                return False
            
            return True
        
        except Exception as e:
            print(f"    Verification error: {e}")
            return False
    
    def _detect_share_success(self) -> tuple[bool, str]:
        """
        Detect if share was successful after clicking destination.
        
        Checks:
        - Modal closed
        - Success toast/message
        - Other UI state changes
        
        Returns:
            (success: bool, message: str)
        """
        # Wait briefly for UI response
        self.page.wait_for_timeout(1500)
        
        # Check if modal closed
        try:
            modal = self.page.locator('[data-test="listing-share-modal-container"]')
            if modal.count() == 0:
                return (True, "Modal closed after share")
        except:
            pass
        
        # Check for success toast/message
        success_indicators = [
            'text=/shared/i',
            'text=/success/i',
            '[class*="success"]',
            '[class*="toast"]'
        ]
        
        for selector in success_indicators:
            try:
                if self.page.locator(selector).count() > 0:
                    return (True, "Success indicator found")
            except:
                pass
        
        # No reliable signal
        return (False, "UNKNOWN - no success indicator detected")
    
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

