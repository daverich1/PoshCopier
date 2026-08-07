from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from inventory.inventory_item import InventoryItem
from runtime_paths import LOGS_DIR


# ===== Constants =====

QUEUE_STATE_FILE = LOGS_DIR / "upload_queue.json"


# ===== Enums =====

class QueueStatus(str, Enum):
    """Status of a queue entry."""
    WAITING = "waiting"
    PENDING = "pending"
    RUNNING = "running"
    UPLOADED = "uploaded"
    ALREADY_EXISTS = "already_exists"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    PUBLISH_UNVERIFIED = "publish_unverified"


# ===== Helper Functions =====

def utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write JSON to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        
        Path(temporary_name).replace(path)
    
    except Exception:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ===== Dataclasses =====

@dataclass
class QueueEntry:
    """Represents a single listing in the upload queue."""
    
    listing_id: str
    title: str
    listing_path: Path
    status: QueueStatus = QueueStatus.WAITING
    attempt_count: int = 0
    last_error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "listing_id": self.listing_id,
            "title": self.title,
            "listing_path": str(self.listing_path),
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueEntry:
        """Deserialize from dict."""
        return cls(
            listing_id=data["listing_id"],
            title=data["title"],
            listing_path=Path(data["listing_path"]),
            status=QueueStatus(data.get("status", QueueStatus.WAITING.value)),
            attempt_count=data.get("attempt_count", 0),
            last_error=data.get("last_error", ""),
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


@dataclass
class UploadQueueState:
    """Represents the entire upload queue state."""
    
    version: int = 1
    queue_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    mode: str = "dry_run"  # "dry_run" or "publish"
    retry_count: int = 3
    retry_delay: float = 3.0
    paused: bool = False
    stop_requested: bool = False
    entries: list[QueueEntry] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "version": self.version,
            "queue_id": self.queue_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "mode": self.mode,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "paused": self.paused,
            "stop_requested": self.stop_requested,
            "entries": [entry.to_dict() for entry in self.entries],
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UploadQueueState:
        """Deserialize from dict."""
        return cls(
            version=data.get("version", 1),
            queue_id=data.get("queue_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            mode=data.get("mode", "dry_run"),
            retry_count=data.get("retry_count", 3),
            retry_delay=data.get("retry_delay", 3.0),
            paused=data.get("paused", False),
            stop_requested=data.get("stop_requested", False),
            entries=[
                QueueEntry.from_dict(entry_data)
                for entry_data in data.get("entries", [])
            ],
        )


# ===== Manager =====

class UploadQueueManager:
    """Manages the upload queue state and persistence."""
    
    def __init__(self, state_file: Path = QUEUE_STATE_FILE):
        self.state_file = state_file
        self.state: UploadQueueState | None = None
    
    # ----- Persistence -----
    
    def load(self) -> UploadQueueState | None:
        """Load queue state from disk."""
        if not self.state_file.exists():
            return None
        
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        
        if not isinstance(payload, dict):
            return None
        
        state = UploadQueueState.from_dict(payload)
        
        # State recovery: Convert RUNNING entries to PENDING
        for entry in state.entries:
            if entry.status == QueueStatus.RUNNING:
                entry.status = QueueStatus.PENDING
                entry.started_at = ""
        
        self.state = state
        return state
    
    def save(self) -> None:
        """Save current queue state to disk."""
        if self.state is None:
            raise RuntimeError("No queue state to save")
        
        self.state.updated_at = utc_now()
        payload = self.state.to_dict()
        _atomic_write_json(self.state_file, payload)
    
    def clear(self) -> bool:
        """Delete queue state file."""
        if not self.state_file.exists():
            return False
        
        try:
            self.state_file.unlink()
            self.state = None
            return True
        except OSError:
            return False
    
    # ----- Queue Management -----
    
    def add_items(self, items: list[InventoryItem]) -> tuple[int, list[str]]:
        """
        Add inventory items to queue.
        
        Returns:
            (added_count, error_messages)
        """
        errors: list[str] = []
        added_count = 0
        
        # Load or create state
        if self.state is None:
            self.state = UploadQueueState(
                queue_id=str(uuid.uuid4()),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        
        # Get existing listing IDs
        existing_ids = {entry.listing_id for entry in self.state.entries}
        
        # Validate and add items
        for item in items:
            # Check if ready for upload
            if not item.ready_for_upload:
                errors.append(
                    f"{item.title}: Not ready for upload "
                    f"(health: {item.health_status})"
                )
                continue
            
            # Check if already in queue
            if item.listing_id in existing_ids:
                errors.append(f"{item.title}: Already in queue")
                continue
            
            # Check if listing file exists
            if not item.listing_path.exists():
                errors.append(f"{item.title}: Listing file not found")
                continue
            
            # Check if already uploaded
            if item.uploaded:
                errors.append(f"{item.title}: Already uploaded")
                continue
            
            # Check if marked as duplicate
            if item.duplicate:
                errors.append(f"{item.title}: Marked as duplicate")
                continue
            
            # Add to queue
            entry = QueueEntry(
                listing_id=item.listing_id,
                title=item.title,
                listing_path=item.listing_path,
                status=QueueStatus.WAITING,
                created_at=utc_now(),
            )
            
            self.state.entries.append(entry)
            existing_ids.add(item.listing_id)
            added_count += 1
        
        # Save if items were added
        if added_count > 0:
            self.save()
        
        return added_count, errors
    
    def remove_entry(self, listing_id: str) -> bool:
        """Remove an entry from the queue."""
        if self.state is None:
            return False
        
        original_count = len(self.state.entries)
        
        # Remove entry if not completed
        self.state.entries = [
            entry
            for entry in self.state.entries
            if entry.listing_id != listing_id
            or entry.status in (QueueStatus.UPLOADED, QueueStatus.ALREADY_EXISTS)
        ]
        
        removed = len(self.state.entries) < original_count
        
        if removed:
            self.save()
        
        return removed
    
    def reset_failed(self) -> int:
        """Reset all failed entries to PENDING. Returns count reset."""
        if self.state is None:
            return 0
        
        reset_count = 0
        
        for entry in self.state.entries:
            if entry.status == QueueStatus.FAILED:
                entry.status = QueueStatus.PENDING
                entry.attempt_count = 0
                entry.last_error = ""
                entry.started_at = ""
                entry.finished_at = ""
                entry.duration_seconds = 0.0
                reset_count += 1
        
        if reset_count > 0:
            self.save()
        
        return reset_count
    
    # ----- Status Updates -----
    
    def _find_entry(self, listing_id: str) -> QueueEntry | None:
        """Find entry by listing_id."""
        if self.state is None:
            return None
        
        for entry in self.state.entries:
            if entry.listing_id == listing_id:
                return entry
        
        return None
    
    def mark_running(self, listing_id: str) -> None:
        """Mark entry as running."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.RUNNING
        entry.started_at = utc_now()
        entry.attempt_count += 1
        
        self.save()
    
    def mark_uploaded(self, listing_id: str) -> None:
        """Mark entry as uploaded."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.UPLOADED
        entry.finished_at = utc_now()
        
        # Calculate duration
        if entry.started_at:
            try:
                started = datetime.fromisoformat(entry.started_at)
                finished = datetime.fromisoformat(entry.finished_at)
                entry.duration_seconds = (finished - started).total_seconds()
            except (ValueError, TypeError):
                pass
        
        self.save()
    
    def mark_already_exists(self, listing_id: str) -> None:
        """Mark entry as already exists."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.ALREADY_EXISTS
        entry.finished_at = utc_now()
        
        # Calculate duration
        if entry.started_at:
            try:
                started = datetime.fromisoformat(entry.started_at)
                finished = datetime.fromisoformat(entry.finished_at)
                entry.duration_seconds = (finished - started).total_seconds()
            except (ValueError, TypeError):
                pass
        
        self.save()
    
    def mark_failed(self, listing_id: str, error: str) -> None:
        """Mark entry as failed with error message."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.FAILED
        entry.last_error = error
        entry.finished_at = utc_now()
        
        # Calculate duration
        if entry.started_at:
            try:
                started = datetime.fromisoformat(entry.started_at)
                finished = datetime.fromisoformat(entry.finished_at)
                entry.duration_seconds = (finished - started).total_seconds()
            except (ValueError, TypeError):
                pass
        
        self.save()
    
    def mark_publish_unverified(self, listing_id: str, message: str = "") -> None:
        """Mark entry as publish_unverified (publish clicked but not verified)."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.PUBLISH_UNVERIFIED
        entry.last_error = message
        entry.finished_at = utc_now()
        
        # Calculate duration
        if entry.started_at:
            try:
                started = datetime.fromisoformat(entry.started_at)
                finished = datetime.fromisoformat(entry.finished_at)
                entry.duration_seconds = (finished - started).total_seconds()
            except (ValueError, TypeError):
                pass
        
        self.save()
    
    def mark_skipped(self, listing_id: str) -> None:
        """Mark entry as skipped."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.SKIPPED
        entry.finished_at = utc_now()
        
        self.save()
    
    def mark_cancelled(self, listing_id: str) -> None:
        """Mark entry as cancelled."""
        entry = self._find_entry(listing_id)
        
        if entry is None:
            raise ValueError(f"Entry not found: {listing_id}")
        
        entry.status = QueueStatus.CANCELLED
        entry.finished_at = utc_now()
        
        self.save()
    
    # ----- Control -----
    
    def request_pause(self) -> None:
        """Request queue processing to pause."""
        if self.state is None:
            raise RuntimeError("No queue state loaded")
        
        self.state.paused = True
        self.save()
    
    def resume(self) -> None:
        """Resume queue processing."""
        if self.state is None:
            raise RuntimeError("No queue state loaded")
        
        self.state.paused = False
        self.save()
    
    def request_stop(self) -> None:
        """Request queue processing to stop."""
        if self.state is None:
            raise RuntimeError("No queue state loaded")
        
        self.state.stop_requested = True
        self.save()
    
    def reset_stop_request(self) -> None:
        """Clear stop request flag."""
        if self.state is None:
            raise RuntimeError("No queue state loaded")
        
        self.state.stop_requested = False
        self.save()
    
    # ----- Queries -----
    
    def pending_entries(self) -> list[QueueEntry]:
        """Get all pending entries."""
        if self.state is None:
            return []
        
        return [
            entry
            for entry in self.state.entries
            if entry.status == QueueStatus.PENDING
        ]
    
    def failed_entries(self) -> list[QueueEntry]:
        """Get all failed entries."""
        if self.state is None:
            return []
        
        return [
            entry
            for entry in self.state.entries
            if entry.status == QueueStatus.FAILED
        ]
    
    def completed_entries(self) -> list[QueueEntry]:
        """Get all completed entries (uploaded or already exists)."""
        if self.state is None:
            return []
        
        return [
            entry
            for entry in self.state.entries
            if entry.status in (QueueStatus.UPLOADED, QueueStatus.ALREADY_EXISTS)
        ]
    
    def progress_summary(self) -> dict[str, Any]:
        """Get progress statistics."""
        if self.state is None:
            return {
                "total": 0,
                "waiting": 0,
                "pending": 0,
                "running": 0,
                "uploaded": 0,
                "already_exists": 0,
                "failed": 0,
                "skipped": 0,
                "cancelled": 0,
                "completed": 0,
                "remaining": 0,
                "percent": 0.0,
            }
        
        # Count by status
        counts = {
            "waiting": 0,
            "pending": 0,
            "running": 0,
            "uploaded": 0,
            "already_exists": 0,
            "failed": 0,
            "skipped": 0,
            "cancelled": 0,
            "publish_unverified": 0,
        }
        
        for entry in self.state.entries:
            status_key = entry.status.value
            if status_key in counts:
                counts[status_key] += 1
        
        total = len(self.state.entries)
        
        # Terminal states that count as "completed"
        terminal_completed = (
            counts["uploaded"]
            + counts["already_exists"]
            + counts["failed"]
            + counts["skipped"]
            + counts["cancelled"]
            + counts["publish_unverified"]
        )
        
        # Remaining = only non-terminal states
        remaining = (
            counts["waiting"]
            + counts["pending"]
            + counts["running"]
        )
        
        # Percent = terminal entries / total
        percent = (terminal_completed / total * 100.0) if total > 0 else 0.0
        
        return {
            "total": total,
            "waiting": counts["waiting"],
            "pending": counts["pending"],
            "running": counts["running"],
            "uploaded": counts["uploaded"],
            "already_exists": counts["already_exists"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "cancelled": counts["cancelled"],
            "publish_unverified": counts["publish_unverified"],
            "completed": completed,
            "remaining": remaining,
            "percent": percent,
        }
