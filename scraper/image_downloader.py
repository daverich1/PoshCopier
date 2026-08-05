from pathlib import Path
from urllib.request import Request, urlopen


from runtime_paths import DOWNLOADS_DIR

def download_listing_images(listing):
    listing_folder = (
        DOWNLOADS_DIR
        / listing["listing_id"]
    )

    listing_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    downloaded_images = []

    for image_number, image_url in enumerate(
        listing.get("image_urls", []),
        start=1,
    ):
        image_path = (
            listing_folder
            / f"image_{image_number}.jpg"
        )

        try:
            request = Request(
                image_url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                },
            )

            with urlopen(
                request,
                timeout=30,
            ) as response:
                image_data = response.read()

            image_path.write_bytes(image_data)

            downloaded_images.append(
                str(image_path)
            )

            print(
                f"Downloaded image {image_number}: "
                f"{image_path.name}"
            )

        except Exception as error:
            print(
                f"Could not download image "
                f"{image_number}: {error}"
            )

    return downloaded_images