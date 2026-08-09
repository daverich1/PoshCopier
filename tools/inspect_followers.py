"""Read-only inspection of follower cards and controls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from login import DESTINATION_STATE_FILE, open_logged_in_browser


FOLLOWERS_URL = "https://poshmark.com/user/dveshop/followers"


def main() -> int:
    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            state_file=DESTINATION_STATE_FILE,
        )
        try:
            page.goto(FOLLOWERS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            evidence = page.locator("body").evaluate(
                r"""
                body => Array.from(body.querySelectorAll('button, a'))
                    .map(element => ({
                        tag: element.tagName,
                        text: (element.innerText || element.textContent || '').trim(),
                        href: element.getAttribute('href') || '',
                        ariaLabel: element.getAttribute('aria-label') || '',
                        dataTest: element.getAttribute('data-test') || '',
                        className: typeof element.className === 'string' ? element.className : '',
                    }))
                    .filter(item => /follow/i.test(item.text + ' ' + item.ariaLabel) || /\/closet\//i.test(item.href))
                    .slice(0, 80)
                """
            )
            print(f"URL: {page.url}")
            print(json.dumps(evidence, indent=2, ensure_ascii=False))
            follow_structure = page.locator("button.follow__btn", has_text="Follow").evaluate_all(
                r"""
                buttons => buttons
                    .filter(button => (button.innerText || '').trim() === 'Follow')
                    .slice(0, 1)
                    .map(button => button.parentElement ? button.parentElement.outerHTML : button.outerHTML)
                """
            )
            print("FOLLOW_ROW_STRUCTURE:")
            print(json.dumps(follow_structure, indent=2, ensure_ascii=False))
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
