from playwright.sync_api import sync_playwright

from data.database.database import (
    mark_listing_copied,
)
from login import (
    DESTINATION_STATE_FILE,
    open_logged_in_browser,
)
from uploader.category import fill_category
from uploader.colors import fill_colors
from uploader.condition import fill_condition
from uploader.duplicate_detector import (
    add_destination_url,
    collect_destination_listing_urls,
    find_existing_duplicate,
)
from uploader.form_fields import (
    close_price_modal,
    fill_brand,
    fill_description,
    fill_price,
    fill_title,
)
from uploader.image_uploader import upload_images
from uploader.listing_loader import (
    find_next_uncopied_listing_file,
    get_image_paths,
    load_listing,
)
from uploader.publisher import publish_listing
from uploader.size import fill_size


SELL_URL = "https://poshmark.com/create-listing"

DESTINATION_CLOSET_URL = (
    "https://poshmark.com/closet/dveshop"
)

# Keep this low while testing.
MAX_LISTINGS_PER_RUN = 50

# Faster timing profile for throughput testing.
# Set to False to restore the conservative waits.
FAST_MODE = True
CREATE_LISTING_WAIT_MS = 2000 if FAST_MODE else 5000
BETWEEN_LISTINGS_WAIT_MS = 750 if FAST_MODE else 2500

def print_listing_summary(
    listing_file,
    listing: dict,
    image_paths: list[str],
    current_number: int,
) -> None:
    print("\n" + "=" * 60)

    print(
        f"PROCESSING LISTING "
        f"{current_number}/"
        f"{MAX_LISTINGS_PER_RUN}"
    )

    print("=" * 60)
    print("Using:", listing_file)
    print(
        "Listing ID:",
        listing.get("listing_id"),
    )
    print(
        "Title:",
        listing.get("title"),
    )
    print(
        "Brand:",
        listing.get("brand"),
    )
    print(
        "Category:",
        listing.get("category"),
    )
    print(
        "Size:",
        listing.get("size"),
    )
    print(
        "Condition:",
        listing.get("condition"),
    )
    print(
        "Colors:",
        listing.get("colors"),
    )
    print(
        "Price:",
        listing.get("price"),
    )
    print(
        "Images:",
        len(image_paths),
    )
    print("=" * 60)


def validate_listing(
    listing: dict,
    image_paths: list[str],
) -> None:
    required_fields = (
        "listing_id",
        "title",
        "description",
        "price",
        "brand",
        "category",
        "size",
        "condition",
    )

    missing_fields = [
        field
        for field in required_fields
        if not listing.get(field)
    ]

    if missing_fields:
        raise RuntimeError(
            "The listing is missing required fields: "
            + ", ".join(missing_fields)
        )

    if not image_paths:
        raise RuntimeError(
            "The listing has no available images."
        )


def fill_listing_form(
    page,
    listing: dict,
    image_paths: list[str],
) -> None:
    page.goto(
        SELL_URL,
        wait_until="domcontentloaded",
    )

    page.wait_for_timeout(
        CREATE_LISTING_WAIT_MS
    )

    print(
        "Create Listing page opened."
    )

    upload_images(
        page,
        image_paths,
    )

    fill_title(
        page,
        listing["title"],
    )

    fill_description(
        page,
        listing["description"],
    )

    fill_price(
        page,
        listing["price"],
    )

    close_price_modal(
        page
    )

    fill_brand(
        page,
        listing["brand"],
    )

    fill_category(
        page,
        listing["category"],
    )

    category_value = str(
        listing.get("category", "")
    ).strip()

    # Poshmark Home and WomenBags categories do not expose a Size control.
    # Keep size handling strict everywhere else.
    if (
        category_value.casefold().startswith("home")
        or category_value.casefold().startswith("womenbags")
    ):
        print(
            "Size not applicable for Home or WomenBags category; "
            "skipping size selection."
        )
    else:
        fill_size(
            page,
            listing["size"],
        )

    fill_condition(
        page,
        listing["condition"],
    )

    fill_colors(
        page,
        listing.get(
            "colors",
            [],
        ),
    )

    print(
        "\nAll listing fields completed."
    )


def process_one_listing(
    page,
    current_number: int,
    destination_urls: list[str],
) -> str:
    listing_file = (
        find_next_uncopied_listing_file()
    )

    listing = load_listing(
        listing_file
    )

    image_paths = get_image_paths(
        listing
    )

    print_listing_summary(
        listing_file,
        listing,
        image_paths,
        current_number,
    )

    validate_listing(
        listing,
        image_paths,
    )

    print(
        "\nChecking dveshop for an "
        "existing matching listing..."
    )

    existing_url = find_existing_duplicate(
        page,
        listing,
        destination_urls,
    )

    if existing_url:
        mark_listing_copied(
            listing["listing_id"]
        )

        print(
            "The listing already exists "
            "in dveshop."
        )

        print(
            "Source listing marked as copied "
            "without creating a duplicate."
        )

        print(
            "Existing destination:",
            existing_url,
        )

        return "skipped_existing"

    fill_listing_form(
        page,
        listing,
        image_paths,
    )

    destination_url = publish_listing(
        page,
        listing,
        DESTINATION_CLOSET_URL,
    )

    mark_listing_copied(
        listing["listing_id"]
    )

    add_destination_url(
        destination_urls,
        destination_url,
    )

    print(
        "Source listing marked as copied."
    )

    print(
        "Published destination:",
        destination_url,
    )

    return "uploaded"


def main() -> None:
    successful_uploads = 0
    existing_duplicates = 0

    with sync_playwright() as playwright:
        browser, context, page = (
            open_logged_in_browser(
                playwright,
                DESTINATION_STATE_FILE,
            )
        )

        try:
            destination_urls = (
                collect_destination_listing_urls(
                    page,
                    DESTINATION_CLOSET_URL,
                )
            )

            for current_number in range(
                1,
                MAX_LISTINGS_PER_RUN + 1,
            ):
                try:
                    result = process_one_listing(
                        page,
                        current_number,
                        destination_urls,
                    )

                    if result == "uploaded":
                        successful_uploads += 1

                    elif result == "skipped_existing":
                        existing_duplicates += 1

                    print(
                        "\n" + "-" * 60
                    )

                    print(
                        "Uploaded this run:",
                        successful_uploads,
                    )

                    print(
                        "Skipped because already "
                        "in dveshop:",
                        existing_duplicates,
                    )

                    print(
                        "Moving to the next "
                        "uncopied listing..."
                    )

                    print(
                        "-" * 60
                    )

                    page.wait_for_timeout(
                        BETWEEN_LISTINGS_WAIT_MS
                    )

                except RuntimeError as error:
                    error_text = str(
                        error
                    )

                    if (
                        "No uncopied downloaded "
                        "listings were found"
                        in error_text
                    ):
                        print(
                            "\nNo uncopied downloaded "
                            "listings remain."
                        )

                        break

                    raise

            print(
                "\n" + "=" * 60
            )

            print(
                "BATCH COMPLETE"
            )

            print("=" * 60)

            print(
                "Successfully uploaded:",
                successful_uploads,
            )

            print(
                "Skipped — already in dveshop:",
                existing_duplicates,
            )

            print("=" * 60)

            input(
                "\nPress ENTER to close "
                "the browser..."
            )

        except Exception as error:
            print(
                "\n" + "=" * 60
            )

            print(
                "UPLOAD ERROR"
            )

            print("=" * 60)

            print(
                error
            )

            print("=" * 60)

            print(
                "Successfully uploaded before error:",
                successful_uploads,
            )

            print(
                "Existing duplicates skipped:",
                existing_duplicates,
            )

            input(
                "\nThe browser will remain open. "
                "Inspect the problem, then press "
                "ENTER to close..."
            )

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
