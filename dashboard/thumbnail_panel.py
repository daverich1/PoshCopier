from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk


PROJECT_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads"


class ThumbnailPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Listing Preview",
            padding=12,
        )

        self.image_label = ttk.Label(
            self,
            text="No image",
            anchor="center",
        )
        self.image_label.pack(
            fill="both",
            expand=True,
        )

        self.photo: ImageTk.PhotoImage | None = None

    def show_listing(
        self,
        listing_id: str,
    ) -> None:
        listing_id = listing_id.strip()

        if not listing_id:
            self.reset()
            return

        listing_dir = (
            DOWNLOADS_DIR
            / listing_id
        )

        image_path = self._find_first_image(
            listing_dir
        )

        if image_path is None:
            self.reset(
                text="Image not found"
            )
            return

        try:
            image = Image.open(
                image_path
            )

            image.thumbnail(
                (240, 240)
            )

            self.photo = ImageTk.PhotoImage(
                image
            )

            self.image_label.configure(
                image=self.photo,
                text="",
            )

        except Exception:
            self.reset(
                text="Could not load image"
            )

    def _find_first_image(
        self,
        listing_dir: Path,
    ) -> Path | None:
        if not listing_dir.exists():
            return None

        preferred = (
            listing_dir / "image_1.jpg"
        )

        if preferred.exists():
            return preferred

        candidates: list[Path] = []

        for pattern in (
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.webp",
        ):
            candidates.extend(
                listing_dir.glob(pattern)
            )

        candidates.sort(
            key=lambda path: path.name
        )

        return (
            candidates[0]
            if candidates
            else None
        )

    def reset(
        self,
        text: str = "No image",
    ) -> None:
        self.photo = None

        self.image_label.configure(
            image="",
            text=text,
        )