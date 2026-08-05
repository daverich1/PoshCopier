from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StatusPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Current Listing",
            padding=12,
        )

        self.title_var = tk.StringVar(
            value="No listing selected"
        )
        self.step_var = tk.StringVar(
            value="Ready"
        )
        self.price_var = tk.StringVar(
            value="—"
        )
        self.sizes_var = tk.StringVar(
            value="—"
        )
        self.mode_var = tk.StringVar(
            value="—"
        )

        self.columnconfigure(
            1,
            weight=1,
        )

        ttk.Label(
            self,
            text="Title:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=0,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=4,
        )

        ttk.Label(
            self,
            textvariable=self.title_var,
            wraplength=680,
            justify="left",
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=4,
        )

        ttk.Label(
            self,
            text="Current step:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )

        ttk.Label(
            self,
            textvariable=self.step_var,
        ).grid(
            row=1,
            column=1,
            sticky="w",
            pady=4,
        )

        ttk.Label(
            self,
            text="Price:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )

        ttk.Label(
            self,
            textvariable=self.price_var,
        ).grid(
            row=2,
            column=1,
            sticky="w",
            pady=4,
        )

        ttk.Label(
            self,
            text="Sizes:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=3,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=4,
        )

        ttk.Label(
            self,
            textvariable=self.sizes_var,
            wraplength=680,
            justify="left",
        ).grid(
            row=3,
            column=1,
            sticky="ew",
            pady=4,
        )

        ttk.Label(
            self,
            text="Mode:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=4,
        )

        ttk.Label(
            self,
            textvariable=self.mode_var,
        ).grid(
            row=4,
            column=1,
            sticky="w",
            pady=4,
        )

    def set_title(
        self,
        value: str,
    ) -> None:
        self.title_var.set(
            value or "No listing selected"
        )

    def set_step(
        self,
        value: str,
    ) -> None:
        self.step_var.set(
            value or "Ready"
        )

    def set_price(
        self,
        value: str,
    ) -> None:
        value = value.strip()

        if value and not value.startswith("$"):
            value = f"${value}"

        self.price_var.set(
            value or "—"
        )

    def set_sizes(
        self,
        value: str,
    ) -> None:
        self.sizes_var.set(
            value or "—"
        )

    def set_mode(
        self,
        value: str,
    ) -> None:
        self.mode_var.set(
            value or "—"
        )

    def reset(self) -> None:
        self.title_var.set(
            "No listing selected"
        )
        self.step_var.set(
            "Ready"
        )
        self.price_var.set("—")
        self.sizes_var.set("—")
        self.mode_var.set("—")
