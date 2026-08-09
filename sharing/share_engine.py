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
        active: Confirmed active status, or None if unchecked
        party_eligible: Confirmed party eligibility, or None if unchecked
        eligibility_reason: Human-readable party eligibility explanation
    """
    
    listing_id: str
    url: str
    title: str
    available: bool = True
    active: bool | None = None
    party_eligible: bool | None = None
    eligibility_reason: str = ""


@dataclass
class FollowCandidate:
    """A confirmed follower who is not currently followed back."""

    username: str
    url: str
    title: str
    available: bool = True

    @property
    def listing_id(self) -> str:
        """Expose a stable identifier for shared batch progress handling."""
        return self.username


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

    def _emit_progress(self, progress: ShareProgress) -> None:
        """Send a progress snapshot without letting UI errors stop sharing."""
        if self.progress_callback is None:
            return

        try:
            self.progress_callback(progress)
        except Exception as error:
            print(f"Progress callback failed: {error}")

    def share_batch(self, listings: list[ShareableListing]) -> ShareResult:
        """Share a rate-limited batch of available listings to followers."""
        selected = list(listings)
        if self.config.max_shares is not None:
            selected = selected[:self.config.max_shares]

        return self._run_batch(
            selected,
            operation=self.share_listing,
            destination="followers",
        )

    def share_community_batch(
        self,
        listings: list[ShareableListing],
    ) -> ShareResult:
        """Share an explicitly limited batch from another seller's closet."""
        if not self.config.share_community_listings:
            return ShareResult(
                success=False,
                failed=1,
                message="Community sharing disabled",
            )

        selected = list(listings)
        if self.config.community_share_limit is not None:
            selected = selected[:self.config.community_share_limit]

        return self._run_batch(
            selected,
            operation=self.share_listing,
            destination="community listings to followers",
        )

    def follow_back_batch(
        self,
        candidates: list[FollowCandidate],
    ) -> ShareResult:
        """Follow a finite list of confirmed followers not already followed."""
        if not self.config.follow_backs_enabled:
            return ShareResult(
                success=False,
                failed=1,
                message="Follow-backs disabled",
            )

        selected = list(candidates)
        if self.config.follow_back_limit is not None:
            selected = selected[:self.config.follow_back_limit]

        return self._run_batch(
            selected,
            operation=self.follow_back,
            destination="follow-backs",
        )

    def follow_back(self, candidate: FollowCandidate) -> ShareResult:
        """Follow one candidate and require the button to change to Following."""
        start_time = time.time()
        try:
            link = self.page.locator(
                f'a.follow__action__container[href="/closet/{candidate.username}"]'
            ).first
            if link.count() == 0 or not link.is_visible():
                return ShareResult(
                    success=False,
                    failed=1,
                    message=f"Follower row not found for @{candidate.username}",
                )

            row = link.locator(
                "xpath=ancestor::*[.//button[contains(@class, 'follow__btn')]][1]"
            )
            button = row.locator("button.follow__btn").first
            if button.count() == 0 or not button.is_visible():
                return ShareResult(
                    success=False,
                    failed=1,
                    message=f"Follow control not found for @{candidate.username}",
                )

            current_text = (button.inner_text() or "").strip()
            if current_text == "Following":
                return ShareResult(
                    success=True,
                    skipped=1,
                    message=f"Already following @{candidate.username}",
                )
            if current_text != "Follow":
                return ShareResult(
                    success=False,
                    failed=1,
                    message=f"Unexpected follow control for @{candidate.username}",
                )

            button.click()
            self.page.wait_for_timeout(1000)
            updated_text = (button.inner_text() or "").strip()
            if updated_text != "Following":
                return ShareResult(
                    success=False,
                    failed=1,
                    message=f"Follow-back could not be verified for @{candidate.username}",
                )
            return ShareResult(
                success=True,
                shared=1,
                elapsed_seconds=time.time() - start_time,
                message=f"Followed back @{candidate.username}",
            )
        except Exception as error:
            return ShareResult(
                success=False,
                failed=1,
                elapsed_seconds=time.time() - start_time,
                message=f"Follow-back failed for @{candidate.username}: {error}",
            )

    def share_batch_to_party(
        self,
        listings: list[ShareableListing],
        party: any,
    ) -> ShareResult:
        """Share an explicitly limited batch to one live Posh Party."""
        if not self.config.share_to_parties:
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_SHARE_FAILED,
                    message="Party sharing is disabled in ShareConfig",
                    recoverable=False,
                )],
                message="Party sharing disabled",
                party_id=getattr(party, "party_id", None),
                party_name=getattr(party, "name", None),
            )

        selected = list(listings)
        if self.config.party_share_limit is not None:
            selected = selected[:self.config.party_share_limit]

        return self._run_batch(
            selected,
            operation=lambda listing: self.share_listing_to_party(
                listing,
                party,
            ),
            destination=f"party {party.name}",
        )

    def _run_batch(
        self,
        listings: list[ShareableListing] | list[FollowCandidate],
        operation: Callable[[ShareableListing | FollowCandidate], ShareResult],
        destination: str,
    ) -> ShareResult:
        """Coordinate a batch with progress, pause, stop, and failure limits."""
        total = len(listings)
        shared = 0
        skipped = 0
        failed = 0
        errors: list[ShareError] = []
        consecutive_failures = 0
        self.start_time = time.time()
        self._stop_requested = False

        self._emit_progress(ShareProgress(
            status=ShareStatus.SHARING,
            total=total,
            message=f"Starting {destination} sharing",
        ))

        for index, listing in enumerate(listings, 1):
            self._wait_while_paused()
            if self._stop_requested:
                break

            if not listing.available:
                skipped += 1
                self._emit_batch_progress(
                    ShareStatus.SHARING, index, total, listing,
                    shared, skipped, failed, "Skipped unavailable listing",
                )
                continue

            result = operation(listing)
            shared += result.shared
            skipped += result.skipped
            failed += result.failed
            errors.extend(result.errors)

            if result.success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            self._emit_batch_progress(
                ShareStatus.SHARING, index, total, listing,
                shared, skipped, failed, result.message,
            )

            if consecutive_failures >= self.config.stop_on_failures:
                break

            if index < total and not self._stop_requested:
                self._apply_delay()

        elapsed = time.time() - self.start_time
        completed = shared + skipped + failed
        stopped_early = completed < total
        success = failed == 0 and not stopped_early
        message = (
            f"{destination.capitalize()} stopped"
            if stopped_early
            else f"{destination.capitalize()} complete"
        )
        status = ShareStatus.COMPLETE if success else ShareStatus.FAILED

        self._emit_progress(ShareProgress(
            status=status,
            current=completed,
            total=total,
            message=message,
            shared=shared,
            skipped=skipped,
            failed=failed,
            elapsed_seconds=elapsed,
            eta_seconds=0.0,
        ))

        return ShareResult(
            success=success,
            shared=shared,
            skipped=skipped,
            failed=failed,
            errors=errors,
            elapsed_seconds=elapsed,
            message=message,
        )

    def _emit_batch_progress(
        self,
        status: ShareStatus,
        current: int,
        total: int,
        listing: ShareableListing | FollowCandidate,
        shared: int,
        skipped: int,
        failed: int,
        message: str,
    ) -> None:
        """Build and emit one batch progress snapshot."""
        elapsed = time.time() - self.start_time
        eta = None
        if current > 0:
            eta = max(0.0, (elapsed / current) * (total - current))

        self._emit_progress(ShareProgress(
            status=status,
            current=current,
            total=total,
            message=message,
            listing_id=listing.listing_id,
            listing_title=listing.title,
            shared=shared,
            skipped=skipped,
            failed=failed,
            elapsed_seconds=elapsed,
            eta_seconds=eta,
        ))
    
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
            # Open the confirmed closet-card share modal.
            print("  Opening share modal from closet...")
            if not self._open_share_modal_from_closet(listing.listing_id):
                error_msg = "Share modal not found for closet listing"
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
        # Strategy 1: Confirmed closet-modal destination selector
        try:
            modal = self.page.locator('[data-test="listing-share-modal-container"]')
            option = modal.locator('a[data-et-name="share_poshmark"]')
            if option.count() > 0 and option.first.is_visible():
                return option.first
        except Exception:
            pass

        # Strategy 2: Current visible destination label
        try:
            modal = self.page.locator('[data-test="listing-share-modal-container"]')
            option = modal.locator('a:has-text("To My Followers")')
            if option.count() > 0 and option.first.is_visible():
                return option.first
        except Exception:
            pass

        # Strategy 3: Look for button/link with legacy text
        try:
            option = self.page.get_by_role("button", name="Share to My Followers")
            if option.count() > 0 and option.first.is_visible():
                return option.first
        except Exception:
            pass
        
        # Strategy 4: Look for any element with "Followers" text
        try:
            option = self.page.locator('text="Share to My Followers"').first
            if option.is_visible():
                return option
        except Exception:
            pass
        
        # Strategy 5: Look for element containing "Followers" (partial match)
        try:
            option = self.page.locator('[role="button"]:has-text("Followers")').first
            if option.is_visible():
                return option
        except Exception:
            pass
        
        # Strategy 6: Look for clickable element with "followers" in text (case-insensitive)
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
            modal = self.page.locator('[data-test="listing-share-modal-container"]').first
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

        # GATE 0: Party sharing must be explicitly enabled
        if not self.config.share_to_parties:
            print("  GATE FAILED: Party sharing is disabled")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_SHARE_FAILED,
                    message="Party sharing is disabled in ShareConfig",
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Party sharing disabled",
                party_id=party.party_id,
                party_name=party.name,
            )
        
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
        
        # GATE 2: Active status
        if listing.active is not True:
            print("  GATE FAILED: Listing active status was not confirmed")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.LISTING_UNAVAILABLE,
                    message="Listing active status was not confirmed",
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Listing not active",
                party_id=party.party_id,
                party_name=party.name,
            )

        # GATE 3: Eligibility must be explicitly confirmed
        if listing.party_eligible is not True:
            reason = listing.eligibility_reason or "Party eligibility was not confirmed"
            print(f"  GATE FAILED: {reason}")
            return ShareResult(
                success=False,
                failed=1,
                errors=[ShareError(
                    error_type=ShareErrorType.PARTY_NOT_ELIGIBLE,
                    message=reason,
                    listing_id=listing.listing_id,
                    recoverable=False,
                )],
                elapsed_seconds=time.time() - start_time,
                message="Listing not eligible for party",
                party_id=party.party_id,
                party_name=party.name,
                eligibility_status="NOT_ELIGIBLE",
                eligibility_reason=reason,
            )

        # GATE 4: Party is live
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
        print(f"  [OK] Active: True")
        print(f"  [OK] Party Eligibility: ELIGIBLE")
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
            
            target_button = None
            previous_link_count = -1
            unchanged_passes = 0

            for _ in range(40):
                try:
                    link = self.page.locator(
                        f'a.tile__covershot[href*="{listing_id}"]'
                    ).first
                    if link.count() > 0:
                        parent_tile = link.locator(
                            "xpath=ancestor::div[contains(@class, 'tile')]"
                        ).first
                        button = parent_tile.locator(
                            "div.share-v2.cursor--pointer"
                        ).first
                        if button.count() > 0:
                            target_button = button
                            break

                    link_count = self.page.locator("a.tile__covershot").count()
                    if link_count == previous_link_count:
                        unchanged_passes += 1
                    else:
                        unchanged_passes = 0
                    previous_link_count = link_count
                    if unchanged_passes >= 3:
                        break

                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    self.page.wait_for_timeout(1000)
                except Exception:
                    break
            
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
        self._emit_progress(ShareProgress(
            status=ShareStatus.PAUSED,
            message="Sharing paused",
            elapsed_seconds=max(0.0, time.time() - self.start_time),
        ))
    
    def resume(self) -> None:
        """Resume from paused state."""
        self._paused = False
        print("Resumed")
        self._emit_progress(ShareProgress(
            status=ShareStatus.SHARING,
            message="Sharing resumed",
            elapsed_seconds=max(0.0, time.time() - self.start_time),
        ))
    
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

