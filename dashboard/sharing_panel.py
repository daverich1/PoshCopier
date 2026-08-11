"""Dashboard controls for safe follower-sharing runs."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from sharing.share_config import MAX_FOLLOWER_SHARES_PER_RUN, ShareConfig
from sharing.share_engine import PoshmarkShareEngine
from sharing.share_progress import ShareProgress, ShareResult, ShareStatus
from sharing.party_runner import (
    MAX_AUTOMATIC_PARTY_SHARES,
    run_live_party_batch,
    run_party_candidate,
)
from sharing.follow_runner import run_follow_backs
from sharing.share_runner import run_community_sharing, run_follower_sharing


DESTINATION_CLOSET_URL = "https://poshmark.com/closet/dveshop"


class SharingPanel(ttk.Frame):
    """Follower-sharing UI with conservative defaults and live progress."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=16)
        self.count_var = tk.StringVar(value="1")
        self.delay_var = tk.StringVar(value="5")
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="0 / 0 (0%)")
        self.shared_var = tk.StringVar(value="0")
        self.skipped_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.eta_var = tk.StringVar(value="—")
        self.party_name_var = tk.StringVar(value="")
        self.party_listing_url_var = tk.StringVar(value="")
        self.auto_party_count_var = tk.StringVar(value="10")
        self.community_closet_url_var = tk.StringVar(value="")
        self.community_count_var = tk.StringVar(value="1")
        self.follow_back_count_var = tk.StringVar(value="1")
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._engine: PoshmarkShareEngine | None = None
        self._auto_party_preview: tuple[str, int, int] | None = None

        self._build_interface()
        self.after(100, self._poll_events)

    def _build_interface(self) -> None:
        settings = ttk.LabelFrame(self, text="Follower Sharing", padding=12)
        settings.pack(fill="x")

        ttk.Label(settings, text="Maximum shares:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(settings, textvariable=self.count_var, width=10).grid(
            row=0, column=1, sticky="w", pady=4,
        )
        ttk.Label(settings, text="Delay (seconds):").grid(
            row=0, column=2, sticky="e", padx=(24, 8), pady=4,
        )
        ttk.Entry(settings, textvariable=self.delay_var, width=10).grid(
            row=0, column=3, sticky="w", pady=4,
        )

        ttk.Label(
            settings,
            text="Shares go to followers. Party and Posh Shows sharing remain disabled here.",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=12)
        self.start_button = ttk.Button(controls, text="Start Sharing", command=self.start)
        self.start_button.pack(side="left")
        self.pause_button = ttk.Button(
            controls, text="Pause", command=self.pause, state="disabled",
        )
        self.pause_button.pack(side="left", padx=(8, 0))
        self.resume_button = ttk.Button(
            controls, text="Resume", command=self.resume, state="disabled",
        )
        self.resume_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(
            controls,
            text="Stop After Current",
            command=self.stop_after_current,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))

        progress = ttk.LabelFrame(self, text="Progress", padding=12)
        progress.pack(fill="x", pady=(0, 12))
        progress.columnconfigure(0, weight=1)
        ttk.Label(progress, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w",
        )
        ttk.Label(progress, textvariable=self.progress_text_var).grid(
            row=0, column=1, sticky="e",
        )
        ttk.Progressbar(
            progress, variable=self.progress_var, maximum=100, mode="determinate",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 12))

        stats = ttk.Frame(progress)
        stats.grid(row=2, column=0, columnspan=2, sticky="ew")
        for column in range(4):
            stats.columnconfigure(column, weight=1)
        for column, (label, variable) in enumerate((
            ("Shared", self.shared_var),
            ("Skipped", self.skipped_var),
            ("Failed", self.failed_var),
            ("ETA", self.eta_var),
        )):
            frame = ttk.Frame(stats)
            frame.grid(row=0, column=column, sticky="nsew")
            ttk.Label(frame, text=label, font=("Segoe UI", 9, "bold")).pack()
            ttk.Label(frame, textvariable=variable).pack(pady=(3, 0))

        ttk.Label(self, text="Activity:").pack(anchor="w")
        self.output = scrolledtext.ScrolledText(
            self, height=16, wrap="word", state="disabled",
        )
        self.output.pack(fill="both", expand=True, pady=(4, 0))

        party = ttk.LabelFrame(self, text="Live Party Sharing (One Listing)", padding=12)
        party.pack(fill="x", pady=(12, 0))
        party.columnconfigure(1, weight=1)
        ttk.Label(party, text="Exact live party name:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(party, textvariable=self.party_name_var).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=4,
        )
        ttk.Label(party, text="Destination listing URL:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(party, textvariable=self.party_listing_url_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=4,
        )
        self.validate_party_button = ttk.Button(
            party, text="Validate Candidate", command=self.validate_party_candidate,
        )
        self.validate_party_button.grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.share_party_button = ttk.Button(
            party, text="Share One to Live Party", command=self.share_party_candidate,
        )
        self.share_party_button.grid(row=2, column=2, sticky="e", pady=(8, 0))
        ttk.Label(
            party,
            text="Validation is read-only. Live sharing requires confirmation and is limited to one listing.",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Separator(party).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(12, 8)
        )
        ttk.Label(party, text="Automatic eligible shares:").grid(
            row=5, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Entry(
            party, textvariable=self.auto_party_count_var, width=10
        ).grid(row=5, column=1, sticky="w", pady=4)
        auto_actions = ttk.Frame(party)
        auto_actions.grid(row=5, column=2, sticky="e", pady=4)
        self.preview_auto_party_button = ttk.Button(
            auto_actions,
            text="Preview Eligible",
            command=self.preview_auto_party,
        )
        self.preview_auto_party_button.pack(side="left")
        self.share_auto_party_button = ttk.Button(
            auto_actions,
            text="Share Previewed",
            command=self.share_auto_party,
        )
        self.share_auto_party_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            party,
            text=(
                "Automatically discovers the live party, applies Available + Active "
                "filters, verifies eligibility, and requires a fresh preview."
            ),
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))

        community = ttk.LabelFrame(self, text="Community Sharing", padding=12)
        community.pack(fill="x", pady=(12, 0))
        community.columnconfigure(1, weight=1)
        ttk.Label(community, text="Other seller's closet URL:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(community, textvariable=self.community_closet_url_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=4,
        )
        ttk.Label(community, text="Maximum shares:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(community, textvariable=self.community_count_var, width=10).grid(
            row=1, column=1, sticky="w", pady=4,
        )
        self.validate_community_button = ttk.Button(
            community,
            text="Validate Listings",
            command=self.validate_community_listings,
        )
        self.validate_community_button.grid(row=1, column=2, padx=(12, 8), pady=4)
        self.share_community_button = ttk.Button(
            community,
            text="Share Community Listings",
            command=self.share_community_listings,
        )
        self.share_community_button.grid(row=1, column=3, sticky="e", pady=4)
        ttk.Label(
            community,
            text="Validation is read-only. Live runs require confirmation and only use unique listings from another closet.",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        follow_backs = ttk.LabelFrame(self, text="Follow Backs", padding=12)
        follow_backs.pack(fill="x", pady=(12, 0))
        ttk.Label(follow_backs, text="Maximum follow-backs:").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        ttk.Entry(
            follow_backs,
            textvariable=self.follow_back_count_var,
            width=10,
        ).grid(row=0, column=1, sticky="w", pady=4)
        self.validate_follow_backs_button = ttk.Button(
            follow_backs,
            text="Validate Candidates",
            command=self.validate_follow_backs,
        )
        self.validate_follow_backs_button.grid(row=0, column=2, padx=(12, 8), pady=4)
        self.run_follow_backs_button = ttk.Button(
            follow_backs,
            text="Follow Back",
            command=self.start_follow_backs,
        )
        self.run_follow_backs_button.grid(row=0, column=3, pady=4)
        ttk.Label(
            follow_backs,
            text="Only followers with an exact Follow control are candidates. Existing Following accounts are never clicked.",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        try:
            count = int(self.count_var.get().strip())
            delay = float(self.delay_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Count must be whole and delay numeric.")
            return

        if count < 1 or count > MAX_FOLLOWER_SHARES_PER_RUN or delay < 0:
            messagebox.showerror(
                "Invalid Settings",
                f"Count must be 1-{MAX_FOLLOWER_SHARES_PER_RUN} and delay cannot be negative.",
            )
            return

        if not messagebox.askyesno(
            "Confirm Follower Sharing",
            f"Share up to {count} listing(s) to your followers?",
        ):
            return

        self._reset_progress()
        self._set_running(True)
        config = ShareConfig(
            closet_url=DESTINATION_CLOSET_URL,
            delay_seconds=delay,
            max_shares=count,
            share_to_parties=False,
            share_to_posh_shows=False,
        )
        self._thread = threading.Thread(
            target=self._run_worker,
            args=(config,),
            daemon=True,
        )
        self._thread.start()

    def _run_worker(self, config: ShareConfig) -> None:
        try:
            result = run_follower_sharing(
                config,
                progress_callback=lambda value: self._events.put(("progress", value)),
                engine_callback=lambda value: self._events.put(("engine", value)),
            )
            self._events.put(("result", result))
        except Exception as error:
            self._events.put(("error", str(error)))

    def validate_community_listings(self) -> None:
        self._start_community_sharing(perform_share=False)

    def share_community_listings(self) -> None:
        self._start_community_sharing(perform_share=True)

    def _start_community_sharing(self, *, perform_share: bool) -> None:
        if self.is_running:
            return
        closet_url = self.community_closet_url_var.get().strip()
        try:
            count = int(self.community_count_var.get().strip())
            delay = float(self.delay_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Count must be whole and delay numeric.")
            return
        if not closet_url or count < 1 or count > 50 or delay < 0:
            messagebox.showerror(
                "Invalid Community Settings",
                "Enter another seller's closet URL, a count from 1 to 50, and a non-negative delay.",
            )
            return
        if perform_share and not messagebox.askyesno(
            "Confirm Community Sharing",
            f"Share up to {count} unique listing(s) from this closet to your followers?\n\n{closet_url}",
        ):
            return

        self._reset_progress()
        self._set_running(True)
        self.status_var.set(
            "Sharing community listings" if perform_share else "Validating community listings"
        )
        config = ShareConfig(
            closet_url=closet_url,
            delay_seconds=delay,
            max_shares=count,
            share_community_listings=perform_share,
            community_share_limit=count,
        )
        self._thread = threading.Thread(
            target=self._run_community_worker,
            args=(config, perform_share),
            daemon=True,
        )
        self._thread.start()

    def _run_community_worker(
        self,
        config: ShareConfig,
        perform_share: bool,
    ) -> None:
        try:
            result = run_community_sharing(
                config,
                DESTINATION_CLOSET_URL,
                perform_share=perform_share,
                progress_callback=lambda value: self._events.put(("progress", value)),
                engine_callback=lambda value: self._events.put(("engine", value)),
            )
            self._events.put(("community_result", (perform_share, result)))
        except Exception as error:
            self._events.put(("error", str(error)))

    def validate_follow_backs(self) -> None:
        self._start_follow_backs(perform_follow=False)

    def start_follow_backs(self) -> None:
        self._start_follow_backs(perform_follow=True)

    def _start_follow_backs(self, *, perform_follow: bool) -> None:
        if self.is_running:
            return
        try:
            count = int(self.follow_back_count_var.get().strip())
            delay = float(self.delay_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Count must be whole and delay numeric.")
            return
        if count < 1 or count > 50 or delay < 0:
            messagebox.showerror(
                "Invalid Follow-Back Settings",
                "Count must be 1–50 and delay cannot be negative.",
            )
            return
        if perform_follow and not messagebox.askyesno(
            "Confirm Follow Backs",
            f"Follow back up to {count} confirmed follower(s)?",
        ):
            return

        self._reset_progress()
        self._set_running(True)
        self.status_var.set("Following back" if perform_follow else "Validating followers")
        config = ShareConfig(
            closet_url=DESTINATION_CLOSET_URL,
            delay_seconds=delay,
            follow_backs_enabled=perform_follow,
            follow_back_limit=count,
        )
        self._thread = threading.Thread(
            target=self._run_follow_back_worker,
            args=(config, perform_follow),
            daemon=True,
        )
        self._thread.start()

    def _run_follow_back_worker(
        self,
        config: ShareConfig,
        perform_follow: bool,
    ) -> None:
        try:
            result = run_follow_backs(
                config,
                "dveshop",
                perform_follow=perform_follow,
                progress_callback=lambda value: self._events.put(("progress", value)),
                engine_callback=lambda value: self._events.put(("engine", value)),
            )
            self._events.put(("follow_back_result", (perform_follow, result)))
        except Exception as error:
            self._events.put(("error", str(error)))

    def validate_party_candidate(self) -> None:
        self._start_party_candidate(perform_share=False)

    def preview_auto_party(self) -> None:
        self._start_auto_party(perform_share=False)

    def share_auto_party(self) -> None:
        self._start_auto_party(perform_share=True)

    def _start_auto_party(self, *, perform_share: bool) -> None:
        if self.is_running:
            return
        try:
            count = int(self.auto_party_count_var.get().strip())
            delay = float(self.delay_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Invalid Party Settings",
                "Count must be whole and delay numeric.",
            )
            return
        if count < 1 or count > MAX_AUTOMATIC_PARTY_SHARES or delay < 0:
            messagebox.showerror(
                "Invalid Party Settings",
                f"Count must be 1-{MAX_AUTOMATIC_PARTY_SHARES} and delay cannot be negative.",
            )
            return
        if perform_share:
            preview = self._auto_party_preview
            if preview is None or preview[2] != count:
                messagebox.showwarning(
                    "Fresh Preview Required",
                    "Preview eligible live-party listings for this count first.",
                )
                return
            party_name, eligible_count, _preview_count = preview
            if not messagebox.askyesno(
                "Confirm Automatic Party Sharing",
                f"Share up to {eligible_count} reverified listing(s) to {party_name}?",
            ):
                return
            run_count = min(count, eligible_count)
            expected_party_name = party_name
        else:
            self._auto_party_preview = None
            run_count = count
            expected_party_name = None

        self._reset_progress()
        self._set_running(True)
        self.status_var.set(
            "Sharing eligible live-party listings"
            if perform_share
            else "Previewing live-party eligibility"
        )
        self._thread = threading.Thread(
            target=self._run_auto_party_worker,
            args=(run_count, delay, perform_share, expected_party_name),
            daemon=True,
        )
        self._thread.start()

    def _run_auto_party_worker(
        self,
        count: int,
        delay: float,
        perform_share: bool,
        expected_party_name: str | None,
    ) -> None:
        try:
            result = run_live_party_batch(
                count,
                delay_seconds=delay,
                perform_share=perform_share,
                expected_party_name=expected_party_name,
                progress_callback=lambda value: self._events.put(("progress", value)),
                engine_callback=lambda value: self._events.put(("engine", value)),
            )
            self._events.put(
                ("auto_party_result", (perform_share, count, result))
            )
        except Exception as error:
            self._events.put(("error", str(error)))

    def share_party_candidate(self) -> None:
        self._start_party_candidate(perform_share=True)

    def _start_party_candidate(self, *, perform_share: bool) -> None:
        if self.is_running:
            return
        party_name = self.party_name_var.get().strip()
        listing_url = self.party_listing_url_var.get().strip()
        if not party_name or not listing_url:
            messagebox.showerror(
                "Missing Party Details",
                "Enter the exact live party name and destination listing URL.",
            )
            return
        if perform_share and not messagebox.askyesno(
            "Confirm One Party Share",
            f"Share exactly one listing to {party_name}?",
        ):
            return

        self._set_running(True)
        self.status_var.set("Validating live party candidate")
        self._thread = threading.Thread(
            target=self._run_party_worker,
            args=(listing_url, party_name, perform_share),
            daemon=True,
        )
        self._thread.start()

    def _run_party_worker(
        self,
        listing_url: str,
        party_name: str,
        perform_share: bool,
    ) -> None:
        try:
            result = run_party_candidate(
                listing_url,
                party_name,
                perform_share=perform_share,
                engine_callback=lambda value: self._events.put(("engine", value)),
            )
            self._events.put(("party_result", (perform_share, result)))
        except Exception as error:
            self._events.put(("error", str(error)))

    def _poll_events(self) -> None:
        try:
            while True:
                event, value = self._events.get_nowait()
                if event == "engine":
                    self._engine = value  # type: ignore[assignment]
                elif event == "progress":
                    self._apply_progress(value)  # type: ignore[arg-type]
                elif event == "result":
                    self._finish(value)  # type: ignore[arg-type]
                elif event == "party_result":
                    perform_share, result = value  # type: ignore[misc]
                    self._finish_party(bool(perform_share), result)
                elif event == "auto_party_result":
                    perform_share, count, result = value  # type: ignore[misc]
                    self._finish_auto_party(
                        bool(perform_share), int(count), result
                    )
                elif event == "community_result":
                    perform_share, result = value  # type: ignore[misc]
                    self._finish_community(bool(perform_share), result)
                elif event == "follow_back_result":
                    perform_follow, result = value  # type: ignore[misc]
                    self._finish_follow_backs(bool(perform_follow), result)
                elif event == "error":
                    self._append(f"ERROR: {value}")
                    self.status_var.set("Failed")
                    self._set_running(False)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_events)

    def _apply_progress(self, progress: ShareProgress) -> None:
        percent = (progress.current / progress.total * 100) if progress.total else 0.0
        self.progress_var.set(percent)
        self.progress_text_var.set(
            f"{progress.current} / {progress.total} ({percent:.0f}%)"
        )
        self.status_var.set(progress.status.display_label)
        self.shared_var.set(str(progress.shared))
        self.skipped_var.set(str(progress.skipped))
        self.failed_var.set(str(progress.failed))
        self.eta_var.set(
            "—" if progress.eta_seconds is None else f"{progress.eta_seconds:.0f}s"
        )
        listing = f" — {progress.listing_title}" if progress.listing_title else ""
        self._append(f"{percent:.0f}% {progress.message}{listing}")
        if progress.status == ShareStatus.PAUSED:
            self.pause_button.configure(state="disabled")
            self.resume_button.configure(state="normal")

    def _finish(self, result: ShareResult) -> None:
        self._append(
            f"Finished: shared={result.shared}, skipped={result.skipped}, failed={result.failed}"
        )
        self.status_var.set("Complete" if result.success else "Stopped / Failed")
        self._set_running(False)
        self._engine = None

    def _finish_party(self, performed_share: bool, result: ShareResult) -> None:
        action = "Party share" if performed_share else "Party validation"
        self._append(f"{action}: {result.message}")
        self.status_var.set("Complete" if result.success else "Failed")
        if result.success:
            self.progress_var.set(100.0)
            self.progress_text_var.set("1 / 1 (100%)")
            if performed_share:
                self.shared_var.set(str(result.shared))
        else:
            self.failed_var.set(str(result.failed))
        self._set_running(False)
        self._engine = None

    def _finish_auto_party(
        self,
        performed_share: bool,
        requested_count: int,
        result: ShareResult,
    ) -> None:
        action = "Automatic party sharing" if performed_share else "Party preview"
        self._append(f"{action}: {result.message}")
        self.status_var.set("Complete" if result.success else "Failed")
        if result.success and not performed_share:
            self._auto_party_preview = (
                result.party_name or "Live Posh Party",
                result.skipped,
                requested_count,
            )
            self.progress_var.set(100.0)
            self.progress_text_var.set(f"{result.skipped} eligible candidate(s)")
        elif performed_share:
            self._auto_party_preview = None
            self.shared_var.set(str(result.shared))
            self.skipped_var.set(str(result.skipped))
            self.failed_var.set(str(result.failed))
        self._set_running(False)
        self._engine = None

    def _finish_community(self, performed_share: bool, result: ShareResult) -> None:
        action = "Community sharing" if performed_share else "Community validation"
        self._append(f"{action}: {result.message}")
        self.status_var.set("Complete" if result.success else "Failed")
        if result.success and not performed_share:
            self.progress_var.set(100.0)
            self.progress_text_var.set(f"{result.skipped} candidate(s) validated")
        self._set_running(False)
        self._engine = None

    def _finish_follow_backs(self, performed_follow: bool, result: ShareResult) -> None:
        action = "Follow-backs" if performed_follow else "Follow-back validation"
        self._append(f"{action}: {result.message}")
        self.status_var.set("Complete" if result.success else "Failed")
        if result.success and not performed_follow:
            self.progress_var.set(100.0)
            self.progress_text_var.set(f"{result.skipped} candidate(s) validated")
        self._set_running(False)
        self._engine = None

    def pause(self) -> None:
        if self._engine is not None:
            self._engine.pause()

    def resume(self) -> None:
        if self._engine is not None:
            self._engine.resume()
            self.pause_button.configure(state="normal")
            self.resume_button.configure(state="disabled")

    def stop_after_current(self) -> None:
        if self._engine is not None:
            self._engine.request_stop_after_current()
            self.status_var.set("Stopping after current share")

    def shutdown(self) -> None:
        """Request a graceful stop when the dashboard closes."""
        if self._engine is not None:
            self._engine.request_stop_after_current()

    @property
    def is_running(self) -> bool:
        """Return whether a sharing worker is currently active."""
        return self._thread is not None and self._thread.is_alive()

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(state="normal" if running else "disabled")
        self.resume_button.configure(state="disabled")
        self.stop_button.configure(state="normal" if running else "disabled")
        party_state = "disabled" if running else "normal"
        self.validate_party_button.configure(state=party_state)
        self.share_party_button.configure(state=party_state)
        self.preview_auto_party_button.configure(state=party_state)
        self.share_auto_party_button.configure(state=party_state)
        self.validate_community_button.configure(state=party_state)
        self.share_community_button.configure(state=party_state)
        self.validate_follow_backs_button.configure(state=party_state)
        self.run_follow_backs_button.configure(state=party_state)

    def _reset_progress(self) -> None:
        self.progress_var.set(0.0)
        self.progress_text_var.set("0 / 0 (0%)")
        self.status_var.set("Starting")
        self.shared_var.set("0")
        self.skipped_var.set("0")
        self.failed_var.set("0")
        self.eta_var.set("—")

    def _append(self, message: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")
