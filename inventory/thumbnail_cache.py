from __future__ import annotations

import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk


class ThumbnailCache:
    def __init__(
        self,
        size: tuple[int, int] = (110, 110),
    ) -> None:
        self.size = size
        self._cache: dict[
            Path,
            ImageTk.PhotoImage,
        ] = {}

    def get(
        self,
        image_path: Path | None,
    ) -> ImageTk.PhotoImage | None:
        if image_path is None:
            return None

        image_path = image_path.resolve()

        cached = self._cache.get(
            image_path
        )

        if cached is not None:
            return cached

        try:
            image = Image.open(
                image_path
            )
            image.thumbnail(
                self.size
            )

            photo = ImageTk.PhotoImage(
                image
            )
        except (
            OSError,
            tk.TclError,
        ):
            return None

        self._cache[
            image_path
        ] = photo

        return photo

    def clear(self) -> None:
        self._cache.clear()