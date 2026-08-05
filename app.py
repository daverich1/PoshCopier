from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


PROJECT_DIR = Path(__file__).resolve().parent
PIPELINE_FILE = PROJECT_DIR / "run_pipeline.py"
LOGS_DIR = PROJECT_DIR / "logs"


class PoshCopierDashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PoshCopier Dashboard")
        self.root.geometry("980x720")
        self.root.minsize(820, 600)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None

        self.mode_var = tk.StringVar(value="dry_run")
        self.count_var = tk.StringVar(value="5")
        self.retries_var = tk.StringVar(value="3")
        self.retry_delay_var = tk.StringVar(value="3")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)

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

        title = ttk.Label(
            main,
            text="PoshCopier",
            font=("Segoe UI", 22, "bold"),
        )
        title.pack(
            anchor="w",
        )

        subtitle = ttk.Label(
            main,
            text=(
                "Source-to-destination listing pipeline"
            ),
            font=("Segoe UI", 10),
        )
        subtitle.pack(
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

        self.count_entry = ttk.Entry(
            settings,
            textvariable=self.count_var,
            width=12,
        )
        self.count_entry.grid(
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

        self.retries_entry = ttk.Entry(
            settings,
            textvariable=self.retries_var,
            width=12,
        )
        self.retries_entry.grid(
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

        self.retry_delay_entry = ttk.Entry(
            settings,
            textvariable=self.retry_delay_var,
            width=12,
        )
        self.retry_delay_entry.grid(
            row=1,
            column=3,
            sticky="w",
            pady=4,
        )

        controls = ttk.Frame(
            main
        )
        controls.pack(
            fill="x",
            pady=12,
        )

        self.start_button = ttk.Button(
            controls,
            text="Start",
            command=self.start_pipeline,
        )
        self.start_button.pack(
            side="left",
        )

        self.stop_button = ttk.Button(
            controls,
            text="Stop",
            command=self.stop_pipeline,
            state="disabled",
        )
        self.stop_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.clear_button = ttk.Button(
            controls,
            text="Clear Log",
            command=self.clear_log,
        )
        self.clear_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.logs_button = ttk.Button(
            controls,
            text="Open Logs",
            command=self.open_logs_folder,
        )
        self.logs_button.pack(
            side="left",
            padx=(8, 0),
        )

        status_frame = ttk.LabelFrame(
            main,
            text="Status",
            padding=10,
        )
        status_frame.pack(
            fill="x",
            pady=(0, 12),
        )

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(
            anchor="w",
        )

        self.progress_bar = ttk.Progressbar(
            status_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.pack(
            fill="x",
            pady=(8, 0),
        )

        log_frame = ttk.LabelFrame(
            main,
            text="Live Output",
            padding=8,
        )
        log_frame.pack(
            fill="both",
            expand=True,
        )

        log_frame.rowconfigure(
            0,
            weight=1,
        )
        log_frame.columnconfigure(
            0,
            weight=1,
        )

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.log_text.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.log_text.configure(
            yscrollcommand=scrollbar.set,
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
                "Listings and retries must be whole numbers, "
                "and retry delay must be a number.",
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
                    f"{count} listing(s).\n\n"
                    "Continue?"
                ),
            )

            if not confirmed:
                return

        command = self.build_command(
            count,
            retries,
            retry_delay,
        )

        self.append_log(
            "\n"
            + "=" * 72
            + "\nStarting command:\n"
            + " ".join(command)
            + "\n"
            + "=" * 72
            + "\n"
        )

        self.progress_var.set(
            0.0
        )
        self.status_var.set(
            "Running"
        )

        self.start_button.configure(
            state="disabled",
        )
        self.stop_button.configure(
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
                stdin=None,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except Exception as error:
            self.process = None
            self.status_var.set(
                "Failed to start"
            )
            self.start_button.configure(
                state="normal",
            )
            self.stop_button.configure(
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
                message = self.output_queue.get_nowait()

                if message == "__PROCESS_FINISHED__":
                    self._process_finished()
                    continue

                self.append_log(
                    message
                )
                self._update_progress_from_line(
                    message
                )

        except queue.Empty:
            pass

        self.root.after(
            100,
            self._poll_output_queue,
        )

    def _update_progress_from_line(
        self,
        line: str,
    ) -> None:
        line = line.strip()

        if not line.startswith(
            "PROGRESS:"
        ):
            return

        try:
            percent_start = line.index(
                "("
            ) + 1
            percent_end = line.index(
                "%",
                percent_start,
            )

            percent = float(
                line[
                    percent_start:
                    percent_end
                ]
            )

            self.progress_var.set(
                percent
            )

            self.status_var.set(
                line
            )

        except (
            ValueError,
            IndexError,
        ):
            pass

    def _process_finished(self) -> None:
        return_code = (
            self.process.returncode
            if self.process is not None
            else None
        )

        self.start_button.configure(
            state="normal",
        )
        self.stop_button.configure(
            state="disabled",
        )

        if return_code == 0:
            self.status_var.set(
                "Completed"
            )
            self.progress_var.set(
                100.0
            )
        else:
            self.status_var.set(
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

        self.status_var.set(
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
        self.log_text.configure(
            state="normal",
        )
        self.log_text.delete(
            "1.0",
            "end",
        )
        self.log_text.configure(
            state="disabled",
        )

    def append_log(
        self,
        text: str,
    ) -> None:
        self.log_text.configure(
            state="normal",
        )
        self.log_text.insert(
            "end",
            text,
        )
        self.log_text.see(
            "end"
        )
        self.log_text.configure(
            state="disabled",
        )

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


def main() -> None:
    root = tk.Tk()

    try:
        style = ttk.Style(root)

        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass

    PoshCopierDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
