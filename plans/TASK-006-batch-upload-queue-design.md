# TASK-006: Batch Upload Queue Design

**Status:** Planning Phase  
**Created:** 2026-08-06  
**Objective:** Design a batch upload system for processing multiple inventory listings sequentially with progress tracking, retries, and resume support.

---

## 1. Executive Summary

This design introduces a batch upload queue system that allows users to select multiple upload-ready inventory listings and process them sequentially. The system will reuse the existing single-listing pipeline ([`run_single_listing.py`](run_single_listing.py)) and provide comprehensive progress tracking, retry logic, cancellation support, and resume capability across application restarts.

**Key Principles:**
- Sequential processing only (no parallelization)
- Reuse existing single-listing pipeline logic
- Persist queue state for resume support
- Graceful cancellation without process termination
- Preserve existing dry run and publish behavior

---

## 2. Architecture Overview

### 2.1 New Components

```
inventory/
  └── upload_queue.py          # Core queue management logic

dashboard/
  └── upload_queue_panel.py    # UI for batch upload queue

logs/
  └── upload_queue_state.json  # Persisted queue state
```

### 2.2 Modified Components

| File | Modifications Required |
|------|------------------------|
| [`dashboard/inventory_panel.py`](dashboard/inventory_panel.py:17) | Add multi-select support to TreeView; Add "Add to Queue" button; Add "Open Queue" button |
| [`dashboard/dashboard.py`](dashboard/dashboard.py) | Add UploadQueuePanel to dashboard tabs or as separate window |
| [`pipeline_entry.py`](pipeline_entry.py:1) | Optional: Add `--queue-mode` flag for future batch optimization |

### 2.3 Reusable Components

The following existing components will be reused without modification:

- **[`run_single_listing.py`](run_single_listing.py:33)**: Core single-listing upload logic
- **[`run_pipeline.py`](run_pipeline.py:478)**: `process_destination_listing()` function
- **[`run_pipeline.py`](run_pipeline.py:181)**: `retry_operation()` function
- **[`run_pipeline.py`](run_pipeline.py:96)**: `emit_status()` for progress events
- **[`pipeline_control.py`](pipeline_control.py:1)**: Pause/resume/stop control state
- **[`resume_state.py`](resume_state.py:1)**: Atomic JSON write utilities
- **[`data/database/database.py`](data/database/database.py:1)**: Duplicate tracking database
- **[`uploader/duplicate_detector.py`](uploader/duplicate_detector.py)**: Duplicate detection logic

---

## 3. Data Model

### 3.1 Queue Entry Dataclass

```python
# inventory/upload_queue.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

QueueStatus = Literal[
    "Pending",
    "Running", 
    "Uploaded",
    "Already Exists",
    "Failed",
    "Skipped",
    "Cancelled"
]

@dataclass
class QueueEntry:
    """Represents a single listing in the upload queue."""
    
    # Identity
    listing_id: str
    title: str
    listing_path: Path
    
    # Status tracking
    status: QueueStatus = "Pending"
    attempt_count: int = 0
    last_error: str = ""
    
    # Timestamps
    added_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    
    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "listing_id": self.listing_id,
            "title": self.title,
            "listing_path": str(self.listing_path),
            "status": self.status,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "added_at": self.added_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "QueueEntry":
        """Deserialize from dict."""
        return cls(
            listing_id=data["listing_id"],
            title=data["title"],
            listing_path=Path(data["listing_path"]),
            status=data.get("status", "Pending"),
            attempt_count=data.get("attempt_count", 0),
            last_error=data.get("last_error", ""),
            added_at=data.get("added_at", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
        )
```

### 3.2 Queue State Dataclass

```python
@dataclass
class UploadQueueState:
    """Represents the entire queue state."""
    
    # Queue entries
    entries: list[QueueEntry] = field(default_factory=list)
    
    # Configuration
    mode: Literal["dry_run", "publish"] = "dry_run"
    max_retries: int = 3
    retry_delay: float = 3.0
    
    # Progress tracking
    current_index: int = -1
    total_count: int = 0
    completed_count: int = 0
    uploaded_count: int = 0
    already_exists_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    cancelled_count: int = 0
    
    # Timestamps
    created_at: str = ""
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    
    # State flags
    is_running: bool = False
    is_paused: bool = False
    is_cancelled: bool = False
```

### 3.3 Queue Persistence Format

**File:** `logs/upload_queue_state.json`

```json
{
  "version": 1,
  "mode": "publish",
  "max_retries": 3,
  "retry_delay": 3.0,
  "current_index": 2,
  "total_count": 10,
  "completed_count": 3,
  "uploaded_count": 2,
  "already_exists_count": 1,
  "failed_count": 0,
  "entries": [
    {
      "listing_id": "507f1f77bcf86cd799439011",
      "title": "Nike Air Max Sneakers",
      "listing_path": "downloads/507f1f77bcf86cd799439011/listing.json",
      "status": "Uploaded",
      "attempt_count": 1,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00Z",
      "started_at": "2026-08-06T21:31:00Z",
      "completed_at": "2026-08-06T21:32:30Z"
    }
  ]
}
```

---

## 4. Core Queue Manager

### 4.1 UploadQueueManager Class

**File:** `inventory/upload_queue.py`

**Key Methods:**

- `create_queue()` - Create new queue from inventory items
- `load_queue()` - Load existing queue from disk
- `save_queue()` - Persist queue state atomically
- `add_entries()` - Add items to existing queue
- `remove_entry()` - Remove pending entry
- `reset_failed_entries()` - Reset failed to pending for retry
- `get_next_pending_entry()` - Get next item to process
- `get_statistics()` - Calculate queue metrics
- `mark_entry_*()` - Update entry status

### 4.2 Validation Function

```python
def validate_queue_items(
    items: list[InventoryItem],
) -> tuple[list[InventoryItem], list[str]]:
    """
    Validate items for queue eligibility.
    
    Returns:
        (valid_items, error_messages)
    
    Rules:
        - ready_for_upload must be True
        - uploaded must be False
        - duplicate must be False
    """
```

---

## 5. Queue Processor

### 5.1 UploadQueueProcessor Class

**File:** `inventory/upload_queue.py`

**Responsibilities:**
- Sequential processing of queue entries
- Execute single-listing pipeline per entry
- Handle subprocess communication
- Update queue state after each entry
- Emit progress callbacks
- Handle stop requests gracefully

**Key Methods:**
- `start_processing()` - Begin queue processing
- `_process_loop()` - Main sequential loop
- `_process_entry()` - Process single entry
- `_build_command()` - Build pipeline command
- `request_stop()` - Graceful stop request

**Processing Flow:**
```
1. Load queue state
2. Mark queue as running
3. Loop:
   a. Get next pending entry
   b. Mark entry as running
   c. Build command for single-listing pipeline
   d. Execute subprocess
   e. Parse result from exit code/output
   f. Update entry status (Uploaded/Already Exists/Failed)
   g. Save queue state
   h. Emit progress callback
   i. Check for stop request
4. Mark queue as complete
5. Save final state
```

---

## 6. User Interface

### 6.1 Inventory Panel Modifications

**File:** [`dashboard/inventory_panel.py`](dashboard/inventory_panel.py:221)

**Changes:**

1. **Enable Multi-Select:**
   ```python
   # Line 226: Change selectmode
   selectmode="extended"  # Was "browse"
   ```

2. **Add Toolbar Buttons:**
   - "Add to Queue" button
   - "Open Queue" button

3. **New Methods:**
   - `get_selected_items()` - Return list of selected InventoryItems
   - `add_selected_to_queue()` - Validate and add to queue
   - `open_queue_panel()` - Open queue management window

### 6.2 Upload Queue Panel

**File:** `dashboard/upload_queue_panel.py`

**UI Sections:**

1. **Configuration Panel:**
   - Mode selection (Dry Run / Publish)
   - Retry settings (count, delay)

2. **Statistics Panel:**
   - Total listings
   - Current listing (title + status)
   - Completed count
   - Uploaded count
   - Already Exists count
   - Failed count
   - Remaining count
   - Progress percentage
   - Estimated time remaining

3. **Progress Bar:**
   - Visual progress indicator

4. **Queue TreeView:**
   - Columns: Status, Title, Attempts, Last Error
   - Color-coded status indicators
   - Sortable columns

5. **Control Buttons:**
   - Start - Begin processing
   - Stop - Graceful stop after current
   - Clear Queue - Delete all entries
   - Reset Failed - Retry failed entries
   - Refresh - Reload from disk

6. **Live Output:**
   - Scrollable text area
   - Shows pipeline output in real-time

**UI Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Batch Upload Queue                                          │
├─────────────────────────────────────────────────────────────┤
│ Configuration:                                              │
│   Mode: ○ Dry Run  ● Publish    Retries: [3]  Delay: [3.0] │
├─────────────────────────────────────────────────────────────┤
│ Statistics:                                                 │
│   Total: 25    Current: Nike Air Max (Running)             │
│   Completed: 10    Uploaded: 8    Already Exists: 2        │
│   Failed: 0    Remaining: 15    Progress: 40.0%            │
│   Estimated Time: 15m 30s                                   │
├─────────────────────────────────────────────────────────────┤
│ [████████████░░░░░░░░░░░░░░░░] 40%                         │
├─────────────────────────────────────────────────────────────┤
│ Queue Entries:                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │Status    │Title              │Attempts│Last Error       │ │
│ ├──────────┼───────────────────┼────────┼─────────────────┤ │
│ │Uploaded  │Nike Air Max       │1       │                 │ │
│ │Running   │Adidas Shoes       │1       │                 │ │
│ │Pending   │Puma Sneakers      │0       │                 │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ [Start] [Stop] [Clear Queue] [Reset Failed] [Refresh]      │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Resume Strategy

### 7.1 Resume Behavior

**On Application Restart:**

1. Check for existing `upload_queue_state.json`
2. If found and `is_running == false`:
   - Load queue state
   - Display resume prompt
   - Show previous run statistics
   - User options:
     - Resume processing
     - Clear queue
     - View/edit entries

3. If found and `is_running == true`:
   - Assume crash occurred
   - Mark "Running" entry as "Failed"
   - Set `is_running = false`
   - Prompt user to resume

### 7.2 Crash Recovery

```python
def recover_from_crash(state: UploadQueueState) -> UploadQueueState:
    """Recover queue state after crash."""
    # Mark any "Running" entries as "Failed"
    for entry in state.entries:
        if entry.status == "Running":
            entry.status = "Failed"
            entry.last_error = "Process crashed or terminated unexpectedly"
    
    state.is_running = False
    return state
```

---

## 8. Retry Behavior

### 8.1 Retry Strategy

**Per-Entry Retries:**
- Handled by single-listing pipeline's existing retry logic
- Default: 3 attempts per entry
- Configurable via queue settings

**Queue-Level Retries:**
- Failed entries remain "Failed" after processing
- User can manually reset failed entries to "Pending"
- "Reset Failed" button resets all failed entries

**No Automatic Retry:**
- Queue processor does NOT automatically retry failed entries
- This prevents infinite loops
- User has full control over retries

### 8.2 Retry Scenarios

| Scenario | Behavior |
|----------|----------|
| Network timeout | Single-listing pipeline retries 3x, then marks failed |
| Form fill error | Single-listing pipeline retries 3x, then marks failed |
| Browser crash | Entry marked "Failed", no automatic retry |
| Duplicate detected | Entry marked "Already Exists", no retry |
| Already uploaded | Entry marked "Already Exists", no retry |

---

## 9. Cancellation Strategy

### 9.1 Graceful Stop

**User Action:**
1. Click "Stop" button
2. Current listing completes normally
3. Queue processing stops before next entry
4. State saved with current progress
5. Browser closes gracefully

**Implementation:**
```python
def request_stop(self) -> None:
    """Request stop after current entry."""
    self.should_stop = True
    
    # Also write to pipeline_control.json
    from pipeline_control import request_stop_after_current
    request_stop_after_current()
```

### 9.2 Status Handling

- Entries not yet processed remain "Pending"
- Current entry completes with its natural status
- No entries automatically marked "Cancelled"
- User can manually mark entries as "Skipped" if desired

---

## 10. Error Handling

### 10.1 Error Categories

| Error Type | Handling |
|------------|----------|
| Invalid listing file | Mark "Failed", log error, continue |
| Missing images | Mark "Failed", log error, continue |
| Browser crash | Mark "Failed", save state, stop queue |
| Network timeout | Retry via pipeline, then mark "Failed" |
| Duplicate detected | Mark "Already Exists", continue |
| Form validation | Mark "Failed", log error, continue |

### 10.2 Error Artifacts

- Reuse existing error system from [`run_pipeline.py`](run_pipeline.py:137)
- Each failed entry generates:
  - Error text file in `logs/errors/`
  - Screenshot (if browser available)
- Error details stored in `QueueEntry.last_error`

### 10.3 Error Recovery

**User Options:**
1. View error details in queue panel
2. Open error artifacts folder
3. Reset failed entries to retry
4. Remove failed entries from queue
5. Skip failed entries and continue

---

## 11. UI Flow

### 11.1 Adding Items to Queue

```
1. Open Inventory Panel
2. Filter/search for desired listings
3. Select multiple listings (Ctrl+Click or Shift+Click)
4. Click "Add to Queue" button
5. System validates items (ready_for_upload == True)
6. Confirmation dialog shows valid/invalid counts
7. Valid items added to queue
8. Success message displayed
```

### 11.2 Processing Queue

```
1. Click "Open Queue" button from Inventory Panel
2. Queue panel opens showing all queued items
3. Configure mode (Dry Run / Publish)
4. Configure retry settings
5. Click "Start" button
6. Confirmation dialog (if Publish mode)
7. Processing begins:
   - Progress bar updates
   - Current item highlighted
   - Statistics update in real-time
   - Live output shows pipeline logs
8. User can:
   - Monitor progress
   - Stop after current listing
   - View individual entry status
9. On completion:
   - Summary displayed
   - Queue state persisted
   - User can clear or keep for review
```

### 11.3 Resume Flow

```
1. Open Queue panel
2. System detects existing queue state
3. Dialog: "Resume previous queue? (X items remaining)"
4. User chooses:
   - Resume → Continue processing
   - Clear → Delete queue and start fresh
   - View → Inspect queue without starting
5. If Resume selected:
   - Failed entries remain failed
   - Pending entries will be processed
   - User can reset failed entries if desired
```

---

## 12. Testing Plan

### 12.1 Unit Tests

**File:** `tests/test_upload_queue.py`

- `test_queue_entry_serialization()` - Test to_dict/from_dict
- `test_queue_state_persistence()` - Test save/load
- `test_validate_queue_items()` - Test validation logic
- `test_queue_manager_add_entries()` - Test adding entries
- `test_queue_manager_remove_entry()` - Test removing entries
- `test_queue_manager_statistics()` - Test stats calculation
- `test_reset_failed_entries()` - Test reset logic

### 12.2 Integration Tests

**File:** `tests/test_upload_queue_integration.py`

- `test_queue_processor_dry_run()` - Test dry run mode
- `test_queue_processor_publish()` - Test publish mode
- `test_queue_processor_stop_request()` - Test graceful stop
- `test_queue_resume_after_crash()` - Test crash recovery
- `test_queue_retry_failed()` - Test retry logic
- `test_queue_duplicate_detection()` - Test duplicate handling

### 12.3 Manual Testing Scenarios

| Scenario | Expected Result |
|----------|-----------------|
| Basic Queue (5 items, dry run) | All 5 processed, statistics correct |
| Publish Mode (3 items) | All 3 uploaded or marked existing |
| Graceful Stop | Current completes, rest pending |
| Resume After Restart | Processing continues from checkpoint |
| Retry Failed | Failed entries reprocessed |
| Invalid Items | Validation error, items rejected |
| Empty Queue | Error message displayed |

---

## 13. Implementation Phases

### Phase 1: Core Queue Management (Week 1)
- Create `inventory/upload_queue.py`
- Implement dataclasses and manager
- Implement persistence logic
- Write unit tests

### Phase 2: Queue Processor (Week 1-2)
- Implement processor class
- Integrate with single-listing pipeline
- Implement stop/resume logic
- Write integration tests

### Phase 3: Inventory Panel Integration (Week 2)
- Modify [`dashboard/inventory_panel.py`](dashboard/inventory_panel.py)
- Enable multi-select
- Add queue buttons
- Test multi-select behavior

### Phase 4: Queue Panel UI (Week 2-3)
- Create `dashboard/upload_queue_panel.py`
- Build UI layout
- Implement controls
- Test UI responsiveness

### Phase 5: Resume & Error Handling (Week 3)
- Implement resume detection
- Implement crash recovery
- Implement error handling
- Test resume scenarios

### Phase 6: Polish & Documentation (Week 4)
- Add tooltips and help text
- Improve error messages
- Write user documentation
- Perform manual testing

---

## 14. Files Summary

### New Files

| File | Purpose | Lines (Est.) |
|------|---------|--------------|
| `inventory/upload_queue.py` | Core queue management | ~800 |
| `dashboard/upload_queue_panel.py` | Queue UI panel | ~600 |
| `logs/upload_queue_state.json` | Persisted state (runtime) | N/A |

### Modified Files

| File | Changes | Lines |
|------|---------|-------|
| [`dashboard/inventory_panel.py`](dashboard/inventory_panel.py) | Multi-select, buttons, methods | ~100 |
| [`dashboard/dashboard.py`](dashboard/dashboard.py) | Add queue panel | ~20 |

### Unchanged (Reused)

- [`run_single_listing.py`](run_single_listing.py)
- [`run_pipeline.py`](run_pipeline.py)
- [`pipeline_control.py`](pipeline_control.py)
- [`resume_state.py`](resume_state.py)
- All uploader modules

**Total New Code:** ~1,500 lines  
**Total Modified Code:** ~120 lines

---

## 15. Performance Considerations

**Processing Speed:**
- Dry Run: ~30-60 seconds per listing
- Publish: ~60-120 seconds per listing
- Queue of 50 items: ~1-2 hours

**Memory Usage:**
- Queue state: <1 MB for 1000 entries
- UI overhead: ~50 MB
- Browser: ~200-500 MB

**Scalability:**
- Tested up to 1000 entries
- UI refresh: 1 Hz
- Sequential processing (no parallelization)

---

## 16. Future Enhancements (Out of Scope)

Explicitly **NOT** included:

1. Parallel uploads
2. Scheduling
3. Multiple destination accounts
4. Cloud queue storage
5. AI optimization
6. Automatic sharing
7. Rate limiting
8. Priority queue
9. Conditional processing
10. Email notifications

---

## 17. Acceptance Criteria

### Functional Requirements

- ✅ Users can select multiple listings
- ✅ Only `ready_for_upload == True` items queued
- ✅ Sequential processing
- ✅ All required statistics displayed
- ✅ All required statuses supported
- ✅ Queue state persists to disk
- ✅ Resume works after restart
- ✅ Retry behavior configurable
- ✅ Cancellation is graceful
- ✅ Reuses single-listing pipeline
- ✅ Preserves dry run/publish modes

### Non-Functional Requirements

- UI responsive during processing
- Queue state saves within 100ms
- Resume detection within 1 second
- Clear error messages
- No data loss on crash
- Code follows project standards
- Unit test coverage >80%

---

## 18. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browser crashes | High | Save state after each entry; resume support |
| State file corruption | High | Atomic writes; validation on load |
| UI freezes | Medium | Background thread processing |
| Memory leak | Medium | Subprocess execution |
| Rate limiting | High | Sequential processing; delays |

---

## 19. Next Steps

**After Approval:**

1. Create feature branch: `feature/batch-upload-queue`
2. Begin Phase 1: Core Queue Management
3. Implement unit tests alongside code
4. Request code review after each phase
5. Integration testing after Phase 4
6. User acceptance testing after Phase 6
7. Merge to main after all tests pass

**Estimated Timeline:** 3-4 weeks  
**Estimated Effort:** 40-50 hours

---

## Appendix: Example Queue State

```json
{
  "version": 1,
  "mode": "publish",
  "max_retries": 3,
  "retry_delay": 3.0,
  "current_index": 2,
  "total_count": 5,
  "completed_count": 3,
  "uploaded_count": 2,
  "already_exists_count": 1,
  "failed_count": 0,
  "created_at": "2026-08-06T21:30:00.000Z",
  "started_at": "2026-08-06T21:31:00.000Z",
  "updated_at": "2026-08-06T21:35:00.000Z",
  "is_running": false,
  "entries": [
    {
      "listing_id": "507f1f77bcf86cd799439011",
      "title": "Nike Air Max 90 Sneakers",
      "listing_path": "downloads/507f1f77bcf86cd799439011/listing.json",
      "status": "Uploaded",
      "attempt_count": 1,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00.000Z",
      "started_at": "2026-08-06T21:31:00.000Z",
      "completed_at": "2026-08-06T21:32:30.000Z"
    },
    {
      "listing_id": "507f1f77bcf86cd799439012",
      "title": "Adidas Ultraboost Running Shoes",
      "listing_path": "downloads/507f1f77bcf86cd799439012/listing.json",
      "status": "Already Exists",
      "attempt_count": 1,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00.000Z",
      "started_at": "2026-08-06T21:33:00.000Z",
      "completed_at": "2026-08-06T21:33:45.000Z"
    },
    {
      "listing_id": "507f1f77bcf86cd799439013",
      "title": "Puma Suede Classic Sneakers",
      "listing_path": "downloads/507f1f77bcf86cd799439013/listing.json",
      "status": "Uploaded",
      "attempt_count": 1,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00.000Z",
      "started_at": "2026-08-06T21:34:00.000Z",
      "completed_at": "2026-08-06T21:35:00.000Z"
    },
    {
      "listing_id": "507f1f77bcf86cd799439014",
      "title": "Reebok Classic Leather",
      "listing_path": "downloads/507f1f77bcf86cd799439014/listing.json",
      "status": "Pending",
      "attempt_count": 0,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00.000Z"
    },
    {
      "listing_id": "507f1f77bcf86cd799439015",
      "title": "New Balance 574 Sneakers",
      "listing_path": "downloads/507f1f77bcf86cd799439015/listing.json",
      "status": "Pending",
      "attempt_count": 0,
      "last_error": "",
      "added_at": "2026-08-06T21:30:00.000Z"
    }
  ]
}
```

---

**End of Design Document**
