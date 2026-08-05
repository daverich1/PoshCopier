from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from dashboard.activity_log import ActivityLog
from dashboard.controls import ControlsPanel
from dashboard.pipeline_io import (
    StatusEvent,
    parse_percent,
    parse_status_line,
)
from dashboard.progress_panel import ProgressPanel
from dashboard.status_panel import StatusPanel
from dashboard.styles import apply_styles


PROJECT_DIR = Path(__file__).resolve().parent.parent
PIPELINE_FILE = PROJECT_DIR / "run_pipeline.py"
LOGS_DIR = PROJECT_DIR / "logs"


class PoshCopierDashboard:
    def __init__(
        self,
        root: tk.Tk,
    ) -> None:
        self.root = root
        self.root.title("PoshCopier Dashboard")
        self.root.geometry("1050x900")
        self.root.minsize(900, 720)

        apply_styles(root)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None

        self.mode_var = tk.StringVar(
            value="dry_run"
        )
        self.count_var = tk.StringVar(
            value="5"
        )
        self.retries_var = tk.StringVar(
            value="3"
        )
        self.retry_delay_var = tk.StringVar(
            value="3"
        )
        self.command_input_var = tk.StringVar(
            value=""
        )

        self._build_interface()
        self._poll_output_queue()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close,
        )

    def _build_interface(self) -> None:
        main = ttk.Frame(
            self.root,
            padding=16,
        )
        main.pack(
            fill="both",
            expand=True,
        )

        ttk.Label(
            main,
            text="PoshCopier",
            style="Title.TLabel",
        ).pack(
            anchor="w",
        )

        ttk.Label(
            main,
            text=(
                "Source-to-destination listing pipeline"
            ),
            style="Subtitle.TLabel",
        ).pack(
            anchor="w",
            pady=(0, 14),
        )

        settings = ttk.LabelFrame(
            main,
            text="Run Settings",
            padding=12,
        )
        settings.pack(
            fill="x",
        )

        settings.columnconfigure(
            1,
            weight=1,
        )
        settings.columnconfigure(
            3,
            weight=1,
        )

        ttk.Label(
            settings,
            text="Mode:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )

        mode_frame = ttk.Frame(
            settings
        )
        mode_frame.grid(
            row=0,
            column=1,
            sticky="w",
            pady=4,
        )

        ttk.Radiobutton(
            mode_frame,
            text="Dry Run",
            variable=self.mode_var,
            value="dry_run",
        ).pack(
            side="left",
            padx=(0, 12),
        )

        ttk.Radiobutton(
            mode_frame,
            text="Live Publish",
            variable=self.mode_var,
            value="publish",
        ).pack(
            side="left",
        )

        ttk.Label(
            settings,
            text="Listings:",
        ).grid(
            row=0,
            column=2,
            sticky="e",
            padx=(16, 8),
            pady=4,
        )

        ttk.Entry(
            settings,
            textvariable=self.count_var,
            width=12,
        ).grid(
            row=0,
            column=3,
            sticky="w",
            pady=4,
        )

        ttk.Label(
            settings,
            text="Retries:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )

        ttk.Entry(
            settings,
            textvariable=self.retries_var,
            width=12,
        ).grid(
            row=1,
            column=1,
            sticky="w",
            pady=4,
        )

        ttk.Label(
            settings,
            text="Retry delay (seconds):",
        ).grid(
            row=1,
            column=2,
            sticky="e",
            padx=(16, 8),
            pady=4,
        )

        ttk.Entry(
            settings,
            textvariable=self.retry_delay_var,
            width=12,
        ).grid(
            row=1,
            column=3,
            sticky="w",
            pady=4,
        )

        self.controls = ControlsPanel(
            main,
            on_start=self.start_pipeline,
            on_stop=self.stop_pipeline,
            on_clear_log=self.clear_log,
            on_open_logs=self.open_logs_folder,
        )
        self.controls.pack(
            fill="x",
            pady=12,
        )

        self.status_panel = StatusPanel(
            main
        )
        self.status_panel.pack(
            fill="x",
            pady=(0, 12),
        )

        self.progress_panel = ProgressPanel(
            main
        )
        self.progress_panel.pack(
            fill="x",
            pady=(0, 12),
        )

        input_frame = ttk.LabelFrame(
            main,
            text="Pipeline Input",
            padding=10,
        )
        input_frame.pack(
            fill="x",
            pady=(0, 12),
        )

        input_frame.columnconfigure(
            0,
            weight=1,
        )

        self.command_entry = ttk.Entry(
            input_frame,
            textvariable=self.command_input_var,
            state="disabled",
        )
        self.command_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.command_entry.bind(
            "<Return>",
            lambda _event: self.send_pipeline_input(),
        )

        self.send_button = ttk.Button(
            input_frame,
            text="Send",
            command=self.send_pipeline_input,
            state="disabled",
        )
        self.send_button.grid(
            row=0,
            column=1,
        )

        ttk.Label(
            input_frame,
            text=(
                "When prompted, type PUBLISH here "
                "and press Enter or click Send."
            ),
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )

        self.activity_log = ActivityLog(
            main
        )
        self.activity_log.pack(
            fill="both",
            expand=True,
        )

    def validate_settings(
        self,
    ) -> tuple[int, int, float] | None:
        try:
            count = int(
                self.count_var.get().strip()
            )
            retries = int(
                self.retries_var.get().strip()
            )
            retry_delay = float(
                self.retry_delay_var.get().strip()
            )
        except ValueError:
            messagebox.showerror(
                "Invalid Settings",
                (
                    "Listings and retries must be whole "
                    "numbers, and retry delay must be a number."
                ),
            )
            return None

        if count < 1:
            messagebox.showerror(
                "Invalid Count",
                "Listings must be at least 1.",
            )
            return None

        if retries < 1:
            messagebox.showerror(
                "Invalid Retries",
                "Retries must be at least 1.",
            )
            return None

        if retry_delay < 0:
            messagebox.showerror(
                "Invalid Retry Delay",
                "Retry delay cannot be negative.",
            )
            return None

        return (
            count,
            retries,
            retry_delay,
        )

    def build_command(
        self,
        count: int,
        retries: int,
        retry_delay: float,
    ) -> list[str]:
        command = [
            sys.executable,
            "-u",
            str(PIPELINE_FILE),
            "--count",
            str(count),
            "--retries",
            str(retries),
            "--retry-delay",
            str(retry_delay),
        ]

        if (
            self.mode_var.get()
            == "publish"
        ):
            command.append(
                "--publish"
            )

        return command

    def start_pipeline(self) -> None:
        if (
            self.process is not None
            and self.process.poll() is None
        ):
            messagebox.showwarning(
                "Already Running",
                "The pipeline is already running.",
            )
            return

        if not PIPELINE_FILE.exists():
            messagebox.showerror(
                "Missing Pipeline",
                f"Could not find:\n{PIPELINE_FILE}",
            )
            return

        settings = self.validate_settings()

        if settings is None:
            return

        count, retries, retry_delay = settings

        if (
            self.mode_var.get()
            == "publish"
        ):
            confirmed = messagebox.askyesno(
                "Confirm Live Publishing",
                (
                    f"This will attempt to publish up to "
                    f"{count} listing(s).\n\nContinue?"
                ),
            )

            if not confirmed:
                return

        command = self.build_command(
            count,
            retries,
            retry_delay,
        )

        self.status_panel.reset()
        self.progress_panel.reset()

        self.activity_log.append(
            "\n"
            + "=" * 72
            + "\nStarting command:\n"
            + " ".join(command)
            + "\n"
            + "=" * 72
            + "\n"
        )

        self.command_input_var.set("")
        self.controls.set_running(True)

        self.command_entry.configure(
            state="normal",
        )
        self.send_button.configure(
            state="normal",
        )

        creation_flags = 0

        if os.name == "nt":
            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
            )

        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except Exception as error:
            self.process = None
            self.controls.set_running(False)

            self.command_entry.configure(
                state="disabled",
            )
            self.send_button.configure(
                state="disabled",
            )

            messagebox.showerror(
                "Start Failed",
                str(error),
            )
            return

        self.reader_thread = threading.Thread(
            target=self._read_process_output,
            daemon=True,
        )
        self.reader_thread.start()

    def send_pipeline_input(self) -> None:
        process = self.process

        if (
            process is None
            or process.poll() is not None
            or process.stdin is None
        ):
            messagebox.showwarning(
                "Pipeline Not Running",
                (
                    "There is no active pipeline "
                    "to receive input."
                ),
            )
            return

        value = (
            self.command_input_var.get().strip()
        )

        if not value:
            return

        try:
            process.stdin.write(
                value + "\n"
            )
            process.stdin.flush()

            self.activity_log.append(
                f"\n[Sent input: {value}]\n"
            )

            self.command_input_var.set("")
            self.command_entry.focus_set()

        except Exception as error:
            messagebox.showerror(
                "Input Failed",
                str(error),
            )

    def _read_process_output(self) -> None:
        process = self.process

        if (
            process is None
            or process.stdout is None
        ):
            return

        try:
            for line in process.stdout:
                self.output_queue.put(
                    line
                )
        finally:
            return_code = process.wait()

            self.output_queue.put(
                f"\n[Process exited with code "
                f"{return_code}]\n"
            )

            self.output_queue.put(
                "__PROCESS_FINISHED__"
            )

    def _poll_output_queue(self) -> None:
        try:
            while True:
                message = (
                    self.output_queue.get_nowait()
                )

                if (
                    message
                    == "__PROCESS_FINISHED__"
                ):
                    self._process_finished()
                    continue

                event = parse_status_line(
                    message
                )

                if event is not None:
                    self._handle_status_event(
                        event
                    )
                    continue

                self.activity_log.append(
                    message
                )

                if (
                    "Type PUBLISH to click the final button"
                    in message
                ):
                    self.status_panel.set_step(
                        "Waiting for PUBLISH"
                    )
                    self.command_entry.focus_set()

        except queue.Empty:
            pass

        self.root.after(
            100,
            self._poll_output_queue,
        )

    def _handle_status_event(
        self,
        event: StatusEvent,
    ) -> None:
        key = event.key
        value = event.value

        if key == "TITLE":
            self.status_panel.set_title(
                value
            )

        elif key == "STEP":
            self.status_panel.set_step(
                value
            )

        elif key == "PRICE":
            self.status_panel.set_price(
                value
            )

        elif key == "SIZES":
            self.status_panel.set_sizes(
                value
            )

        elif key == "MODE":
            self.status_panel.set_mode(
                value
            )

        elif key == "PROGRESS":
            self.progress_panel.set_progress(
                value
            )

        elif key == "PERCENT":
            percent = parse_percent(
                value
            )

            if percent is not None:
                self.progress_panel.set_percent(
                    percent
                )

        elif key == "UPLOADED":
            self.progress_panel.set_uploaded(
                value
            )

        elif key == "EXISTING":
            self.progress_panel.set_existing(
                value
            )

        elif key == "FAILED":
            self.progress_panel.set_failed(
                value
            )

        elif key == "ETA":
            self.progress_panel.set_eta(
                value
            )

    def _process_finished(self) -> None:
        return_code = (
            self.process.returncode
            if self.process is not None
            else None
        )

        self.controls.set_running(False)

        self.command_entry.configure(
            state="disabled",
        )
        self.send_button.configure(
            state="disabled",
        )

        if return_code == 0:
            self.status_panel.set_step(
                "Completed"
            )
            self.progress_panel.set_percent(
                100.0
            )
        else:
            self.status_panel.set_step(
                f"Stopped or failed "
                f"(code {return_code})"
            )

        self.process = None

    def stop_pipeline(self) -> None:
        process = self.process

        if (
            process is None
            or process.poll() is not None
        ):
            return

        confirmed = messagebox.askyesno(
            "Stop Pipeline",
            (
                "Stop the current run?\n\n"
                "The resume checkpoint will remain "
                "available for the next run."
            ),
        )

        if not confirmed:
            return

        self.status_panel.set_step(
            "Stopping..."
        )

        try:
            process.terminate()
        except Exception as error:
            messagebox.showerror(
                "Stop Failed",
                str(error),
            )

    def clear_log(self) -> None:
        self.activity_log.clear()

    def open_logs_folder(self) -> None:
        LOGS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            if os.name == "nt":
                os.startfile(
                    str(LOGS_DIR)
                )
            elif sys.platform == "darwin":
                subprocess.Popen(
                    [
                        "open",
                        str(LOGS_DIR),
                    ]
                )
            else:
                subprocess.Popen(
                    [
                        "xdg-open",
                        str(LOGS_DIR),
                    ]
                )
        except Exception as error:
            messagebox.showerror(
                "Could Not Open Logs",
                str(error),
            )

    def on_close(self) -> None:
        if (
            self.process is not None
            and self.process.poll() is None
        ):
            confirmed = messagebox.askyesno(
                "Pipeline Running",
                (
                    "The pipeline is still running.\n\n"
                    "Stop it and close the dashboard?"
                ),
            )

            if not confirmed:
                return

            try:
                self.process.terminate()
            except Exception:
                pass

        self.root.destroy()