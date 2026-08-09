import json
from pathlib import Path, PureWindowsPath

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
    image_paths: list[str] = []
    seen_paths: set[Path] = set()
    listing_id = str(listing.get("listing_id", "")).strip()
    listing_dir = DOWNLOADS_DIR / listing_id if listing_id else None

    # New format
    saved_images = listing.get("local_images")

    # Backward compatibility
    if not saved_images:
        saved_images = listing.get(
            "downloaded_images",
            [],
        )

    for saved_path in saved_images:
        path = Path(saved_path)

        resolved_path = path
        if not resolved_path.exists() and listing_dir is not None:
            filename = (
                PureWindowsPath(saved_path).name
                if "\\" in str(saved_path)
                else path.name
            )
            portable_path = listing_dir / filename
            if portable_path.exists():
                resolved_path = portable_path

        if resolved_path.exists():
            canonical = resolved_path.resolve()
            if canonical not in seen_paths:
                seen_paths.add(canonical)
                image_paths.append(str(resolved_path))
        else:
            print(
                "Missing image file:",
                path,
            )

    if not image_paths and listing_dir is not None and listing_dir.exists():
        for path in sorted(listing_dir.glob("image_*.*")):
            if path.is_file():
                image_paths.append(str(path))

    return image_paths
