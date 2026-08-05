from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def apply_styles(
    root: tk.Tk,
) -> None:
    style = ttk.Style(root)

    if "vista" in style.theme_names():
        style.theme_use("vista")

    style.configure(
        "Title.TLabel",
        font=("Segoe UI", 22, "bold"),
    )

    style.configure(
        "Subtitle.TLabel",
        font=("Segoe UI", 10),
    )

    style.configure(
        "SectionValue.TLabel",
        font=("Segoe UI", 10, "bold"),
    )