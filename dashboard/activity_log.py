from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ActivityLog(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
    ) -> None:
        super().__init__(
            parent,
            text="Live Output",
            padding=8,
        )

        self.rowconfigure(
            0,
            weight=1,
        )
        self.columnconfigure(
            0,
            weight=1,
        )

        self.text = tk.Text(
            self,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.text.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.text.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.text.configure(
            yscrollcommand=scrollbar.set,
        )

    def append(
        self,
        value: str,
    ) -> None:
        self.text.configure(
            state="normal",
        )
        self.text.insert(
            "end",
            value,
        )
        self.text.see(
            "end"
        )
        self.text.configure(
            state="disabled",
        )

    def clear(self) -> None:
        self.text.configure(
            state="normal",
        )
        self.text.delete(
            "1.0",
            "end",
        )
        self.text.configure(
            state="disabled",
        )
