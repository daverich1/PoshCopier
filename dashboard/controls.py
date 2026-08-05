from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class ControlsPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_start: Callable[[], None],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_stop_after_current: Callable[[], None],
        on_stop: Callable[[], None],
        on_clear_log: Callable[[], None],
        on_open_logs: Callable[[], None],
    ) -> None:
        super().__init__(parent)

        self.start_button = ttk.Button(
            self,
            text="Start",
            command=on_start,
        )
        self.start_button.pack(side="left")

        self.pause_button = ttk.Button(
            self,
            text="Pause",
            command=on_pause,
            state="disabled",
        )
        self.pause_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.resume_button = ttk.Button(
            self,
            text="Resume",
            command=on_resume,
            state="disabled",
        )
        self.resume_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.stop_after_button = ttk.Button(
            self,
            text="Stop After Current",
            command=on_stop_after_current,
            state="disabled",
        )
        self.stop_after_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.stop_button = ttk.Button(
            self,
            text="Emergency Stop",
            command=on_stop,
            state="disabled",
        )
        self.stop_button.pack(
            side="left",
            padx=(8, 0),
        )

        ttk.Button(
            self,
            text="Clear Log",
            command=on_clear_log,
        ).pack(
            side="left",
            padx=(8, 0),
        )

        ttk.Button(
            self,
            text="Open Logs",
            command=on_open_logs,
        ).pack(
            side="left",
            padx=(8, 0),
        )

    def set_running(
        self,
        running: bool,
    ) -> None:
        self.start_button.configure(
            state="disabled" if running else "normal"
        )

        self.pause_button.configure(
            state="normal" if running else "disabled"
        )

        self.resume_button.configure(
            state="disabled"
        )

        self.stop_after_button.configure(
            state="normal" if running else "disabled"
        )

        self.stop_button.configure(
            state="normal" if running else "disabled"
        )

    def set_paused(
        self,
        paused: bool,
    ) -> None:
        self.pause_button.configure(
            state="disabled" if paused else "normal"
        )

        self.resume_button.configure(
            state="normal" if paused else "disabled"
        )