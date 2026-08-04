from playwright.sync_api import Page


def upload_images(
    page: Page,
    image_paths: list[str],
) -> None:
    if not image_paths:
        raise RuntimeError(
            "No downloaded image files were found."
        )

    file_input = page.locator(
        'input[type="file"]'
    ).first

    file_input.wait_for(
        state="attached",
        timeout=20000,
    )

    file_input.set_input_files(
        image_paths
    )

    print(
        f"Selected {len(image_paths)} images "
        f"for upload."
    )

    page.wait_for_timeout(15000)
