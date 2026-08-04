from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_DIR = Path(__file__).resolve().parent

SOURCE_STATE_FILE = PROJECT_DIR / "source_state.json"
DESTINATION_STATE_FILE = PROJECT_DIR / "destination_state.json"


def save_login(state_file):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False
        )

        context = browser.new_context()
        page = context.new_page()

        page.goto(
            "https://poshmark.com/login",
            wait_until="domcontentloaded",
        )

        print("=" * 50)
        print("Log into the correct Poshmark account.")
        print("After you are completely logged in,")
        print("press ENTER in this terminal.")
        print("=" * 50)

        input()

        context.storage_state(
            path=str(state_file)
        )

        context.close()
        browser.close()

        print(f"Login saved to: {state_file.name}")


def save_source_login():
    save_login(SOURCE_STATE_FILE)


def save_destination_login():
    save_login(DESTINATION_STATE_FILE)


def open_logged_in_browser(
    playwright,
    state_file=DESTINATION_STATE_FILE,
):
    if not state_file.exists():
        raise FileNotFoundError(
            f"{state_file.name} was not found."
        )

    browser = playwright.chromium.launch(
        headless=False
    )

    context = browser.new_context(
        storage_state=str(state_file)
    )

    page = context.new_page()

    page.goto(
        "https://poshmark.com/feed",
        wait_until="domcontentloaded",
    )

    return browser, context, page


if __name__ == "__main__":
    print("Which account do you want to save?")
    print("1. Source store")
    print("2. Destination store — dveshop")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        save_source_login()
    elif choice == "2":
        save_destination_login()
    else:
        print("Invalid choice.")
