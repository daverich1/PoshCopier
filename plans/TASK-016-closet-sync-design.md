# TASK-016: Automatic Closet Sync Pipeline - Design Document

## Overview

Create a one-button workflow to synchronize the source Poshmark closet with local inventory, automatically downloading new listings and queueing them for upload.

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Dashboard (Main Thread)                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Pipeline Tab UI                           │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  [Sync Closet] Button                            │  │ │
│  │  │  - Shows confirmation dialog                     │  │ │
│  │  │  - Launches sync in daemon thread                │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                          │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │  Progress Display (Label)                        │  │ │
│  │  │  - Updates via self.after() callbacks            │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Spawns daemon thread
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  ClosetSync (Worker Thread)                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  run()                                                 │ │
│  │    ├─► scan_source()                                  │ │
│  │    │     └─► scraper.discover.discover_closet()       │ │
│  │    │                                                   │ │
│  │    ├─► download_new()                                 │ │
│  │    │     └─► scraper.listing_scraper.scrape_listing() │ │
│  │    │                                                   │ │
│  │    ├─► build_inventory()                              │ │
│  │    │     └─► inventory.InventoryManager.load_items()  │ │
│  │    │                                                   │ │
│  │    ├─► queue_ready()                                  │ │
│  │    │     └─► inventory.UploadQueueManager.add()       │ │
│  │    │                                                   │ │
│  │    └─► refresh_dashboard()                            │ │
│  │          └─► Callback via self.after()                │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Class Design

### ClosetSync

**Location:** `pipeline/closet_sync.py`

```python
class ClosetSync:
    """
    Orchestrates automatic closet synchronization.
    
    Scans source closet, downloads new listings, updates inventory,
    and queues ready items for upload.
    """
    
    def __init__(
        self,
        source_username: str,
        downloads_dir: Path,
        progress_callback: Callable[[str], None] | None = None,
        log_file: Path | None = None,
    ):
        """
        Args:
            source_username: Poshmark username to scan
            downloads_dir: Directory for downloaded listings
            progress_callback: Function to report progress (thread-safe)
            log_file: Path to sync log file
        """
        
    def scan_source(self) -> list[DiscoveredListing]:
        """
        Scan source closet for all listings.
        
        Returns:
            List of discovered listings with metadata
            
        Raises:
            RuntimeError: If browser automation fails
        """
        
    def download_new(
        self,
        discovered: list[DiscoveredListing]
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """
        Download only listings not already in inventory.
        
        Args:
            discovered: List of discovered listings
            
        Returns:
            Tuple of (successful_ids, failed_items)
            failed_items is list of (listing_id, error_message)
        """
        
    def build_inventory(self) -> list[InventoryItem]:
        """
        Reload inventory from disk.
        
        Returns:
            Complete list of inventory items
        """
        
    def queue_ready(
        self,
        new_ids: list[str]
    ) -> int:
        """
        Queue newly downloaded listings that are Ready.
        
        Args:
            new_ids: List of newly downloaded listing IDs
            
        Returns:
            Number of items queued
        """
        
    def refresh_dashboard(self) -> None:
        """
        Trigger dashboard refresh via callback.
        
        Must be called via self.after() to ensure thread safety.
        """
        
    def run(self) -> SyncResult:
        """
        Execute complete sync workflow.
        
        Returns:
            SyncResult with statistics and errors
        """

@dataclass
class SyncResult:
    """Result of closet sync operation."""
    total_scanned: int
    already_downloaded: int
    new_imported: int
    queued: int
    failed: list[tuple[str, str]]  # (listing_id, error)
    elapsed_seconds: float
```

---

## Callback Flow

### Thread Communication Pattern

```
Main Thread (UI)                    Worker Thread (ClosetSync)
─────────────────                   ──────────────────────────

[Sync Button Clicked]
      │
      ├─► Show confirmation dialog
      │
      ├─► Create ClosetSync instance
      │       with progress_callback
      │
      ├─► Start daemon thread
      │       thread.start()
      │
      └─► Return (UI remains responsive)
                                            │
                                            ├─► run() begins
                                            │
                                            ├─► scan_source()
                                            │     │
                                            │     └─► progress_callback(
                                            │           "Scanning closet..."
                                            │         )
                                            │              │
      ┌─────────────────────────────────────────────────────┘
      │
      ├─► self.after(0, update_label, msg)
      │     └─► UI updates immediately
      │
                                            │
                                            ├─► download_new()
                                            │     │
                                            │     └─► progress_callback(
                                            │           "Downloading 3/9..."
                                            │         )
                                            │              │
      ┌─────────────────────────────────────────────────────┘
      │
      ├─► self.after(0, update_label, msg)
      │
                                            │
                                            ├─► queue_ready()
                                            │
                                            ├─► refresh_dashboard()
                                            │     │
                                            │     └─► progress_callback(
                                            │           "REFRESH_PANELS"
                                            │         )
                                            │              │
      ┌─────────────────────────────────────────────────────┘
      │
      ├─► self.after(0, refresh_all_panels)
      │
                                            │
                                            └─► return SyncResult
                                                      │
      ┌─────────────────────────────────────────────┘
      │
      └─► self.after(0, show_completion_dialog)
```

### Key Principles

1. **Never call Tkinter from worker thread**
   - All UI updates via `self.after(0, callback)`
   
2. **Progress callback is thread-safe**
   - Accepts string messages
   - Queues UI updates via `self.after()`
   
3. **Daemon thread**
   - Automatically terminates when main thread exits
   - No blocking of application shutdown

---

## Thread Lifecycle

### State Diagram

```
┌─────────────┐
│   IDLE      │  User clicks "Sync Closet"
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ CONFIRMING  │  Show dialog: "Continue?"
└──────┬──────┘
       │ [Yes]
       ▼
┌─────────────┐
│  STARTING   │  Create thread, set daemon=True
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  SCANNING   │  Worker: scan_source()
└──────┬──────┘  Progress: "Scanning closet..."
       │
       ▼
┌─────────────┐
│ DOWNLOADING │  Worker: download_new()
└──────┬──────┘  Progress: "Downloading 3/9..."
       │
       ▼
┌─────────────┐
│  QUEUEING   │  Worker: queue_ready()
└──────┬──────┘  Progress: "Queueing ready items..."
       │
       ▼
┌─────────────┐
│ REFRESHING  │  Worker: refresh_dashboard()
└──────┬──────┘  Callback: Refresh panels
       │
       ▼
┌─────────────┐
│  COMPLETE   │  Show completion dialog
└──────┬──────┘  Thread terminates
       │
       ▼
┌─────────────┐
│   IDLE      │
└─────────────┘
```

### Error Handling

- **Individual download failures**: Continue processing remaining listings
- **Critical failures** (browser crash): Abort, show error dialog
- **All failures logged** to `logs/closet_sync.log`

---

## Dashboard Integration

### UI Changes

#### Pipeline Tab Layout

```
┌────────────────────────────────────────────────────────┐
│  Run Settings                                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Mode: ○ Dry Run  ○ Live Publish                 │ │
│  │  Listings: [5]    Retries: [3]                   │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Closet Sync                                          │
│  ┌──────────────────────────────────────────────────┐ │
│  │  [Sync Closet]                                   │ │
│  │                                                   │ │
│  │  Status: Idle                                    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Controls                                             │
│  ┌──────────────────────────────────────────────────┐ │
│  │  [Start Pipeline]  [Pause]  [Stop]               │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

#### New Section: Closet Sync

**Location:** Between "Run Settings" and "Controls"

**Components:**
- `ttk.LabelFrame` with text "Closet Sync"
- `ttk.Button` labeled "Sync Closet"
- `ttk.Label` for status display (initially "Idle")

### Confirmation Dialog

**Title:** "Sync Closet"

**Message:**
```
This will scan the source closet for new listings.

Only listings not already downloaded will be imported.

Continue?
```

**Buttons:** Yes / No

### Progress Display

**Updates during sync:**
```
Scanning closet...
Found 12 listings
3 already downloaded
9 new listings
Downloading 1/9...
Downloading 2/9...
...
Downloading 9/9...
Inventory updated
Queue updated
Sync Complete
```

### Completion Dialog

**Title:** "Closet Sync Complete"

**Message:**
```
Closet Sync Complete

Listings scanned: 12
Already downloaded: 3
New imported: 9
Queued: 7
Failed: 0

Elapsed time: 2m 34s
```

**Button:** OK

### Panel Refresh

After sync completion:
1. **Inventory Panel**: Call `refresh()` to reload items
2. **Upload Queue Panel**: Call `refresh()` to reload queue
3. **Status counts**: Update all count labels

---

## Duplicate Detection

### Strategy

Use existing inventory to prevent re-downloads:

```python
def is_already_downloaded(listing_id: str) -> bool:
    """Check if listing already exists in downloads directory."""
    listing_dir = DOWNLOADS_DIR / listing_id
    listing_file = listing_dir / "listing.json"
    return listing_file.exists()
```

### Implementation

In `download_new()`:
1. Load existing inventory items
2. Build set of existing listing IDs
3. Filter discovered listings
4. Download only new listings

---

## Queue Behavior

### Queueing Rules

**Only queue listings that are Ready:**

```python
def should_queue(item: InventoryItem) -> bool:
    """Determine if item should be auto-queued."""
    return (
        item.health_status == "Ready" and
        item.ready_for_upload and
        not item.uploaded and
        not item.duplicate
    )
```

### Implementation

In `queue_ready()`:
1. Load inventory items for new listing IDs
2. Filter by `should_queue()` criteria
3. Add to upload queue via `UploadQueueManager.add()`
4. Return count of queued items

---

## Error Handling

### Download Failures

**Strategy:** Continue processing remaining listings

```python
successful = []
failed = []

for listing in to_download:
    try:
        scrape_listing(listing.url)
        successful.append(listing.listing_id)
    except Exception as e:
        failed.append((listing.listing_id, str(e)))
        log_error(listing.listing_id, e)
```

### Critical Failures

**Examples:**
- Browser automation fails to start
- Source username not configured
- Network completely unavailable

**Handling:**
- Abort sync immediately
- Show error dialog with details
- Log full traceback

### Logging

**File:** `logs/closet_sync.log`

**Format:**
```
2026-08-07 00:15:23 - INFO - Starting closet sync for @username
2026-08-07 00:15:45 - INFO - Discovered 12 listings
2026-08-07 00:15:45 - INFO - 3 already downloaded, 9 new
2026-08-07 00:16:12 - ERROR - Failed to download 65f3a2b1c4d5e6f7a8b9c0d1: Network timeout
2026-08-07 00:18:57 - INFO - Sync complete: 8 imported, 1 failed
```

---

## Configuration

### Source Username

**Location:** `config.py` or `source_state.json`

**Fallback:** Prompt user if not configured

### Sync Settings

```python
# Maximum concurrent downloads (future enhancement)
MAX_CONCURRENT_DOWNLOADS = 1

# Retry failed downloads
RETRY_FAILED_DOWNLOADS = True
MAX_DOWNLOAD_RETRIES = 2

# Browser timeout
BROWSER_TIMEOUT_SECONDS = 30
```

---

## Testing Strategy

### Unit Tests

Not required for initial implementation (per task requirements).

### Manual Testing

1. **Empty inventory**: Sync should download all listings
2. **Partial inventory**: Sync should download only new listings
3. **Complete inventory**: Sync should download nothing
4. **Mixed health states**: Only Ready items should be queued
5. **Download failures**: Should continue processing remaining items

### Compilation Test

```bash
python -m py_compile pipeline/closet_sync.py
python -m py_compile dashboard/dashboard.py
python -m py_compile dashboard/pipeline_panel.py
```

---

## Implementation Checklist

- [ ] Create `pipeline/closet_sync.py`
  - [ ] `ClosetSync` class
  - [ ] `SyncResult` dataclass
  - [ ] All methods with proper error handling
  - [ ] Logging to `logs/closet_sync.log`

- [ ] Modify `dashboard/dashboard.py`
  - [ ] Add "Closet Sync" section to Pipeline tab
  - [ ] Add "Sync Closet" button
  - [ ] Add status label
  - [ ] Implement confirmation dialog
  - [ ] Implement progress callback
  - [ ] Implement completion dialog
  - [ ] Wire up panel refresh

- [ ] Test compilation
  - [ ] `pipeline/closet_sync.py`
  - [ ] `dashboard/dashboard.py`

---

## Future Enhancements

1. **Scheduled sync**: Run automatically on timer
2. **Incremental sync**: Track last sync time, only check new listings
3. **Concurrent downloads**: Download multiple listings in parallel
4. **Sync history**: Track sync operations over time
5. **Selective sync**: Allow user to choose which listings to import

---

## Dependencies

### Existing Components

- `scraper.discover.discover_closet()` - Closet scanning
- `scraper.listing_scraper.scrape_listing()` - Listing download
- `inventory.InventoryManager` - Inventory management
- `inventory.UploadQueueManager` - Queue management
- `inventory.InventoryItem` - Item representation

### New Dependencies

None - uses existing infrastructure.

---

## Notes

- **No automatic upload**: Sync only prepares listings, user must manually start upload
- **Thread safety**: All UI updates via `self.after()` callbacks
- **Daemon thread**: Ensures clean shutdown
- **Idempotent**: Safe to run multiple times
- **Resilient**: Individual failures don't abort entire sync

