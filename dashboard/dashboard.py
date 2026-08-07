from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from dashboard.activity_log import ActivityLog
from dashboard.inventory_panel import InventoryPanel
from dashboard.recovery_panel import RecoveryPanel
from dashboard.upload_queue_panel import UploadQueuePanel
from dashboard.controls import ControlsPanel
from dashboard.pipeline_io import (
    StatusEvent,
    parse_percent,
    parse_status_line,
)
from dashboard.progress_panel import ProgressPanel
from dashboard.status_panel import StatusPanel
from dashboard.styles import apply_styles
from dashboard.thumbnail_panel import ThumbnailPanel
from pipeline.closet_sync import ClosetSync, SyncResult
from pipeline_control import (
    request_pause,
    request_resume,
    request_stop_after_current,
)
from runtime_paths import (
    APP_DIR,
    LOGS_DIR,
    PIPELINE_EXE,
    PIPELINE_SCRIPT,
    ensure_runtime_directories,
    is_frozen,
)


PROJECT_DIR = APP_DIR
PIPELINE_FILE = PIPELINE_SCRIPT


class PoshCopierDashboard:
    def __init__(
        self,
        root: tk.Tk,
    ) -> None:
        self.root = root
        self.root.title("PoshCopier Dashboard")
        self.root.geometry("1050x980")
        self.root.minsize(900, 760)

        ensure_runtime_directories()
        apply_styles(root)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None

        self.mode_var = tk.StringVar(value="dry_run")
        self.count_var = tk.StringVar(value="5")
        self.retries_var = tk.StringVar(value="3")
        self.retry_delay_var = tk.StringVar(value="3")
        self.command_input_var = tk.StringVar(value="")

        # Closet sync state
        self._sync_thread: threading.Thread | None = None
        self._sync_running = False
        self.import_limit_var = tk.StringVar()

        self._build_interface()
        self._load_import_limit_from_config()
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
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="Source-to-destination listing pipeline",
            style="Subtitle.TLabel",
        ).pack(
            anchor="w",
            pady=(0, 14),
        )
        notebook = ttk.Notebook(
            main
        )
        notebook.pack(
            fill="both",
            expand=True,
        )

        pipeline_tab = ttk.Frame(
            notebook,
            padding=0,
        )
        inventory_tab = ttk.Frame(
            notebook,
            padding=0,
        )
        upload_queue_tab = ttk.Frame(
            notebook,
            padding=0,
        )
        recovery_tab = ttk.Frame(
            notebook,
            padding=0,
        )

        notebook.add(
            pipeline_tab,
            text="Pipeline",
        )
        notebook.add(
            inventory_tab,
            text="Inventory",
        )
        notebook.add(
            upload_queue_tab,
            text="Upload Queue",
        )
        notebook.add(
            recovery_tab,
            text="Recovery",
        )
        settings = ttk.LabelFrame(
            pipeline_tab,
            text="Run Settings",
            padding=12,
)
        settings.pack(fill="x")

        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

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

        mode_frame = ttk.Frame(settings)
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
        ).pack(side="left")

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
            pipeline_tab,
            on_start=self.start_pipeline,
            on_pause=self.pause_pipeline,
            on_resume=self.resume_pipeline,
            on_stop_after_current=self.stop_after_current,
            on_stop=self.stop_pipeline,
            on_clear_log=self.clear_log,
            on_open_logs=self.open_logs_folder,
        )
        self.controls.pack(
            fill="x",
            pady=12,
        )

        # Closet Sync section
        sync_frame = ttk.LabelFrame(
            pipeline_tab,
            text="Closet Sync",
            padding=12,
        )
        sync_frame.pack(fill="x", pady=(0, 12))

        sync_frame.columnconfigure(1, weight=1)
        sync_frame.columnconfigure(3, weight=1)

        # Sync button
        self.sync_button = ttk.Button(
            sync_frame,
            text="Sync Closet",
            command=self._on_sync_closet,
        )
        self.sync_button.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=4,
        )

        # Import Limit label
        ttk.Label(
            sync_frame,
            text="Import Limit:",
        ).grid(
            row=0,
            column=1,
            sticky="e",
            padx=(0, 8),
            pady=4,
        )

        # Import Limit combobox
        self.import_limit_combo = ttk.Combobox(
            sync_frame,
            textvariable=self.import_limit_var,
            values=["25", "50", "100", "Unlimited"],
            state="readonly",
            width=12,
        )
        self.import_limit_combo.grid(
            row=0,
            column=2,
            sticky="w",
            pady=4,
        )
        self.import_limit_combo.bind("<<ComboboxSelected>>", self._on_import_limit_changed)

        # Status label
        ttk.Label(
            sync_frame,
            text="Status:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=4,
        )

        self.sync_status_var = tk.StringVar(value="Idle")
        ttk.Label(
            sync_frame,
            textvariable=self.sync_status_var,
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="w",
            pady=4,
        )

        # Progress label
        ttk.Label(
            sync_frame,
            text="Progress:",
        ).grid(
            row=2,
            column=0,
            sticky="nw",
            padx=(0, 12),
            pady=4,
        )

        self.sync_progress_var = tk.StringVar(value="—")
        ttk.Label(
            sync_frame,
            textvariable=self.sync_progress_var,
        ).grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="w",
            pady=4,
        )

        # Output window
        ttk.Label(
            sync_frame,
            text="Output:",
        ).grid(
            row=3,
            column=0,
            sticky="nw",
            padx=(0, 12),
            pady=(8, 4),
        )

        self.sync_output = scrolledtext.ScrolledText(
            sync_frame,
            height=6,
            width=80,
            wrap="word",
            state="disabled",
        )
        self.sync_output.grid(
            row=3,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=(8, 4),
        )

        upper_content = ttk.Frame(pipeline_tab)
        upper_content.pack(
            fill="x",
            pady=(0, 12),
        )

        upper_content.columnconfigure(
            0,
            weight=0,
        )
        upper_content.columnconfigure(
            1,
            weight=1,
        )

        self.thumbnail_panel = ThumbnailPanel(
            upper_content
        )
        self.thumbnail_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 12),
        )

        self.status_panel = StatusPanel(
            upper_content
        )
        self.status_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        self.progress_panel = ProgressPanel(
            pipeline_tab
        )
        self.progress_panel.pack(
            fill="x",
            pady=(0, 12),
        )

        input_frame = ttk.LabelFrame(
            pipeline_tab,
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

        self.activity_log = ActivityLog(pipeline_tab)
        self.activity_log.pack(
            fill="both",
            expand=True,
        )
        self.inventory_panel = InventoryPanel(
            inventory_tab
        )
        self.inventory_panel.pack(
            fill="both",
            expand=True,
        )

        self.upload_queue_panel = UploadQueuePanel(
            upload_queue_tab
        )
        self.upload_queue_panel.pack(
            fill="both",
            expand=True,
        )

        self.recovery_panel = RecoveryPanel(
            recovery_tab
        )
        self.recovery_panel.pack(
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

        return count, retries, retry_delay

    def build_command(
        self,
        count: int,
        retries: int,
        retry_delay: float,
    ) -> list[str]:
        arguments = [
            "--count",
            str(count),
            "--retries",
            str(retries),
            "--retry-delay",
            str(retry_delay),
        ]

        if self.mode_var.get() == "publish":
            arguments.append("--publish")

        if is_frozen():
            if not PIPELINE_EXE.exists():
                raise FileNotFoundError(
                    "PoshCopierPipeline.exe was not found beside "
                    "PoshCopier.exe."
                )

            return [
                str(PIPELINE_EXE),
                *arguments,
            ]

        return [
            sys.executable,
            "-u",
            str(PIPELINE_FILE),
            *arguments,
        ]

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

        settings = self.validate_settings()

        if settings is None:
            return

        count, retries, retry_delay = settings

        if self.mode_var.get() == "publish":
            confirmed = messagebox.askyesno(
                "Confirm Live Publishing",
                (
                    f"This will attempt to publish up to "
                    f"{count} listing(s).\n\nContinue?"
                ),
            )

            if not confirmed:
                return

        try:
            command = self.build_command(
                count,
                retries,
                retry_delay,
            )
        except Exception as error:
            messagebox.showerror(
                "Missing Pipeline",
                str(error),
            )
            return

        self.thumbnail_panel.reset()
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

            if is_frozen():
                creation_flags |= (
                    subprocess.CREATE_NO_WINDOW
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

        value = self.command_input_var.get().strip()

        if not value:
            return

        try:
            process.stdin.write(value + "\n")
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
                self.output_queue.put(line)
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

        elif key == "LISTING_ID":
            self.thumbnail_panel.show_listing(
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

    def pause_pipeline(self) -> None:
        process = self.process

        if (
            process is None
            or process.poll() is not None
        ):
            return

        try:
            request_pause()
            self.controls.set_paused(True)
            self.status_panel.set_step(
                "Pause requested - finishing current listing"
            )
        except Exception as error:
            messagebox.showerror(
                "Pause Failed",
                str(error),
            )

    def resume_pipeline(self) -> None:
        process = self.process

        if (
            process is None
            or process.poll() is not None
        ):
            return

        try:
            request_resume()
            self.controls.set_paused(False)
            self.status_panel.set_step(
                "Resuming"
            )
        except Exception as error:
            messagebox.showerror(
                "Resume Failed",
                str(error),
            )

    def stop_after_current(self) -> None:
        process = self.process

        if (
            process is None
            or process.poll() is not None
        ):
            return

        confirmed = messagebox.askyesno(
            "Stop After Current",
            (
                "Finish the current listing, save progress, "
                "and then stop?"
            ),
        )

        if not confirmed:
            return

        try:
            request_stop_after_current()
            self.status_panel.set_step(
                "Stop requested after current listing"
            )
        except Exception as error:
            messagebox.showerror(
                "Stop Request Failed",
                str(error),
            )

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

    def _get_source_closet_url(self) -> str | None:
        """Get source closet URL from config.json or prompt user."""
        config_file = PROJECT_DIR / "config.json"
        existing_config = {}
        config_is_valid = False
        
        # Try reading from config.json
        if config_file.exists():
            try:
                existing_config = json.loads(config_file.read_text(encoding="utf-8"))
                config_is_valid = True
                url = existing_config.get("source_closet_url", "").strip()
                if url:
                    return url
            except Exception:
                # Config exists but is invalid JSON
                config_is_valid = False
        
        # Prompt user for URL
        while True:
            url = simpledialog.askstring(
                "Source Closet URL",
                "Enter the source Poshmark closet URL:\n"
                "(e.g., https://poshmark.com/closet/username)",
                parent=self.root,
            )
            
            if not url:
                # User cancelled
                return None
            
            url = url.strip()
            
            # Validate URL format
            if not url.startswith("https://poshmark.com/closet/"):
                messagebox.showerror(
                    "Invalid URL",
                    "URL must start with:\nhttps://poshmark.com/closet/",
                )
                continue
            
            # Extract and validate username
            username = url.replace("https://poshmark.com/closet/", "").strip("/")
            if not username:
                messagebox.showerror(
                    "Invalid URL",
                    "URL must contain a closet username after:\n"
                    "https://poshmark.com/closet/",
                )
                continue
            
            # Valid URL - try to save it
            if config_is_valid:
                # Merge with existing config
                try:
                    existing_config["source_closet_url"] = url
                    config_file.write_text(
                        json.dumps(existing_config, indent=2),
                        encoding="utf-8",
                    )
                except Exception as error:
                    messagebox.showwarning(
                        "Config Save Failed",
                        f"Could not save to config.json:\n{error}\n\n"
                        "Continuing with this URL for current session only.",
                    )
            elif config_file.exists():
                # Config exists but is invalid - don't overwrite
                messagebox.showwarning(
                    "Invalid Config File",
                    "config.json exists but contains invalid JSON.\n\n"
                    "Please fix or delete the file manually.\n\n"
                    "Continuing with this URL for current session only.",
                )
            else:
                # No config file - create new one
                try:
                    config_file.write_text(
                        json.dumps({"source_closet_url": url}, indent=2),
                        encoding="utf-8",
                    )
                except Exception as error:
                    messagebox.showwarning(
                        "Config Save Failed",
                        f"Could not create config.json:\n{error}\n\n"
                        "Continuing with this URL for current session only.",
                    )
            
            return url

    def _load_import_limit_from_config(self) -> None:
        """Load closet_sync_import_limit from config.json."""
        config_file = PROJECT_DIR / "config.json"
        default_value = "50"
        
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding="utf-8"))
                limit = config.get("closet_sync_import_limit")
                
                # Validate and convert
                if limit is None:
                    self.import_limit_var.set("Unlimited")
                elif limit in [25, 50, 100]:
                    self.import_limit_var.set(str(limit))
                else:
                    # Invalid value, use default
                    self.import_limit_var.set(default_value)
            except Exception:
                # Config read failed, use default
                self.import_limit_var.set(default_value)
        else:
            # No config file, use default
            self.import_limit_var.set(default_value)

    def _on_import_limit_changed(self, event=None) -> None:
        """Save import limit to config.json when changed."""
        config_file = PROJECT_DIR / "config.json"
        
        try:
            # Read existing config
            if config_file.exists():
                existing_config = json.loads(config_file.read_text(encoding="utf-8"))
            else:
                existing_config = {}
            
            # Convert UI value to config value
            ui_value = self.import_limit_var.get()
            if ui_value == "Unlimited":
                config_value = None
            else:
                config_value = int(ui_value)
            
            # Update and save
            existing_config["closet_sync_import_limit"] = config_value
            config_file.write_text(
                json.dumps(existing_config, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Non-critical, just continue
            pass

    def _get_max_new_listings(self) -> int | None:
        """Convert UI import limit to max_new_listings parameter."""
        ui_value = self.import_limit_var.get()
        if ui_value == "Unlimited":
            return None
        else:
            return int(ui_value)

    def _on_sync_closet(self) -> None:
        """Handle Sync Closet button click."""
        if self._sync_running:
            messagebox.showwarning(
                "Sync Running",
                "Closet sync is already running.",
            )
            return
        
        # Get source closet URL
        source_url = self._get_source_closet_url()
        if not source_url:
            messagebox.showerror(
                "No Source URL",
                "Source closet URL is required to sync.",
            )
            return
        
        # Get import limit for display
        max_new = self._get_max_new_listings()
        limit_display = "Unlimited" if max_new is None else str(max_new)
        
        # Show confirmation dialog
        confirmed = messagebox.askyesno(
            "Confirm Closet Sync",
            "This will:\n\n"
            "• Scan the source closet\n"
            "• Download only NEW listings\n"
            "• Update Inventory\n"
            "• Queue Ready listings\n\n"
            f"Import Limit: {limit_display}\n\n"
            "No listings will be uploaded automatically.\n\n"
            "Continue?",
        )
        
        if not confirmed:
            return
        
        # Update UI state
        self._sync_running = True
        self.sync_button.configure(state="disabled")
        self.sync_status_var.set("Running")
        self.sync_progress_var.set("Starting...")
        
        # Clear output
        self.sync_output.configure(state="normal")
        self.sync_output.delete("1.0", "end")
        self.sync_output.configure(state="disabled")
        
        # Start worker thread
        self._sync_thread = threading.Thread(
            target=self._run_closet_sync_worker,
            args=(source_url, max_new),
            daemon=True,
        )
        self._sync_thread.start()

    def _run_closet_sync_worker(
        self,
        source_url: str,
        max_new_listings: int | None,
    ) -> None:
        """Worker thread for closet sync."""
        try:
            # Create ClosetSync instance with progress callback
            sync = ClosetSync(
                source_closet_url=source_url,
                progress_callback=self._update_sync_progress,
                max_new_listings=max_new_listings,
            )
            
            # Run sync
            result = sync.run()
            
            # Schedule completion handler on main thread
            self.root.after(0, self._on_sync_complete, result)
            
        except Exception as error:
            # Schedule error handler on main thread
            error_msg = str(error)
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Sync Failed",
                    f"Closet sync failed:\n\n{error_msg}",
                ),
            )
            self.root.after(0, self._reset_sync_ui)

    def _update_sync_progress(self, message: str) -> None:
        """Update sync progress (called from worker thread)."""
        def update_ui():
            # Update progress label
            self.sync_progress_var.set(message)
            
            # Append to output window
            self.sync_output.configure(state="normal")
            self.sync_output.insert("end", message + "\n")
            self.sync_output.see("end")
            self.sync_output.configure(state="disabled")
        
        # Schedule UI update on main thread
        self.root.after(0, update_ui)

    def _on_sync_complete(self, result: SyncResult) -> None:
        """Handle sync completion."""
        if result.success:
            # Format elapsed time
            elapsed = result.stats.elapsed_seconds
            if elapsed < 60:
                elapsed_str = f"{elapsed:.1f} seconds"
            else:
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                elapsed_str = f"{minutes}m {seconds}s"
            
            # Build summary message
            summary = (
                f"Closet Sync Complete\n\n"
                f"Scanned: {result.stats.total_scanned}\n"
                f"Already Downloaded: {result.stats.already_downloaded}\n"
                f"New Downloaded: {result.stats.new_imported}\n"
                f"Queued: {result.stats.queued}\n"
                f"Failed: {len(result.stats.failed)}\n"
                f"Elapsed Time: {elapsed_str}"
            )
            
            if result.stats.failed:
                summary += "\n\nFailed listings:\n"
                for listing_id, error in result.stats.failed[:5]:
                    summary += f"  • {listing_id}: {error[:50]}\n"
                if len(result.stats.failed) > 5:
                    summary += f"  ... and {len(result.stats.failed) - 5} more"
            
            messagebox.showinfo("Sync Complete", summary)
            
            # Refresh panels
            self.inventory_panel.refresh()
            self.upload_queue_panel.refresh()
            
        else:
            messagebox.showerror(
                "Sync Failed",
                f"Closet sync failed:\n\n{result.error_message}",
            )
        
        # Reset UI
        self._reset_sync_ui()

    def _reset_sync_ui(self) -> None:
        """Reset sync UI to idle state."""
        self._sync_running = False
        self.sync_button.configure(state="normal")
        self.sync_status_var.set("Idle")
        self.sync_progress_var.set("—")

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
