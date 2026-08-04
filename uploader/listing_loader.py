import json
from pathlib import Path

from data.database.database import (
    listing_already_copied,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"


def load_listing(
    listing_file: Path,
) -> dict:
    with listing_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def find_next_uncopied_listing_file() -> Path:
    listing_files = list(
        DOWNLOADS_DIR.glob("*/listing.json")
    )

    if not listing_files:
        raise FileNotFoundError(
            "No listing.json files were found "
            "inside the downloads folder."
        )

    listing_files.sort(
        key=lambda path: path.stat().st_mtime
    )

    for listing_file in listing_files:
        try:
            listing = load_listing(
                listing_file
            )

            listing_id = listing.get(
                "listing_id"
            )

            if not listing_id:
                print(
                    "Skipping file with no listing ID:",
                    listing_file,
                )
                continue

            if listing_already_copied(
                listing_id
            ):
                print(
                    "Skipping copied listing:",
                    listing_id,
                )
                continue

            return listing_file

        except Exception as error:
            print(
                "Could not inspect listing file:",
                listing_file,
            )
            print("Reason:", error)

    raise RuntimeError(
        "No uncopied downloaded listings were found."
    )


def get_image_paths(
    listing: dict,
) -> list[str]:
    image_paths = []

    for saved_path in listing.get(
        "downloaded_images",
        [],
    ):
        path = Path(saved_path)

        if path.exists():
            image_paths.append(
                str(path)
            )
        else:
            print(
                "Missing image file:",
                path,
            )

    return image_paths