import re
import unicodedata

from playwright.sync_api import Locator, Page


# TEMPORARY TEST HOOK - REMOVE AFTER TASK-023D-P1 VALIDATION
FORCE_PUBLISH_VERIFICATION_FAILURE = False

# Faster timing profile for throughput testing.
# Safety checks, duplicate protection, and all verification attempts stay enabled.
FAST_MODE = True
NEXT_WAIT_MS = 1250 if FAST_MODE else 2500
POST_PUBLISH_WAIT_MS = 4000 if FAST_MODE else 8000
VERIFY_DELAYS_MS = (1000, 1000, 1500) if FAST_MODE else (2000, 2000, 3000)
SCROLL_WAIT_MS = 600 if FAST_MODE else 1000


class PublishUnverifiedException(Exception):
    """
    Raised when the final Publish button was clicked (or click was attempted)
    but the result could not be verified.
    
    This is a TERMINAL exception - the publish operation must NOT be retried
    automatically because the listing may already exist on Poshmark.
    """
    pass


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip().lower()


def find_visible(
    locator: Locator,
) -> Locator | None:
    for index in range(locator.count()):
        candidate = locator.nth(index)

        try:
            if candidate.is_visible():
                return candidate

        except Exception:
            continue

    return None


def click_next(page: Page) -> None:
    selectors = [
        'button:text-is("Next")',
        'button:has-text("Next")',
        '[role="button"]:text-is("Next")',
    ]

    for selector in selectors:
        button = find_visible(
            page.locator(selector)
        )

        if button is None:
            continue

        button.scroll_into_view_if_needed()
        button.click()

        page.wait_for_timeout(NEXT_WAIT_MS)

        print("Next clicked.")
        return

    raise RuntimeError(
        "Could not find the Next button."
    )


def find_publish_button(
    page: Page,
) -> Locator | None:
    button_names = [
        "List Item",
        "List This Item",
        "Publish",
        "List",
    ]

    for name in button_names:
        button = find_visible(
            page.get_by_role(
                "button",
                name=name,
                exact=True,
            )
        )

        if button is not None:
            return button

    selectors = [
        'button:has-text("List Item")',
        'button:has-text("List This Item")',
        'button:has-text("Publish")',
    ]

    for selector in selectors:
        button = find_visible(
            page.locator(selector)
        )

        if button is not None:
            return button

    return None



def confirm_oversized_item_warning(page: Page) -> bool:
    """
    Detect and confirm Poshmark's specific "Problem Detected" oversized-item
    warning after the normal publish click.

    Safety:
    - Requires oversized-item warning evidence.
    - Clicks only an exact "Publish Listing" button.
    - Never clicks Delete Listing.
    """
    warning_phrases = (
        "potential oversized item",
        "currently do not support items that surpass",
        "packages over 5 lbs",
        "maximum weight our labels support is 10 lbs",
    )

    # Give the modal time to render. Poshmark can display it asynchronously.
    for attempt in range(1, 9):
        page.wait_for_timeout(750)

        try:
            body_text = normalize_text(
                page.locator("body").inner_text()
            )
        except Exception:
            body_text = ""

        warning_detected = any(
            phrase in body_text
            for phrase in warning_phrases
        )

        # Prefer a visible dialog/modal container if one exists.
        dialog = find_visible(
            page.locator(
                '[role="dialog"], '
                '[data-test*="modal" i], '
                '[class*="modal" i]'
            )
        )

        if dialog is not None:
            try:
                dialog_text = normalize_text(
                    dialog.inner_text()
                )
            except Exception:
                dialog_text = ""

            if any(
                phrase in dialog_text
                for phrase in warning_phrases
            ):
                warning_detected = True

        if not warning_detected:
            continue

        print(
            "Potential oversized item warning detected."
        )

        # Search the modal first, then the page as a fallback.
        button = None

        if dialog is not None:
            try:
                button = find_visible(
                    dialog.get_by_role(
                        "button",
                        name="Publish Listing",
                        exact=True,
                    )
                )
            except Exception:
                button = None

            if button is None:
                try:
                    button = find_visible(
                        dialog.locator(
                            'button:has-text("Publish Listing")'
                        )
                    )
                except Exception:
                    button = None

        if button is None:
            button = find_visible(
                page.get_by_role(
                    "button",
                    name="Publish Listing",
                    exact=True,
                )
            )

        if button is None:
            button = find_visible(
                page.locator(
                    'button:has-text("Publish Listing")'
                )
            )

        if button is None:
            raise RuntimeError(
                "The oversized-item warning was detected, "
                "but its Publish Listing button could not be found."
            )

        print(
            "Confirming oversized-item warning with Publish Listing..."
        )

        button.scroll_into_view_if_needed()
        button.click()

        print(
            "Oversized-item warning confirmed."
        )

        # Poshmark then opens a second confirmation dialog titled
        # "Publish Listing" with Cancel / Publish buttons.
        page.wait_for_timeout(500)

        second_dialog = None

        for _ in range(8):
            page.wait_for_timeout(500)

            dialogs = page.locator(
                '[role="dialog"], '
                '[data-test*="modal" i], '
                '[class*="modal" i]'
            )

            for index in range(dialogs.count()):
                candidate = dialogs.nth(index)

                try:
                    if not candidate.is_visible():
                        continue

                    dialog_text = normalize_text(
                        candidate.inner_text()
                    )

                    if (
                        "publish listing" in dialog_text
                        and "cancel" in dialog_text
                        and "publish" in dialog_text
                    ):
                        second_dialog = candidate
                        break

                except Exception:
                    continue

            if second_dialog is not None:
                break

        if second_dialog is None:
            raise RuntimeError(
                "The oversized-item confirmation was clicked, "
                "but the second Publish Listing dialog did not appear."
            )

        second_publish_button = find_visible(
            second_dialog.get_by_role(
                "button",
                name="Publish",
                exact=True,
            )
        )

        if second_publish_button is None:
            second_publish_button = find_visible(
                second_dialog.locator(
                    'button:text-is("Publish")'
                )
            )

        if second_publish_button is None:
            raise RuntimeError(
                "The second Publish Listing dialog appeared, "
                "but its Publish button could not be found."
            )

        print(
            "Second Publish Listing confirmation detected. "
            "Clicking Publish..."
        )

        second_publish_button.scroll_into_view_if_needed()
        second_publish_button.click()

        print(
            "Second Publish confirmation clicked."
        )

        page.wait_for_timeout(1500)
        return True

    return False

def collect_listing_links(
    page: Page,
) -> list[str]:
    page.wait_for_timeout(4000)

    links = page.locator(
        'a[href*="/listing/"]'
    ).evaluate_all(
        """
        elements => [
            ...new Set(
                elements
                    .map(element => element.href)
                    .filter(Boolean)
            )
        ]
        """
    )

    return links


def load_fresh_listings_with_scroll(
    page: Page,
    target_count: int,
) -> list[str]:
    """
    Scroll to load approximately target_count newest listings.
    
    Stops early if:
    - Target count reached
    - No new listings load after 3 consecutive checks
    
    Args:
        page: Playwright page (already on closet page)
        target_count: Approximate number of listings to load (e.g., 96, 144, 192)
    
    Returns:
        List of listing URLs loaded
    """
    max_scroll_rounds = 20  # Safety limit
    stable_rounds = 0
    previous_count = 0
    
    for scroll_round in range(max_scroll_rounds):
        # Check current listing count
        current_links = page.locator(
            'a[href*="/listing/"]'
        ).evaluate_all(
            """
            elements => [
                ...new Set(
                    elements
                        .map(element => element.href)
                        .filter(Boolean)
                )
            ]
            """
        )
        
        current_count = len(current_links)
        
        # Stop if target reached
        if current_count >= target_count:
            break
        
        # Stop if no progress after 3 rounds
        if current_count == previous_count:
            stable_rounds += 1
            if stable_rounds >= 3:
                break
        else:
            stable_rounds = 0
        
        previous_count = current_count
        
        # Scroll down
        page.evaluate(
            """
            () => {
                window.scrollTo(
                    0,
                    document.body.scrollHeight
                );
            }
            """
        )
        
        page.wait_for_timeout(SCROLL_WAIT_MS)
    
    # Final collection after scrolling
    return collect_listing_links(page)


def find_published_listing(
    page: Page,
    listing: dict,
    destination_closet_url: str,
) -> str | None:
    """
    Verify the published listing by checking fresh closet data.
    
    Uses 3 verification-only attempts with propagation delays.
    Reuses find_existing_duplicate() for efficient candidate narrowing.
    
    Args:
        page: Playwright page (may be on any page after publish)
        listing: Full source listing dict with title, brand, price, size
        destination_closet_url: Explicit closet URL to reload
    
    Returns:
        Destination listing URL if verified, None otherwise
    """
    from uploader.duplicate_detector import find_existing_duplicate
    
    for attempt in range(1, 4):
        print(f"\nVerification attempt {attempt}/3")
        
        # Always navigate back to closet explicitly
        print(f"Loading destination closet: {destination_closet_url}")
        page.goto(
            destination_closet_url,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        
        # Wait for propagation (longer on later attempts).
        # Fast mode shortens waits but keeps all 3 verification attempts.
        delay = VERIFY_DELAYS_MS[attempt - 1]
        page.wait_for_timeout(delay)
        
        # Determine target count based on attempt
        if attempt == 1:
            target_count = 96
        elif attempt == 2:
            target_count = 144
        else:  # attempt 3
            target_count = 192
        
        print(f"Target fresh links: {target_count}")
        
        # Scroll to load target count, then collect
        fresh_links = load_fresh_listings_with_scroll(page, target_count)
        
        print(f"Loaded fresh links: {len(fresh_links)}")
        print(f"Checking {len(fresh_links)} fresh closet links...")
        
        # Reuse existing duplicate detection logic:
        # - Cheap slug prefiltering (top 8 candidates)
        # - Full page inspection with scoring
        # - Threshold >= 80
        destination_url = find_existing_duplicate(
            page,
            listing,
            fresh_links,
        )
        
        if destination_url:
            print("\nPublished listing verified:")
            print(destination_url)
            return destination_url
        
        print("Published listing not visible yet.")
        
        if attempt < 3:
            print("Waiting for Poshmark propagation...")
    
    return None


def publish_listing(
    page: Page,
    listing: dict,
    destination_closet_url: str,
) -> str:
    """
    Click Next, then click the final Publish button, then verify.
    
    Args:
        page: Playwright page
        listing: Full source listing dict (needs title, brand, price, size for verification)
        destination_closet_url: Explicit closet URL for verification retries
    
    Raises:
        PublishUnverifiedException: If publish was attempted but verification failed.
            This is TERMINAL - do not retry the full publish flow.
        RuntimeError: For pre-publish failures (button not found, etc.) - retryable.
    """
    click_next(page)

    publish_button = find_publish_button(page)

    if publish_button is None:
        raise RuntimeError(
            "Could not find the final publish button."
        )

    print("\nThe listing is ready for publishing.")
    print("Clicking the final publish button...")

    # ============================================================
    # COMMIT BOUNDARY: Everything after this point is protected
    # ============================================================
    publish_attempted = False

    try:
        # Mark BEFORE click - even if click() raises, we cannot safely
        # assume Poshmark didn't receive it
        publish_attempted = True

        publish_button.scroll_into_view_if_needed()
        publish_button.click()

        print("Final publish button clicked.")

        oversized_confirmed = confirm_oversized_item_warning(
            page
        )

        if oversized_confirmed:
            print(
                "Continuing publish verification after "
                "oversized-item confirmation."
            )

        # TEMPORARY TEST HOOK - REMOVE AFTER TASK-023D-P1 VALIDATION
        if FORCE_PUBLISH_VERIFICATION_FAILURE:
            raise PublishUnverifiedException(
                "TEST ONLY: Forced post-publish verification failure"
            )

        page.wait_for_timeout(POST_PUBLISH_WAIT_MS)

        current_url = page.url

        # A. DIRECT URL SUCCESS
        # Some publishes go directly to the new listing.
        if "/listing/" in current_url:
            print("Listing published successfully.")
            print("Destination URL:", current_url)

            return current_url

        # B. CLOSET REDIRECT - Perform verification-only retries
        if "/closet/" in current_url:
            print(
                "Redirected to the closet. "
                "Performing verification with retries..."
            )

            destination_url = find_published_listing(
                page,
                listing,
                destination_closet_url,
            )

            if destination_url:
                print("\nListing published successfully.")
                print(
                    "Destination URL:",
                    destination_url,
                )

                return destination_url

        # Verification failed after all attempts
        raise PublishUnverifiedException(
            f"The final Publish button was clicked, but the published listing "
            f"could not be verified after 3 attempts. Current URL: {current_url}. "
            f"DO NOT RETRY - the listing may already exist on Poshmark."
        )

    except PublishUnverifiedException:
        # Already the right exception type, re-raise as-is
        raise

    except Exception as error:
        # Any other exception after publish_attempted = True
        # must be converted to PublishUnverifiedException
        if publish_attempted:
            raise PublishUnverifiedException(
                f"Final Publish was attempted, but the result could not be "
                f"safely verified due to an error: {error}. "
                f"DO NOT RETRY - the listing may already exist on Poshmark."
            ) from error

        # Exception before publish attempt - safe to retry
        raise