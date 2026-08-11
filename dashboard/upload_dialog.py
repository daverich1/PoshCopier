from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from inventory.inventory_item import InventoryItem
from runtime_paths import APP_DIR, PIPELINE_EXE, is_frozen


PROJECT_DIR = APP_DIR
PIPELINE_ENTRY = PROJECT_DIR / "pipeline_entry.py"


class UploadDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        item: InventoryItem,
        *,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self.item = item
        self.on_finished = on_finished
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self.mode_var = tk.StringVar(value="dry_run")
        self.size_mode_var = tk.StringVar(value="combined")
        self.status_var = tk.StringVar(value="Ready")

        self.title(f"Upload Listing - {item.title or item.listing_id}")
        self.geometry("820x620")
        self.minsize(700, 520)
        self.transient(parent)

        self._build_interface()
        self._poll_output_queue()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_interface(self) -> None:
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        ttk.Label(
            main,
            text="Upload Selected Listing",
            font=("Segoe UI", 17, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            main,
            text=self.item.title or "Untitled listing",
            font=("Segoe UI", 10, "bold"),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 14))

        mode_frame = ttk.LabelFrame(main, text="Mode", padding=10)
        mode_frame.grid(row=2, column=0, sticky="ew")

        ttk.Radiobutton(
            mode_frame,
            text="Dry Run",
            variable=self.mode_var,
            value="dry_run",
        ).pack(side="left")

        ttk.Radiobutton(
            mode_frame,
            text="Publish Live",
            variable=self.mode_var,
            value="publish",
        ).pack(side="left", padx=(16, 0))

        ttk.Label(mode_frame, text="Multi-size publishing:").pack(
            side="left", padx=(28, 8)
        )
        ttk.Combobox(
            mode_frame,
            textvariable=self.size_mode_var,
            values=("combined", "separate"),
            state="readonly",
            width=12,
        ).pack(side="left")

        controls = ttk.Frame(main)
        controls.grid(row=3, column=0, sticky="ew", pady=12)

        self.start_button = ttk.Button(
            controls,
            text="Start",
            command=self.start,
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            controls,
            text="Stop",
            command=self.stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))

        self.close_button = ttk.Button(
            controls,
            text="Close",
            command=self.close,
        )
        self.close_button.pack(side="left", padx=(8, 0))

        ttk.Label(controls, textvariable=self.status_var).pack(side="right")

        log_frame = ttk.LabelFrame(main, text="Live Output", padding=8)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def build_command(self) -> list[str]:
        arguments = [
            "--listing-file",
            str(self.item.listing_path),
            "--retries",
            "3",
            "--retry-delay",
            "3.0",
            "--size-mode",
            self.size_mode_var.get(),
        ]

        if self.mode_var.get() == "publish":
            arguments.append("--publish")

        if is_frozen():
            if not PIPELINE_EXE.exists():
                raise FileNotFoundError(
                    "PoshCopierPipeline.exe was not found beside "
                    "the PoshCopier application."
                )
            return [str(PIPELINE_EXE), *arguments]

        if not PIPELINE_ENTRY.exists():
            raise FileNotFoundError(f"Could not find:\n{PIPELINE_ENTRY}")

        return [sys.executable, "-u", str(PIPELINE_ENTRY), *arguments]

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        if self.mode_var.get() == "publish":
            confirmed = messagebox.askyesno(
                "Confirm Live Publish",
                "This will attempt to publish the selected listing to the "
                "destination closet.\n\n"
                f"Multi-size mode: {self.size_mode_var.get()}\n\nContinue?",
                parent=self,
            )
            if not confirmed:
                return

        try:
            command = self.build_command()
        except Exception as error:
            messagebox.showerror("Could Not Start", str(error), parent=self)
            return

        self._clear_log()
        self._append_log(
            "=" * 72
            + "\nStarting command:\n"
            + subprocess.list2cmdline(command)
            + "\n"
            + "=" * 72
            + "\n"
        )

        self.status_var.set("Running")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.close_button.configure(state="disabled")

        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            if is_frozen():
                creation_flags |= subprocess.CREATE_NO_WINDOW

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
            self.status_var.set("Failed to start")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.close_button.configure(state="normal")
            messagebox.showerror("Start Failed", str(error), parent=self)
            return

        self.reader_thread = threading.Thread(
            target=self._read_output,
            daemon=True,
        )
        self.reader_thread.start()

    def _read_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return

        try:
            for line in process.stdout:
                self.output_queue.put(line)
        finally:
            return_code = process.wait()
            self.output_queue.put(f"\n[Process exited with code {return_code}]\n")
            self.output_queue.put(f"__PROCESS_FINISHED__:{return_code}")

    def _poll_output_queue(self) -> None:
        try:
            while True:
                message = self.output_queue.get_nowait()

                if message.startswith("__PROCESS_FINISHED__:"):
                    return_code_text = message.split(":", 1)[1]
                    try:
                        return_code = int(return_code_text)
                    except ValueError:
                        return_code = 1
                    self._process_finished(return_code)
                    continue

                self._append_log(message)
        except queue.Empty:
            pass

        if self.winfo_exists():
            self.after(100, self._poll_output_queue)

    def _process_finished(self, return_code: int) -> None:
        self.process = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.close_button.configure(state="normal")

        if return_code == 0:
            self.status_var.set("Complete")
        else:
            self.status_var.set(f"Failed (code {return_code})")

        if self.on_finished is not None:
            try:
                self.on_finished()
            except Exception:
                pass

    def stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return

        confirmed = messagebox.askyesno(
            "Stop Upload",
            "Stop the current selected-listing run?",
            parent=self,
        )
        if not confirmed:
            return

        self.status_var.set("Stopping...")
        try:
            process.terminate()
        except Exception as error:
            messagebox.showerror("Stop Failed", str(error), parent=self)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning(
                "Upload Running",
                "Stop the running upload before closing this window.",
                parent=self,
            )
            return
        self.destroy()
