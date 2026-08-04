from playwright.sync_api import Page, sync_playwright

from login import (
    DESTINATION_STATE_FILE,
    open_logged_in_browser,
)


SELL_URL = "https://poshmark.com/create-listing"


def print_element_details(page: Page) -> None:
    print("\n" + "=" * 70)
    print("POSHMARK FORM INSPECTOR")
    print("=" * 70)
    print("Click the field you want to inspect in the browser.")
    print("Then return to this terminal and press ENTER.")
    print("=" * 70)

    input()

    details = page.evaluate(
        """
        () => {
            const active = document.activeElement;

            if (!active) {
                return {
                    error: "No active element was found."
                };
            }

            const labels = [];

            if (active.labels) {
                for (const label of active.labels) {
                    labels.push(label.innerText.trim());
                }
            }

            const parentText =
                active.parentElement
                    ? active.parentElement.innerText.trim()
                    : "";

            const grandparentText =
                active.parentElement &&
                active.parentElement.parentElement
                    ? active.parentElement.parentElement.innerText.trim()
                    : "";

            return {
                tag: active.tagName,
                type: active.getAttribute("type"),
                id: active.id,
                name: active.getAttribute("name"),
                placeholder: active.getAttribute("placeholder"),
                ariaLabel: active.getAttribute("aria-label"),
                role: active.getAttribute("role"),
                className: active.className,
                value: active.value,
                labels: labels,
                parentText: parentText,
                grandparentText: grandparentText,
                outerHTML: active.outerHTML
            };
        }
        """
    )

    print("\nACTIVE ELEMENT DETAILS")
    print("-" * 70)

    for key, value in details.items():
        print(f"{key}: {value}")

    print("-" * 70)


def print_visible_form_fields(page: Page) -> None:
    print("\nVISIBLE FORM FIELDS")
    print("=" * 70)

    fields = page.locator(
        """
        input:not([type="hidden"]),
        textarea,
        select,
        button,
        [contenteditable="true"],
        [role="combobox"]
        """
    )

    field_count = fields.count()

    print(f"Total fields found: {field_count}\n")

    for index in range(field_count):
        field = fields.nth(index)

        try:
            if not field.is_visible():
                continue

            information = field.evaluate(
                """
                element => ({
                    tag: element.tagName,
                    type: element.getAttribute("type"),
                    id: element.id,
                    name: element.getAttribute("name"),
                    placeholder:
                        element.getAttribute("placeholder"),
                    ariaLabel:
                        element.getAttribute("aria-label"),
                    role: element.getAttribute("role"),
                    text:
                        element.innerText
                        ? element.innerText.trim()
                        : "",
                    value:
                        "value" in element
                        ? element.value
                        : ""
                })
                """
            )

            print(f"FIELD {index + 1}")
            print(f"  Tag: {information['tag']}")
            print(f"  Type: {information['type']}")
            print(f"  ID: {information['id']}")
            print(f"  Name: {information['name']}")
            print(
                f"  Placeholder: "
                f"{information['placeholder']}"
            )
            print(
                f"  Aria label: "
                f"{information['ariaLabel']}"
            )
            print(f"  Role: {information['role']}")
            print(f"  Text: {information['text']}")
            print(f"  Value: {information['value']}")
            print("-" * 70)

        except Exception as error:
            print(
                f"Could not inspect field "
                f"{index + 1}: {error}"
            )


def main() -> None:
    with sync_playwright() as playwright:
        browser, context, page = open_logged_in_browser(
            playwright,
            DESTINATION_STATE_FILE,
        )

        try:
            page.goto(
                SELL_URL,
                wait_until="domcontentloaded",
            )

            page.wait_for_timeout(5000)

            print("Create-listing page opened.")

            while True:
                print("\nChoose an option:")
                print("1. Inspect the field you clicked")
                print("2. Print all visible form fields")
                print("3. Exit")

                choice = input(
                    "Enter 1, 2, or 3: "
                ).strip()

                if choice == "1":
                    print_element_details(page)

                elif choice == "2":
                    print_visible_form_fields(page)

                elif choice == "3":
                    break

                else:
                    print("Invalid choice.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()