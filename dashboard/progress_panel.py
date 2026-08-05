from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ProgressPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Progress",
            padding=12,
        )

        self.percent_var = tk.DoubleVar(
            value=0.0
        )
        self.progress_text_var = tk.StringVar(
            value="0 / 0"
        )
        self.uploaded_var = tk.StringVar(
            value="0"
        )
        self.existing_var = tk.StringVar(
            value="0"
        )
        self.failed_var = tk.StringVar(
            value="0"
        )
        self.eta_var = tk.StringVar(
            value="—"
        )

        self.columnconfigure(
            0,
            weight=1,
        )
        self.columnconfigure(
            1,
            weight=1,
        )
        self.columnconfigure(
            2,
            weight=1,
        )
        self.columnconfigure(
            3,
            weight=1,
        )

        ttk.Label(
            self,
            textvariable=self.progress_text_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
        )

        ttk.Progressbar(
            self,
            variable=self.percent_var,
            maximum=100,
            mode="determinate",
        ).grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(8, 12),
        )

        self._build_stat(
            column=0,
            label="Uploaded",
            variable=self.uploaded_var,
        )
        self._build_stat(
            column=1,
            label="Existing",
            variable=self.existing_var,
        )
        self._build_stat(
            column=2,
            label="Failed",
            variable=self.failed_var,
        )
        self._build_stat(
            column=3,
            label="ETA",
            variable=self.eta_var,
        )

    def _build_stat(
        self,
        *,
        column: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        frame = ttk.Frame(
            self
        )
        frame.grid(
            row=2,
            column=column,
            sticky="nsew",
            padx=6,
        )

        ttk.Label(
            frame,
            text=label,
            font=("Segoe UI", 9, "bold"),
        ).pack()

        ttk.Label(
            frame,
            textvariable=variable,
            font=("Segoe UI", 12),
        ).pack(
            pady=(3, 0),
        )

    def set_percent(
        self,
        value: float,
    ) -> None:
        value = max(
            0.0,
            min(
                float(value),
                100.0,
            ),
        )

        self.percent_var.set(
            value
        )

    def set_progress(
        self,
        value: str,
    ) -> None:
        self.progress_text_var.set(
            value or "0 / 0"
        )

    def set_uploaded(
        self,
        value: str,
    ) -> None:
        self.uploaded_var.set(
            value or "0"
        )

    def set_existing(
        self,
        value: str,
    ) -> None:
        self.existing_var.set(
            value or "0"
        )

    def set_failed(
        self,
        value: str,
    ) -> None:
        self.failed_var.set(
            value or "0"
        )

    def set_eta(
        self,
        value: str,
    ) -> None:
        self.eta_var.set(
            value or "—"
        )

    def reset(self) -> None:
        self.percent_var.set(
            0.0
        )
        self.progress_text_var.set(
            "0 / 0"
        )
        self.uploaded_var.set(
            "0"
        )
        self.existing_var.set(
            "0"
        )
        self.failed_var.set(
            "0"
        )
        self.eta_var.set(
            "—"
        )
