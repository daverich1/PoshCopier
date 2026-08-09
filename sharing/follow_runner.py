"""Application runner for guarded Poshmark follow-backs."""

from __future__ import annotations

import re
from collections.abc import Callable

from playwright.sync_api import Page, sync_playwright

from login import DESTINATION_STATE_FILE, open_logged_in_browser
from sharing.share_config import ShareConfig
from sharing.share_engine import FollowCandidate, PoshmarkShareEngine
from sharing.share_progress import ShareProgress, ShareResult


USERNAME_PATTERN = re.compile(r"^/closet/([A-Za-z0-9_]+)$")


def collect_follow_back_candidates(
    page: Page,
    username: str,
    limit: int,
) -> list[FollowCandidate]:
    """Collect unique followers whose scoped control says exactly Follow."""
    page.goto(
        f"https://poshmark.com/user/{username}/followers",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_timeout(3000)

    candidates: list[FollowCandidate] = []
    seen: set[str] = set()
    buttons = page.locator("button.follow__btn").all()
    for button in buttons:
        if not button.is_visible() or (button.inner_text() or "").strip() != "Follow":
            continue
        row = button.locator(
            "xpath=ancestor::*[.//a[contains(@class, 'follow__action__container')]][1]"
        )
        if row.count() == 0:
            continue
        link = row.locator("a.follow__action__container").first
        href = link.get_attribute("href") or ""
        match = USERNAME_PATTERN.fullmatch(href)
        if not match:
            continue
        candidate_username = match.group(1).lower()
        if candidate_username == username.lower() or candidate_username in seen:
            continue
        seen.add(candidate_username)
        candidates.append(FollowCandidate(
            username=candidate_username,
            url=f"https://poshmark.com/closet/{candidate_username}",
            title=f"@{candidate_username}",
        ))
        if len(candidates) >= limit:
            break
    return candidates


def run_follow_backs(
    config: ShareConfig,
    username: str,
    *,
    perform_follow: bool = False,
    progress_callback: Callable[[ShareProgress], None] | None = None,
    engine_callback: Callable[[PoshmarkShareEngine], None] | None = None,
) -> ShareResult:
    """Validate or follow a finite batch of followers not already followed."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", username):
        raise ValueError("Invalid Poshmark username")
    if config.follow_back_limit is None:
        raise ValueError("Follow-backs require a finite limit")
    if perform_follow and not config.follow_backs_enabled:
        raise ValueError("Follow-backs are disabled")
    if not DESTINATION_STATE_FILE.exists():
        raise FileNotFoundError(
            f"{DESTINATION_STATE_FILE.name} was not found. Save the destination login first."
        )

    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            engine = PoshmarkShareEngine(page, config, progress_callback)
            if engine_callback is not None:
                engine_callback(engine)
            candidates = collect_follow_back_candidates(
                page,
                username,
                config.follow_back_limit,
            )
            if not candidates:
                return ShareResult(
                    success=True,
                    message="No followers currently need a follow-back",
                )
            if not perform_follow:
                names = ", ".join(f"@{item.username}" for item in candidates)
                return ShareResult(
                    success=True,
                    skipped=len(candidates),
                    message=f"Validated {len(candidates)} follow-back candidate(s): {names}",
                )
            return engine.follow_back_batch(candidates)
        finally:
            context.close()
            browser.close()
