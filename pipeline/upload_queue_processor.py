"""
Sequential upload queue processor.

Consumes UploadQueueManager entries one at a time by reusing the existing
single-listing pipeline (run_single_listing.py).
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from inventory.upload_queue import (
    QueueEntry,
    QueueStatus,
    UploadQueueManager,
    utc_now,
)
from runtime_paths import LOGS_DIR


# ===== Logging Setup =====

QUEUE_LOG_FILE = LOGS_DIR / "upload_queue.log"


def setup_logger() -> logging.Logger:
    """Configure logger for upload queue processor."""
    logger = logging.getLogger("upload_queue_processor")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Ensure log directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # File handler
    file_handler = logging.FileHandler(
        QUEUE_LOG_FILE,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logger()


# ===== Result Dataclass =====

@dataclass
class ProcessResult:
    """Result of processing a single queue entry."""
    
    listing_id: str
    status: QueueStatus
    exit_code: int
    message: str
    started_at: str
    finished_at: str
    duration_seconds: float


# ===== Processor =====

class UploadQueueProcessor:
    """Sequential processor for upload queue entries."""
    
    def __init__(
        self,
        queue_manager: UploadQueueManager,
        progress_callback: Callable[[int, int], None] | None = None,
        output_callback: Callable[[str], None] | None = None,
        completion_callback: Callable[[ProcessResult], None] | None = None,
    ):
        """
        Initialize the upload queue processor.
        
        Args:
            queue_manager: The queue manager instance
            progress_callback: Optional callback for progress updates (current, total)
            output_callback: Optional callback for streaming subprocess output
            completion_callback: Optional callback when an entry completes
        """
        self.queue_manager = queue_manager
        self.progress_callback = progress_callback
        self.output_callback = output_callback
        self.completion_callback = completion_callback
        
        self._stop_requested = False
        self._pause_requested = False
    
    def process_queue(self) -> list[ProcessResult]:
        """
        Process all eligible entries sequentially.
        
        Returns:
            List of ProcessResult for each processed entry
        """
        if self.queue_manager.state is None:
            logger.warning("No queue state loaded")
            return []
        
        state = self.queue_manager.state
        
        # Reset stop/pause flags
        self._stop_requested = state.stop_requested
        self._pause_requested = state.paused
        
        # Get eligible entries (WAITING or PENDING)
        eligible_entries = [
            entry for entry in state.entries
            if entry.status in (QueueStatus.WAITING, QueueStatus.PENDING)
        ]
        
        if not eligible_entries:
            logger.info("No eligible entries to process")
            return []
        
        total_entries = len(eligible_entries)
        
        logger.info(f"Starting queue processing: {total_entries} entries")
        logger.info(f"Mode: {state.mode}")
        logger.info(f"Retry count: {state.retry_count}")
        logger.info(f"Retry delay: {state.retry_delay}s")
        
        results: list[ProcessResult] = []
        processed_count = 0
        
        for entry in eligible_entries:
            # Check for pause request
            if self._pause_requested or state.paused:
                logger.info("Pause requested - stopping before next entry")
                break
            
            # Check for stop request
            if self._stop_requested or state.stop_requested:
                logger.info("Stop requested - stopping before next entry")
                break
            
            # Convert WAITING to PENDING
            if entry.status == QueueStatus.WAITING:
                entry.status = QueueStatus.PENDING
                self.queue_manager.save()
            
            # Process the entry
            result = self._process_entry(entry)
            results.append(result)
            processed_count += 1
            
            # Report progress
            if self.progress_callback:
                self.progress_callback(processed_count, total_entries)
            
            # Report completion
            if self.completion_callback:
                self.completion_callback(result)
            
            # Reload state to check for external changes
            self.queue_manager.load()
            state = self.queue_manager.state
            
            if state is None:
                logger.warning("Queue state was cleared externally")
                break
            
            self._stop_requested = state.stop_requested
            self._pause_requested = state.paused
        
        logger.info(f"Queue processing complete: {processed_count}/{total_entries} entries processed")
        
        return results
    
    def _process_entry(self, entry: QueueEntry) -> ProcessResult:
        """
        Process a single queue entry.
        
        Args:
            entry: The queue entry to process
            
        Returns:
            ProcessResult with outcome
        """
        logger.info(f"Processing entry: {entry.listing_id} - {entry.title}")
        
        # Mark as RUNNING
        try:
            self.queue_manager.mark_running(entry.listing_id)
        except ValueError as e:
            logger.error(f"Failed to mark entry as running: {e}")
            # Entry might have been removed, create a failed result
            return ProcessResult(
                listing_id=entry.listing_id,
                status=QueueStatus.FAILED,
                exit_code=-1,
                message=str(e),
                started_at=utc_now(),
                finished_at=utc_now(),
                duration_seconds=0.0,
            )
        
        started_at = entry.started_at
        
        # Execute the listing
        try:
            exit_code, stdout, stderr = self._execute_listing(entry)
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            exit_code = -1
            stdout = ""
            stderr = str(e)
        
        # Parse outcome
        status, message = self._parse_outcome(exit_code, stdout, stderr)
        
        finished_at = utc_now()
        
        # Calculate duration
        duration_seconds = 0.0
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                finished = datetime.fromisoformat(finished_at)
                duration_seconds = (finished - started).total_seconds()
            except (ValueError, TypeError):
                pass
        
        # Update queue entry status
        try:
            if status == QueueStatus.UPLOADED:
                self.queue_manager.mark_uploaded(entry.listing_id)
            elif status == QueueStatus.ALREADY_EXISTS:
                self.queue_manager.mark_already_exists(entry.listing_id)
            elif status == QueueStatus.PUBLISH_UNVERIFIED:
                self.queue_manager.mark_publish_unverified(entry.listing_id, message)
            elif status == QueueStatus.SKIPPED:
                self.queue_manager.mark_skipped(entry.listing_id)
            elif status == QueueStatus.FAILED:
                self.queue_manager.mark_failed(entry.listing_id, message)
            else:
                # Unexpected status, mark as failed
                self.queue_manager.mark_failed(
                    entry.listing_id,
                    f"Unexpected status: {status}",
                )
        except ValueError as e:
            logger.error(f"Failed to update entry status: {e}")
        
        # Log result
        logger.info(
            f"Entry complete: {entry.listing_id} - "
            f"Status: {status.value} - "
            f"Duration: {duration_seconds:.1f}s - "
            f"Attempt: {entry.attempt_count}"
        )
        
        if status == QueueStatus.FAILED:
            logger.error(f"Failure message: {message}")
        
        return ProcessResult(
            listing_id=entry.listing_id,
            status=status,
            exit_code=exit_code,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
        )
    
    def _execute_listing(self, entry: QueueEntry) -> tuple[int, str, str]:
        """
        Execute single listing via subprocess.
        
        Args:
            entry: The queue entry to execute
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if self.queue_manager.state is None:
            raise RuntimeError("No queue state loaded")
        
        state = self.queue_manager.state
        
        # Build command
        command = [
            sys.executable,
            "run_single_listing.py",
            "--listing-file",
            str(entry.listing_path),
            "--retries",
            str(state.retry_count),
            "--retry-delay",
            str(state.retry_delay),
        ]
        
        # Add publish flag if in publish mode
        if state.mode == "publish":
            command.append("--publish")
        
        logger.info(f"Executing command: {' '.join(command)}")
        
        # Execute subprocess
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            
            # Stream output
            if process.stdout:
                for line in process.stdout:
                    stdout_lines.append(line)
                    if self.output_callback:
                        self.output_callback(line.rstrip("\n"))
            
            # Wait for completion
            process.wait()
            
            # Capture stderr
            if process.stderr:
                stderr_lines = process.stderr.readlines()
            
            exit_code = process.returncode
            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)
            
            logger.info(f"Process exited with code: {exit_code}")
            
            return exit_code, stdout, stderr
            
        except Exception as e:
            logger.error(f"Subprocess execution failed: {e}")
            raise
    
    def _parse_status_lines(self, stdout: str) -> dict[str, str]:
        """
        Parse all STATUS:KEY=VALUE lines into a dictionary.
        
        Args:
            stdout: The subprocess stdout
            
        Returns:
            Dictionary of status key-value pairs
        """
        status_dict: dict[str, str] = {}
        
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("STATUS:"):
                payload = line.removeprefix("STATUS:")
                if "=" in payload:
                    key, value = payload.split("=", 1)
                    status_dict[key.strip()] = value.strip()
        
        return status_dict
    
    def _extract_error_message(self, stderr: str, stdout: str) -> str:
        """
        Extract the most useful error message with fallback priority.
        
        Args:
            stderr: The subprocess stderr
            stdout: The subprocess stdout
            
        Returns:
            Error message truncated to 500 characters
        """
        
        # Helper: Check if line is meaningful (not generic traceback)
        def is_meaningful_line(line: str) -> bool:
            line = line.strip()
            if not line:
                return False
            # Ignore generic traceback lines
            ignore_patterns = [
                "Traceback (most recent call last):",
                "File \"",
                "^",  # caret-only lines
            ]
            for pattern in ignore_patterns:
                if line.startswith(pattern) or line == pattern:
                    return False
            return True
        
        # Priority 1: Search stderr from bottom to top for meaningful error
        stderr_lines = [
            line.strip()
            for line in stderr.splitlines()
            if is_meaningful_line(line)
        ]
        
        error_keywords = [
            "Error",
            "Exception",
            "RuntimeError",
            "ValueError",
            "TimeoutError",
            "failed",
            "failure",
        ]
        
        for line in reversed(stderr_lines):
            if any(keyword in line for keyword in error_keywords):
                return line[:500]
        
        # Priority 2: Search stdout from bottom to top for error indicators
        stdout_patterns = [
            "STATUS:STEP=Selected Listing Failed",
            "RuntimeError:",
            "Error:",
            "Exception:",
            "failed (attempt",
            "Destination failures:",
            "Source scrape failures:",
        ]
        
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if any(pattern in line for pattern in stdout_patterns):
                return line[:500]
        
        # Priority 3: Any non-empty stderr line
        if stderr_lines:
            return stderr_lines[-1][:500]
        
        # Priority 4: Generic message
        return "Unknown failure"
    
    def _parse_outcome(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> tuple[QueueStatus, str]:
        """
        Parse subprocess outcome into status and message.
        
        Args:
            exit_code: The subprocess exit code
            stdout: The subprocess stdout
            stderr: The subprocess stderr
            
        Returns:
            Tuple of (QueueStatus, message)
        """
        # Parse STATUS: lines
        status = self._parse_status_lines(stdout)
        
        # Helper to safely parse integers
        def get_int(key: str) -> int:
            try:
                return int(status.get(key, "0"))
            except ValueError:
                return 0
        
        # Apply precedence rules
        if exit_code != 0:
            error_msg = self._extract_error_message(stderr, stdout)
            return QueueStatus.FAILED, error_msg
        
        if get_int("FAILED") > 0:
            error_msg = self._extract_error_message(stderr, stdout)
            return QueueStatus.FAILED, error_msg
        
        if get_int("UPLOADED") > 0:
            return QueueStatus.UPLOADED, "Successfully uploaded"
        
        if get_int("EXISTING") > 0:
            return QueueStatus.ALREADY_EXISTS, "Duplicate found"
        
        if get_int("PUBLISH_UNVERIFIED") > 0:
            return QueueStatus.PUBLISH_UNVERIFIED, "Publish clicked but verification failed"
        
        if get_int("WOULD_UPLOAD") > 0:
            return QueueStatus.SKIPPED, "Dry-run: would upload"
        
        # Fallback: check for "Already recorded copied"
        match = re.search(r"Already recorded copied:\s*(\d+)", stdout)
        if match and int(match.group(1)) > 0:
            return QueueStatus.ALREADY_EXISTS, "Already recorded copied"
        
        # No recognized outcome
        return (
            QueueStatus.FAILED,
            "Process exited successfully but no recognized terminal outcome was reported.",
        )
