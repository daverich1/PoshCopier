from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from inventory.upload_queue import QueueStatus, UploadQueueManager
from inventory.batch_report import save_batch_report
from pipeline.upload_queue_processor import ProcessResult, UploadQueueProcessor


class ProcessorState:
    """Processor state enumeration."""
    IDLE = "Idle"
    RUNNING = "Running"
    STOP_REQUESTED = "Stop Requested"
    COMPLETE = "Complete"


class UploadQueuePanel(ttk.LabelFrame):
    """Upload queue panel with batch processing capabilities."""
    
    def __init__(
        self,
        parent: tk.Misc,
        mode_var: tk.StringVar | None = None,
    ) -> None:
        super().__init__(
            parent,
            text="Upload Queue",
            padding=10,
        )
        
        self.queue_manager = UploadQueueManager()
        self.mode_var = mode_var  # Reference to dashboard's mode radio button
        
        # Processor state
        self._processor_state = ProcessorState.IDLE
        self._worker_thread: threading.Thread | None = None
        self._processor: UploadQueueProcessor | None = None
        self._current_listing = ""
        self._current_progress = ""
        self._last_result = ""
        
        # Summary variables
        self.total_var = tk.StringVar(value="0")
        self.waiting_var = tk.StringVar(value="0")
        self.pending_var = tk.StringVar(value="0")
        self.running_var = tk.StringVar(value="0")
        self.uploaded_var = tk.StringVar(value="0")
        self.already_exists_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.skipped_var = tk.StringVar(value="0")
        self.remaining_var = tk.StringVar(value="0")
        self.percent_var = tk.StringVar(value="0%")
        
        # Status variables
        self.processor_state_var = tk.StringVar(value=ProcessorState.IDLE)
        self.current_listing_var = tk.StringVar(value="—")
        self.current_progress_var = tk.StringVar(value="—")
        self.last_result_var = tk.StringVar(value="—")
        
        self._build_interface()
        self.refresh()
    
    def _build_interface(self) -> None:
        """Build the panel UI."""
        # Configure main panel grid weights
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)  # Treeview row expands
        
        # Configure Treeview style for increased row height
        style = ttk.Style()
        style.configure("UploadQueue.Treeview", rowheight=28)
        
        # Summary section
        summary_frame = ttk.LabelFrame(
            self,
            text="Queue Summary",
            padding=10,
        )
        summary_frame.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        
        # Summary grid layout with better spacing
        summary_grid = ttk.Frame(summary_frame)
        summary_grid.pack(fill="x", expand=True)
        
        # Row 0 - First 4 statistics
        self._add_summary_stat(summary_grid, 0, 0, "Total:", self.total_var)
        self._add_summary_stat(summary_grid, 0, 2, "Waiting:", self.waiting_var)
        self._add_summary_stat(summary_grid, 0, 4, "Pending:", self.pending_var)
        self._add_summary_stat(summary_grid, 0, 6, "Running:", self.running_var)
        
        # Row 1 - Next 4 statistics
        self._add_summary_stat(summary_grid, 1, 0, "Uploaded:", self.uploaded_var)
        self._add_summary_stat(summary_grid, 1, 2, "Already Exists:", self.already_exists_var)
        self._add_summary_stat(summary_grid, 1, 4, "Failed:", self.failed_var)
        self._add_summary_stat(summary_grid, 1, 6, "Skipped:", self.skipped_var)
        
        # Row 2 - Last 2 statistics
        self._add_summary_stat(summary_grid, 2, 0, "Remaining:", self.remaining_var)
        self._add_summary_stat(summary_grid, 2, 2, "Percent:", self.percent_var)
        
        # Progress bar section with full width
        progress_frame = ttk.Frame(summary_frame)
        progress_frame.pack(fill="x", expand=True, pady=(10, 0))
        
        # Progress label
        ttk.Label(
            progress_frame,
            text="Progress:",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 8))
        
        # Progress bar - expands to fill width
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            maximum=100,
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        # Percent label on the right
        self.percent_label = ttk.Label(
            progress_frame,
            textvariable=self.percent_var,
            font=("Segoe UI", 9, "bold"),
            width=6,
        )
        self.percent_label.pack(side="left")
        
        # Status section
        status_frame = ttk.LabelFrame(
            self,
            text="Processor Status",
            padding=10,
        )
        status_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        
        status_grid = ttk.Frame(status_frame)
        status_grid.pack(fill="x", expand=True)
        
        # Status row 0
        self._add_summary_stat(status_grid, 0, 0, "State:", self.processor_state_var)
        self._add_summary_stat(status_grid, 0, 2, "Current Listing:", self.current_listing_var)
        
        # Status row 1
        self._add_summary_stat(status_grid, 1, 0, "Progress:", self.current_progress_var)
        self._add_summary_stat(status_grid, 1, 2, "Last Result:", self.last_result_var)
        
        # Actions section
        actions_frame = ttk.Frame(self)
        actions_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        
        self.start_queue_button = ttk.Button(
            actions_frame,
            text="Start Queue",
            command=self._start_queue,
        )
        self.start_queue_button.pack(side="left", padx=(0, 8))
        
        self.stop_queue_button = ttk.Button(
            actions_frame,
            text="Stop After Current",
            command=self._stop_queue,
            state="disabled",
        )
        self.stop_queue_button.pack(side="left", padx=(0, 8))
        
        self.refresh_button = ttk.Button(
            actions_frame,
            text="Refresh",
            command=self.refresh,
        )
        self.refresh_button.pack(side="left", padx=(0, 8))
        
        self.clear_completed_button = ttk.Button(
            actions_frame,
            text="Clear Completed",
            command=self._clear_completed,
        )
        self.clear_completed_button.pack(side="left", padx=(0, 8))
        
        self.reset_failed_button = ttk.Button(
            actions_frame,
            text="Reset Failed",
            command=self._reset_failed,
        )
        self.reset_failed_button.pack(side="left")
        
        # Output window section
        output_frame = ttk.LabelFrame(
            self,
            text="Processing Output",
            padding=10,
        )
        output_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        
        # Output text widget with scrollbar
        output_container = ttk.Frame(output_frame)
        output_container.pack(fill="both", expand=True)
        
        self.output_text = tk.Text(
            output_container,
            height=8,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self.output_text.pack(side="left", fill="both", expand=True)
        
        output_scrollbar = ttk.Scrollbar(
            output_container,
            orient="vertical",
            command=self.output_text.yview,
        )
        output_scrollbar.pack(side="right", fill="y")
        self.output_text.configure(yscrollcommand=output_scrollbar.set)
        
        # Empty state message
        self.empty_label = ttk.Label(
            self,
            text="No upload queue has been created yet.\n\nUse the Inventory tab to add listings to the queue.",
            justify="center",
            font=("Segoe UI", 10),
        )
        
        # Treeview section with both scrollbars
        tree_frame = ttk.Frame(self)
        tree_frame.grid(
            row=5,
            column=0,
            sticky="nsew",
        )
        
        # Configure tree frame grid weights
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        columns = (
            "title",
            "listing_id",
            "status",
            "attempts",
            "duration",
            "last_error",
        )
        
        # Treeview with custom style for row height
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="UploadQueue.Treeview",
        )
        
        self.tree.heading("title", text="Title")
        self.tree.heading("listing_id", text="Listing ID")
        self.tree.heading("status", text="Status")
        self.tree.heading("attempts", text="Attempts")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("last_error", text="Last Error")
        
        self.tree.column("title", width=300, anchor="w")
        self.tree.column("listing_id", width=100, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("attempts", width=80, anchor="center")
        self.tree.column("duration", width=90, anchor="center")
        self.tree.column("last_error", width=250, anchor="w")
        
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 0), pady=(0, 0))
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(
            tree_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=h_scrollbar.set)
    
    def _add_summary_stat(
        self,
        parent: ttk.Frame,
        row: int,
        col: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        """Add a summary statistic label and value with improved spacing."""
        ttk.Label(
            parent,
            text=label,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=row, column=col, sticky="w", padx=(0, 4), pady=4)
        
        ttk.Label(
            parent,
            textvariable=variable,
        ).grid(row=row, column=col + 1, sticky="w", padx=(0, 20), pady=4)
    
    def refresh(self) -> None:
        """Reload queue state and update display."""
        # Load queue from disk
        state = self.queue_manager.load()
        
        if state is None or len(state.entries) == 0:
            self._show_empty_state()
            return
        
        self._hide_empty_state()
        
        # Update summary
        summary = self.queue_manager.progress_summary()
        
        self.total_var.set(str(summary["total"]))
        self.waiting_var.set(str(summary["waiting"]))
        self.pending_var.set(str(summary["pending"]))
        self.running_var.set(str(summary["running"]))
        self.uploaded_var.set(str(summary["uploaded"]))
        self.already_exists_var.set(str(summary["already_exists"]))
        self.failed_var.set(str(summary["failed"]))
        self.skipped_var.set(str(summary["skipped"]))
        self.remaining_var.set(str(summary["remaining"]))
        self.percent_var.set(f"{summary['percent']:.1f}%")
        
        # Update progress bar
        self.progress_bar["value"] = summary["percent"]
        
        # Update treeview
        self._populate_tree()
        
        # Update button states
        self._update_button_states()
    
    def _populate_tree(self) -> None:
        """Populate the treeview with queue entries."""
        # Clear existing items
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        
        state = self.queue_manager.state
        
        if state is None:
            return
        
        # Add entries
        for entry in state.entries:
            self.tree.insert(
                "",
                "end",
                values=(
                    self._truncate(entry.title, 40),
                    self._format_listing_id(entry.listing_id),
                    self._format_status(entry.status),
                    str(entry.attempt_count),
                    self._format_duration(entry.duration_seconds),
                    self._truncate(entry.last_error, 35),
                ),
            )
    
    def _show_empty_state(self) -> None:
        """Show empty state message and hide tree."""
        self.empty_label.grid(row=4, column=0, pady=20)
        self.tree.grid_remove()
        
        # Reset summary
        self.total_var.set("0")
        self.waiting_var.set("0")
        self.pending_var.set("0")
        self.running_var.set("0")
        self.uploaded_var.set("0")
        self.already_exists_var.set("0")
        self.failed_var.set("0")
        self.skipped_var.set("0")
        self.remaining_var.set("0")
        self.percent_var.set("0%")
        self.progress_bar["value"] = 0
        
        # Disable buttons
        self.start_queue_button.configure(state="disabled")
        self.clear_completed_button.configure(state="disabled")
        self.reset_failed_button.configure(state="disabled")
    
    def _hide_empty_state(self) -> None:
        """Hide empty state message and show tree."""
        self.empty_label.grid_remove()
        self.tree.grid()
    
    def _update_button_states(self) -> None:
        """Update button enabled/disabled states."""
        state = self.queue_manager.state
        
        if state is None or len(state.entries) == 0:
            self.start_queue_button.configure(state="disabled")
            self.clear_completed_button.configure(state="disabled")
            self.reset_failed_button.configure(state="disabled")
            return
        
        # Check if processing
        is_processing = self._processor_state == ProcessorState.RUNNING
        
        if is_processing:
            # During processing
            self.start_queue_button.configure(state="disabled")
            self.stop_queue_button.configure(state="normal")
            self.refresh_button.configure(state="disabled")
            self.clear_completed_button.configure(state="disabled")
            self.reset_failed_button.configure(state="disabled")
        else:
            # Not processing
            self.stop_queue_button.configure(state="disabled")
            self.refresh_button.configure(state="normal")
            
            # Check if there are eligible entries for starting
            has_eligible = any(
                entry.status in (QueueStatus.WAITING, QueueStatus.PENDING)
                for entry in state.entries
            )
            
            self.start_queue_button.configure(
                state="normal" if has_eligible else "disabled"
            )
            
            # Check if there are completed entries
            has_completed = any(
                entry.status in (
                    QueueStatus.UPLOADED,
                    QueueStatus.ALREADY_EXISTS,
                    QueueStatus.SKIPPED,
                )
                for entry in state.entries
            )
            
            # Check if there are failed entries
            has_failed = any(
                entry.status == QueueStatus.FAILED
                for entry in state.entries
            )
            
            self.clear_completed_button.configure(
                state="normal" if has_completed else "disabled"
            )
            self.reset_failed_button.configure(
                state="normal" if has_failed else "disabled"
            )
    
    def _start_queue(self) -> None:
        """Start queue processing."""
        # Reload queue from disk
        state = self.queue_manager.load()
        
        if state is None:
            messagebox.showerror(
                "No Queue",
                "No upload queue found. Please add items to the queue first.",
            )
            return
        
        # Check if already running
        if self._processor_state == ProcessorState.RUNNING:
            messagebox.showwarning(
                "Already Running",
                "Queue processor is already running.",
            )
            return
        
        # Check for eligible entries
        eligible_entries = [
            entry for entry in state.entries
            if entry.status in (QueueStatus.WAITING, QueueStatus.PENDING)
        ]
        
        if not eligible_entries:
            messagebox.showinfo(
                "No Eligible Entries",
                "No entries are waiting or pending.\n\n"
                "All entries have already been processed or are in a terminal state.",
            )
            return
        
        # Synchronize queue mode with dashboard radio button
        if self.mode_var is not None:
            dashboard_mode = self.mode_var.get()
            if dashboard_mode in ("dry_run", "publish"):
                # Update queue state to match dashboard
                state.mode = dashboard_mode
                self.queue_manager.save()
        
        mode = state.mode
        
        # Different confirmation flows for dry_run vs publish
        if mode == "publish":
            # Live Publish requires explicit confirmation
            confirm_msg = (
                "Live Publish Confirmation\n\n"
                "You are about to publish listings to the destination Poshmark closet.\n\n"
                "This action will create live listings.\n\n"
                f"Queue items ready to process: {len(eligible_entries)}\n\n"
                "Continue with Live Publish?"
            )
            
            confirmed = messagebox.askyesno(
                "Live Publish Confirmation",
                confirm_msg,
                icon="warning",
            )
            
            if not confirmed:
                return
        else:
            # Dry Run mode - simple confirmation
            confirm_msg = (
                f"Start Dry Run processing for {len(eligible_entries)} entries?\n\n"
                f"Retry count: {state.retry_count}\n"
                f"Retry delay: {state.retry_delay}s\n\n"
                "Dry Run will NOT create live listings."
            )
            
            confirmed = messagebox.askyesno(
                "Start Dry Run",
                confirm_msg,
            )
            
            if not confirmed:
                return
        
        # Clear stop request flag
        self.queue_manager.reset_stop_request()
        
        # Clear output window
        self._clear_output()
        
        # Update state
        self._processor_state = ProcessorState.RUNNING
        self.processor_state_var.set(ProcessorState.RUNNING)
        self._current_listing = ""
        self._current_progress = ""
        self._last_result = ""
        self.current_listing_var.set("—")
        self.current_progress_var.set("—")
        self.last_result_var.set("—")
        
        # Update button states
        self._update_button_states()
        
        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._run_processor_thread,
            daemon=True,
        )
        self._worker_thread.start()
        
        # Append start message
        self._append_output(f"=== Queue Processing Started ===")
        self._append_output(f"Mode: {mode_display}")
        self._append_output(f"Entries to process: {len(eligible_entries)}")
        self._append_output("")
    
    def _stop_queue(self) -> None:
        """Request queue processing to stop after current listing."""
        if self._processor_state != ProcessorState.RUNNING:
            return
        
        # Request stop
        try:
            self.queue_manager.request_stop()
        except RuntimeError:
            messagebox.showerror(
                "Error",
                "Failed to request stop: No queue state loaded.",
            )
            return
        
        # Update state
        self._processor_state = ProcessorState.STOP_REQUESTED
        self.processor_state_var.set("Stop requested — finishing current listing...")
        
        # Append message
        self._append_output("")
        self._append_output("=== Stop Requested ===")
        self._append_output("Finishing current listing...")
        self._append_output("")
    
    def _run_processor_thread(self) -> None:
        """Worker thread function to run the processor."""
        try:
            # Create processor with callbacks
            self._processor = UploadQueueProcessor(
                queue_manager=self.queue_manager,
                progress_callback=self._on_progress,
                output_callback=self._on_output,
                completion_callback=self._on_completion,
            )
            
            # Process queue (blocking)
            results = self._processor.process_queue()
            
            # Processing complete
            self.after(0, self._on_processing_complete, results)
            
        except Exception as e:
            # Handle unexpected errors
            self.after(0, self._on_processing_error, str(e))
    
    def _on_progress(self, current: int, total: int) -> None:
        """Progress callback (called from worker thread)."""
        progress_text = f"{current}/{total}"
        self.after(0, self._update_progress, progress_text)
    
    def _on_output(self, line: str) -> None:
        """Output callback (called from worker thread)."""
        self.after(0, self._append_output, line)
    
    def _on_completion(self, result: ProcessResult) -> None:
        """Completion callback (called from worker thread)."""
        self.after(0, self._update_completion, result)
    
    def _update_progress(self, progress_text: str) -> None:
        """Update progress display (called on main thread)."""
        self._current_progress = progress_text
        self.current_progress_var.set(progress_text)
    
    def _append_output(self, line: str) -> None:
        """Append line to output window (called on main thread)."""
        self.output_text.configure(state="normal")
        self.output_text.insert("end", line + "\n")
        self.output_text.configure(state="disabled")
        self.output_text.see("end")  # Auto-scroll
    
    def _clear_output(self) -> None:
        """Clear output window."""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")
    
    def _update_completion(self, result: ProcessResult) -> None:
        """Update completion display (called on main thread)."""
        # Update current listing
        self._current_listing = result.listing_id
        self.current_listing_var.set(self._format_listing_id(result.listing_id))
        
        # Update last result
        status_display = self._format_status(result.status)
        self._last_result = f"{status_display}: {result.message}"
        self.last_result_var.set(self._truncate(self._last_result, 50))
        
        # Refresh summary and tree
        self.refresh()
    
    def _on_processing_complete(self, results: list[ProcessResult]) -> None:
        """Handle processing completion (called on main thread)."""
        # Update state
        self._processor_state = ProcessorState.COMPLETE
        self.processor_state_var.set(ProcessorState.COMPLETE)
        
        # Reload queue
        self.queue_manager.load()
        
        # Refresh display
        self.refresh()
        
        # Update button states
        self._update_button_states()
        
        # Append completion message
        self._append_output("")
        self._append_output("=== Queue Processing Complete ===")
        self._append_output(f"Total processed: {len(results)}")
        self._append_output("")
        
        # Calculate statistics from current run
        run_uploaded = sum(1 for r in results if r.status == QueueStatus.UPLOADED)
        run_already_exists = sum(1 for r in results if r.status == QueueStatus.ALREADY_EXISTS)
        run_skipped = sum(1 for r in results if r.status == QueueStatus.SKIPPED)
        run_failed = sum(1 for r in results if r.status == QueueStatus.FAILED)
        run_publish_unverified = sum(1 for r in results if r.status == QueueStatus.PUBLISH_UNVERIFIED)
        run_cancelled = sum(1 for r in results if r.status == QueueStatus.CANCELLED)
        
        # Get cumulative queue summary for remaining count
        summary = self.queue_manager.progress_summary()

        try:
            _, report_path = save_batch_report(results, summary)
            self._append_output(f"Completion report: {report_path}")
        except OSError as exc:
            self._append_output(f"Warning: could not save completion report: {exc}")
        
        # Show completion dialog with current-run statistics
        completion_msg = (
            f"Queue processing complete!\n\n"
            f"Processed this run: {len(results)}\n"
            f"Uploaded: {run_uploaded}\n"
            f"Already Exists: {run_already_exists}\n"
            f"Skipped: {run_skipped}\n"
            f"Failed: {run_failed}\n"
            f"Publish Unverified: {run_publish_unverified}\n"
            f"Cancelled: {run_cancelled}\n\n"
            f"Queue remaining: {summary['remaining']}"
        )
        
        messagebox.showinfo(
            "Processing Complete",
            completion_msg,
        )
        
        # Reset state to idle
        self._processor_state = ProcessorState.IDLE
        self.processor_state_var.set(ProcessorState.IDLE)
        self._processor = None
        self._worker_thread = None
    
    def _on_processing_error(self, error_msg: str) -> None:
        """Handle processing error (called on main thread)."""
        # Update state
        self._processor_state = ProcessorState.IDLE
        self.processor_state_var.set(ProcessorState.IDLE)
        
        # Append error message
        self._append_output("")
        self._append_output(f"=== ERROR ===")
        self._append_output(error_msg)
        self._append_output("")
        
        # Reload and refresh
        self.queue_manager.load()
        self.refresh()
        
        # Update button states
        self._update_button_states()
        
        # Show error dialog
        messagebox.showerror(
            "Processing Error",
            f"An error occurred during processing:\n\n{error_msg}",
        )
        
        # Reset state
        self._processor = None
        self._worker_thread = None
    
    def _clear_completed(self) -> None:
        """Remove completed entries from the queue."""
        state = self.queue_manager.state
        
        if state is None:
            return
        
        # Count entries to remove
        completed_statuses = (
            QueueStatus.UPLOADED,
            QueueStatus.ALREADY_EXISTS,
            QueueStatus.SKIPPED,
        )
        
        to_remove = [
            entry for entry in state.entries
            if entry.status in completed_statuses
        ]
        
        if not to_remove:
            messagebox.showinfo(
                "No Completed Entries",
                "There are no completed entries to clear.",
            )
            return
        
        # Confirm removal
        confirmed = messagebox.askyesno(
            "Clear Completed",
            f"Remove {len(to_remove)} completed entries?\n\n"
            "This will remove entries with status:\n"
            "• UPLOADED\n"
            "• ALREADY_EXISTS\n"
            "• SKIPPED",
        )
        
        if not confirmed:
            return
        
        # Remove completed entries
        state.entries = [
            entry for entry in state.entries
            if entry.status not in completed_statuses
        ]
        
        # Save and refresh
        self.queue_manager.save()
        self.refresh()
        
        messagebox.showinfo(
            "Completed",
            f"Removed {len(to_remove)} completed entries.",
        )
    
    def _reset_failed(self) -> None:
        """Reset all failed entries to PENDING."""
        state = self.queue_manager.state
        
        if state is None:
            return
        
        # Count failed entries
        failed_count = sum(
            1 for entry in state.entries
            if entry.status == QueueStatus.FAILED
        )
        
        if failed_count == 0:
            messagebox.showinfo(
                "No Failed Entries",
                "There are no failed entries to reset.",
            )
            return
        
        # Confirm reset
        confirmed = messagebox.askyesno(
            "Reset Failed",
            f"Reset {failed_count} failed entries to PENDING?\n\n"
            "This will clear error messages and attempt counts.",
        )
        
        if not confirmed:
            return
        
        # Reset failed entries
        reset_count = self.queue_manager.reset_failed()
        
        # Refresh display
        self.refresh()
        
        messagebox.showinfo(
            "Completed",
            f"Reset {reset_count} failed entries to PENDING.",
        )
    
    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if not text:
            return "—"
        
        if len(text) <= max_length:
            return text
        
        return text[:max_length - 1] + "…"
    
    @staticmethod
    def _format_listing_id(listing_id: str) -> str:
        """Format listing ID for display."""
        if not listing_id:
            return "—"
        
        if len(listing_id) <= 8:
            return listing_id
        
        return listing_id[:8] + "…"
    
    @staticmethod
    def _format_status(status: QueueStatus) -> str:
        """Format status for display."""
        return status.value.replace("_", " ").title()
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds <= 0:
            return "—"
        
        if seconds < 60:
            return f"{int(seconds)}s"
        
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        
        if minutes < 60:
            if remaining_seconds > 0:
                return f"{minutes}m {remaining_seconds}s"
            return f"{minutes}m"
        
        hours = int(minutes // 60)
        remaining_minutes = int(minutes % 60)
        
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"
