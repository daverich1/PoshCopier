# TASK-016: Closet Sync - Concrete Implementation Specification

## 1. Exact Existing Functions/Classes to Reuse

### Scanning Source Closet
**Function:** `scraper.discover.discover_closet()`
```python
# Location: scraper/discover.py:366
def discover_closet(
    page: Page,
    closet_url: str,
    *,
    max_scrolls: int = 600,
    stable_rounds_required: int = 8,
    scroll_pause_ms: int = 1200,
    progress_path: Path | None = None,
) -> list[DiscoveredListing]
```

**Returns:** `list[DiscoveredListing]` with fields:
- `listing_id: str`
- `url: str`
- `title: str`
- `card_status: str`
- `available: bool`
- `card_text: str`
- `matched_status_text: str`

### Scraping/Downloading One Listing
**Function:** `scraper.listing_scraper.scrape_listing()`
```python
# Location: scraper/listing_scraper.py:402
def scrape_listing(
    page: Page,
    listing_url: str,
) -> dict
```

**Returns:** Dictionary with listing data (automatically saved to disk via `save_listing()`)

**Note:** This function internally calls:
- `scraper.save_listing.save_listing()` - Saves to `downloads/{listing_id}/listing.json`
- `scraper.image_downloader.download_listing_images()` - Downloads images

### Duplicate Detection
**Function:** Check if listing directory exists
```python
# Location: scraper.py:52 (pattern to reuse)
def listing_is_downloaded(listing_id: str) -> bool:
    path = DOWNLOADS_DIR / listing_id / "listing.json"
    return path.exists()
```

**Implementation in ClosetSync:**
```python
def _is_already_downloaded(self, listing_id: str) -> bool:
    """Check if listing already exists in downloads."""
    listing_file = self.downloads_dir / listing_id / "listing.json"
    return listing_file.exists()
```

### Inventory Reload
**Class:** `inventory.inventory_manager.InventoryManager`
```python
# Location: inventory/inventory_manager.py:12
class InventoryManager:
    def load_items(self) -> list[InventoryItem]:
        """Load all inventory items from downloads directory."""
```

### Queueing Ready Items
**Class:** `inventory.upload_queue.UploadQueueManager`
```python
# Location: inventory/upload_queue.py:145
class UploadQueueManager:
    def add_items(
        self, 
        items: list[InventoryItem]
    ) -> tuple[int, list[str]]:
        """
        Add inventory items to queue.
        Returns: (added_count, error_messages)
        """
```

**Validation Logic (already built-in):**
- Checks `item.ready_for_upload` (line 250)
- Checks `item.uploaded` (line 268)
- Checks `item.duplicate` (line 274)
- Checks `item.health_status == "Ready"` (implicit via ready_for_upload)

---

## 2. Exact Files Created/Modified

### Files to CREATE

**`pipeline/closet_sync.py`** (~350 lines)
- `ClosetSync` class
- `SyncResult` dataclass
- `SyncStats` dataclass
- Logging utilities

### Files to MODIFY

**`dashboard/dashboard.py`** (+80 lines, modify lines 253-266)
- Add "Closet Sync" section after "Run Settings"
- Add sync button and status label
- Add `_on_sync_closet()` method
- Add `_run_closet_sync_thread()` method
- Add `_update_sync_progress()` method
- Add `_show_sync_complete()` method
- Pass panel references to sync callbacks

**No other files need modification** - existing components are reused as-is.

---

## 3. Exact Method Signatures for ClosetSync

```python
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, sync_playwright
from scraper.discover import DiscoveredListing, discover_closet
from scraper.listing_scraper import scrape_listing
from inventory.inventory_manager import InventoryManager
from inventory.inventory_item import InventoryItem
from inventory.upload_queue import UploadQueueManager
from runtime_paths import DOWNLOADS_DIR, LOGS_DIR, SOURCE_STATE_FILE


@dataclass
class SyncStats:
    """Statistics for sync operation."""
    total_scanned: int = 0
    already_downloaded: int = 0
    new_imported: int = 0
    queued: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class SyncResult:
    """Result of closet sync operation."""
    success: bool
    stats: SyncStats
    error_message: str = ""


class ClosetSync:
    """
    Orchestrates automatic closet synchronization.
    
    Scans source closet, downloads new listings, updates inventory,
    and queues ready items for upload.
    """
    
    def __init__(
        self,
        source_closet_url: str,
        downloads_dir: Path = DOWNLOADS_DIR,
        source_state_file: Path = SOURCE_STATE_FILE,
        progress_callback: Callable[[str], None] | None = None,
        log_file: Path | None = None,
    ) -> None:
        """
        Initialize ClosetSync.
        
        Args:
            source_closet_url: URL of source Poshmark closet
            downloads_dir: Directory for downloaded listings
            source_state_file: Path to Playwright auth state
            progress_callback: Thread-safe callback for progress updates
            log_file: Path to log file (default: logs/closet_sync.log)
        """
        
    def _is_already_downloaded(self, listing_id: str) -> bool:
        """Check if listing already exists in downloads directory."""
        
    def _report_progress(self, message: str) -> None:
        """Report progress via callback and logging."""
        
    def scan_source(self, page: Page) -> list[DiscoveredListing]:
        """
        Scan source closet for all listings.
        
        Args:
            page: Playwright page instance
            
        Returns:
            List of discovered listings
            
        Raises:
            RuntimeError: If browser automation fails
        """
        
    def download_new(
        self,
        page: Page,
        discovered: list[DiscoveredListing],
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """
        Download only listings not already in inventory.
        
        Args:
            page: Playwright page instance
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
        
    def queue_ready(self, new_ids: list[str]) -> int:
        """
        Queue newly downloaded listings that are Ready.
        
        Args:
            new_ids: List of newly downloaded listing IDs
            
        Returns:
            Number of items queued
        """
        
    def run(self) -> SyncResult:
        """
        Execute complete sync workflow.
        
        Returns:
            SyncResult with statistics and errors
        """
```

---

## 4. Source Closet URL/Account Acquisition

### Current Pattern in Codebase
**Location:** `scraper.py:24`
```python
CLOSET_URL = "https://poshmark.com/closet/successboutique"
```

### Implementation Strategy

**Option 1: Configuration File (RECOMMENDED)**
Create `config.json` in APP_DIR:
```json
{
  "source_closet_url": "https://poshmark.com/closet/successboutique"
}
```

**Option 2: Prompt User (FALLBACK)**
If config not found, show input dialog:
```python
from tkinter import simpledialog

def _get_source_closet_url(self) -> str | None:
    """Get source closet URL from config or user."""
    config_file = APP_DIR / "config.json"
    
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            url = config.get("source_closet_url", "").strip()
            if url:
                return url
        except Exception:
            pass
    
    # Prompt user
    url = simpledialog.askstring(
        "Source Closet URL",
        "Enter the source Poshmark closet URL:\n"
        "(e.g., https://poshmark.com/closet/username)",
        parent=self.root,
    )
    
    if url and url.strip():
        # Save for future use
        try:
            config_file.write_text(
                json.dumps({"source_closet_url": url.strip()}, indent=2)
            )
        except Exception:
            pass
        return url.strip()
    
    return None
```

**Dashboard Integration:**
```python
def _on_sync_closet(self) -> None:
    """Handle Sync Closet button click."""
    # Get source URL
    source_url = self._get_source_closet_url()
    if not source_url:
        messagebox.showerror(
            "Configuration Required",
            "Source closet URL is required for sync."
        )
        return
    
    # Show confirmation dialog
    response = messagebox.askyesno(
        "Sync Closet",
        "This will scan the source closet for new listings.\n\n"
        "Only listings not already downloaded will be imported.\n\n"
        "Continue?"
    )
    
    if response:
        self._run_closet_sync_thread(source_url)
```

---

## 5. New Listing Identification Logic

### Listing ID Comparison

```python
def download_new(
    self,
    page: Page,
    discovered: list[DiscoveredListing],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Download only new listings."""
    
    # Build set of existing listing IDs
    existing_ids = set()
    if self.downloads_dir.exists():
        for listing_dir in self.downloads_dir.iterdir():
            if listing_dir.is_dir():
                listing_file = listing_dir / "listing.json"
                if listing_file.exists():
                    existing_ids.add(listing_dir.name)
    
    self._report_progress(
        f"Found {len(discovered)} listings in closet"
    )
    self._report_progress(
        f"{len(existing_ids)} already downloaded"
    )
    
    # Filter to only new, available listings
    to_download = [
        item for item in discovered
        if item.available and item.listing_id not in existing_ids
    ]
    
    self._report_progress(
        f"{len(to_download)} new listings to download"
    )
    
    # Download each new listing
    successful = []
    failed = []
    
    for index, item in enumerate(to_download, start=1):
        try:
            self._report_progress(
                f"Downloading {index}/{len(to_download)}: {item.title[:50]}"
            )
            
            # scrape_listing() automatically saves to disk
            scrape_listing(page, item.url)
            
            successful.append(item.listing_id)
            self.logger.info(
                f"Downloaded: {item.listing_id} - {item.title}"
            )
            
        except Exception as error:
            error_msg = str(error)
            failed.append((item.listing_id, error_msg))
            self.logger.error(
                f"Failed to download {item.listing_id}: {error_msg}"
            )
            # Continue with remaining listings
    
    return successful, failed
```

**Key Points:**
1. Listing ID is the directory name in `downloads/`
2. Existence check: `downloads/{listing_id}/listing.json` exists
3. Only download if `available == True` and not in existing_ids
4. Individual failures don't abort the sync

---

## 6. Sequential vs Parallel Processing

### First Version: SEQUENTIAL ONLY

```python
def download_new(
    self,
    page: Page,
    discovered: list[DiscoveredListing],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Download listings sequentially (one at a time)."""
    
    # ... filtering logic ...
    
    # Sequential download loop
    for index, item in enumerate(to_download, start=1):
        try:
            self._report_progress(
                f"Downloading {index}/{len(to_download)}: {item.title[:50]}"
            )
            
            # Single page, single browser - sequential only
            scrape_listing(page, item.url)
            
            successful.append(item.listing_id)
            
        except Exception as error:
            failed.append((item.listing_id, str(error)))
            # Continue to next listing
    
    return successful, failed
```

**Rationale:**
- Single Playwright page instance
- Simpler error handling
- Easier to debug
- Sufficient for typical closet sizes (< 500 listings)
- Parallel can be added in future version

---

## 7. Exact Callback Signatures and Payloads

### Progress Callback

**Signature:**
```python
Callable[[str], None]
```

**Usage in ClosetSync:**
```python
def _report_progress(self, message: str) -> None:
    """Report progress via callback and logging."""
    self.logger.info(message)
    if self.progress_callback:
        self.progress_callback(message)
```

**Dashboard Implementation:**
```python
def _update_sync_progress(self, message: str) -> None:
    """
    Thread-safe progress update.
    Called from worker thread via self.after().
    """
    self.sync_status_label.config(text=message)
    self.root.update_idletasks()

def _run_closet_sync_thread(self, source_url: str) -> None:
    """Start sync in daemon thread."""
    
    def progress_callback(message: str) -> None:
        """Thread-safe callback - queues UI update."""
        self.root.after(0, self._update_sync_progress, message)
    
    def worker() -> None:
        """Worker thread function."""
        try:
            sync = ClosetSync(
                source_closet_url=source_url,
                progress_callback=progress_callback,
            )
            result = sync.run()
            
            # Queue completion dialog on main thread
            self.root.after(0, self._show_sync_complete, result)
            
        except Exception as error:
            error_msg = str(error)
            self.root.after(
                0,
                messagebox.showerror,
                "Sync Failed",
                f"Closet sync failed:\n\n{error_msg}"
            )
    
    # Start daemon thread
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
```

**Message Examples:**
- `"Scanning closet..."`
- `"Found 12 listings in closet"`
- `"3 already downloaded"`
- `"9 new listings to download"`
- `"Downloading 1/9: Nike Air Max Sneakers Size 10"`
- `"Downloading 2/9: Lululemon Align Leggings Size 6"`
- `"Inventory updated"`
- `"Queued 7 ready listings"`
- `"Sync complete"`

---

## 8. Thread Lifecycle and Cancellation

### Thread Lifecycle

```
┌─────────────────────────────────────────────────────┐
│ Main Thread (UI)                                    │
│                                                     │
│  [Sync Button Clicked]                             │
│         │                                           │
│         ├─► Show confirmation dialog                │
│         │                                           │
│         ├─► Create daemon thread                    │
│         │   thread = Thread(target=worker,          │
│         │                   daemon=True)            │
│         │   thread.start()                          │
│         │                                           │
│         └─► Return (UI remains responsive)          │
│                                                     │
└─────────────────────────────────────────────────────┘
                    │
                    │ Thread spawned
                    ▼
┌─────────────────────────────────────────────────────┐
│ Worker Thread (Daemon)                              │
│                                                     │
│  try:                                               │
│      sync = ClosetSync(...)                         │
│      result = sync.run()                            │
│      root.after(0, show_completion, result)         │
│  except Exception as e:                             │
│      root.after(0, show_error, str(e))              │
│                                                     │
│  [Thread terminates automatically]                  │
└─────────────────────────────────────────────────────┘
```

### Cancellation Handling

**First Version: NO CANCELLATION**

Rationale:
- Sync operations are typically fast (< 5 minutes)
- Cancellation mid-download could corrupt data
- Daemon thread terminates automatically on app close
- User can close app if needed

**Future Enhancement:**
```python
class ClosetSync:
    def __init__(self, ...):
        self._stop_requested = False
    
    def request_stop(self) -> None:
        """Request graceful stop."""
        self._stop_requested = True
    
    def download_new(self, ...):
        for item in to_download:
            if self._stop_requested:
                self.logger.info("Stop requested, aborting sync")
                break
            # ... download logic ...
```

### Window Close Handling

```python
def on_close(self) -> None:
    """Handle window close event."""
    # Daemon threads terminate automatically
    # No special handling needed for sync thread
    
    if self.process:
        # Existing pipeline cleanup
        self.process.terminate()
    
    self.root.destroy()
```

---

## 9. Dashboard Refresh Mechanism

### Panel Refresh Methods

**InventoryPanel:**
```python
# Location: dashboard/inventory_panel.py:534
def refresh(self) -> None:
    """Reload inventory and update display."""
    self.items = self.manager.load_items()
    self._apply_filters()
    self._update_tree()
    self._update_count()
```

**UploadQueuePanel:**
```python
# Location: dashboard/upload_queue_panel.py:329
def refresh(self) -> None:
    """Reload queue state and update display."""
    self.queue_manager.load()
    self._update_summary()
    self._update_tree()
```

### Dashboard Integration

**Store panel references in __init__:**
```python
# dashboard/dashboard.py:372-394
self.inventory_panel = InventoryPanel(inventory_tab)
self.inventory_panel.pack(fill="both", expand=True)

self.upload_queue_panel = UploadQueuePanel(upload_queue_tab)
self.upload_queue_panel.pack(fill="both", expand=True)
```

**Refresh after sync completion:**
```python
def _show_sync_complete(self, result: SyncResult) -> None:
    """Show completion dialog and refresh panels."""
    
    # Refresh panels FIRST
    try:
        self.inventory_panel.refresh()
        self.upload_queue_panel.refresh()
    except Exception as error:
        # Log but don't fail
        print(f"Panel refresh error: {error}")
    
    # Then show dialog
    stats = result.stats
    elapsed_str = self._format_elapsed(stats.elapsed_seconds)
    
    message = (
        f"Closet Sync Complete\n\n"
        f"Listings scanned: {stats.total_scanned}\n"
        f"Already downloaded: {stats.already_downloaded}\n"
        f"New imported: {stats.new_imported}\n"
        f"Queued: {stats.queued}\n"
        f"Failed: {len(stats.failed)}\n\n"
        f"Elapsed time: {elapsed_str}"
    )
    
    if stats.failed:
        message += f"\n\nFailed listings:\n"
        for listing_id, error in stats.failed[:5]:
            message += f"  • {listing_id}: {error[:50]}\n"
        if len(stats.failed) > 5:
            message += f"  ... and {len(stats.failed) - 5} more"
    
    messagebox.showinfo("Sync Complete", message)
    
    # Reset status label
    self.sync_status_label.config(text="Idle")

def _format_elapsed(self, seconds: float) -> str:
    """Format elapsed time as human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"
```

**Thread-Safe Refresh:**
```python
def _run_closet_sync_thread(self, source_url: str) -> None:
    """Start sync in daemon thread."""
    
    def worker() -> None:
        try:
            sync = ClosetSync(
                source_closet_url=source_url,
                progress_callback=lambda msg: self.root.after(
                    0, self._update_sync_progress, msg
                ),
            )
            result = sync.run()
            
            # Queue completion on main thread
            # This ensures panel refresh happens on main thread
            self.root.after(0, self._show_sync_complete, result)
            
        except Exception as error:
            self.root.after(
                0,
                messagebox.showerror,
                "Sync Failed",
                f"Closet sync failed:\n\n{str(error)}"
            )
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
```

---

## 10. Exact Failure Behavior

### One Listing Scrape Fails

**Behavior:** Continue processing remaining listings

```python
def download_new(self, page, discovered):
    successful = []
    failed = []
    
    for index, item in enumerate(to_download, start=1):
        try:
            self._report_progress(f"Downloading {index}/{len(to_download)}")
            scrape_listing(page, item.url)
            successful.append(item.listing_id)
            
        except Exception as error:
            # Log error
            error_msg = str(error)
            self.logger.error(
                f"Failed to download {item.listing_id}: {error_msg}"
            )
            
            # Add to failed list
            failed.append((item.listing_id, error_msg))
            
            # CONTINUE to next listing (don't raise)
    
    return successful, failed
```

### Inventory Reload Fails

**Behavior:** Log error, return empty list, continue sync

```python
def build_inventory(self) -> list[InventoryItem]:
    """Reload inventory from disk."""
    try:
        manager = InventoryManager(self.downloads_dir)
        items = manager.load_items()
        self._report_progress(f"Inventory loaded: {len(items)} items")
        return items
        
    except Exception as error:
        self.logger.error(f"Inventory reload failed: {error}")
        self._report_progress("Warning: Inventory reload failed")
        return []  # Return empty list, don't abort sync
```

### Queue Save Fails

**Behavior:** Log error, report in result, don't abort

```python
def queue_ready(self, new_ids: list[str]) -> int:
    """Queue newly downloaded listings that are Ready."""
    try:
        # Load inventory
        manager = InventoryManager(self.downloads_dir)
        all_items = manager.load_items()
        
        # Filter to new items that are ready
        new_items = [
            item for item in all_items
            if item.listing_id in new_ids
            and item.ready_for_upload
            and not item.uploaded
            and not item.duplicate
        ]
        
        if not new_items:
            self._report_progress("No ready items to queue")
            return 0
        
        # Add to queue
        queue_manager = UploadQueueManager()
        added_count, errors = queue_manager.add_items(new_items)
        
        if errors:
            for error in errors[:3]:
                self.logger.warning(f"Queue error: {error}")
        
        self._report_progress(f"Queued {added_count} ready listings")
        return added_count
        
    except Exception as error:
        self.logger.error(f"Queue operation failed: {error}")
        self._report_progress("Warning: Queue operation failed")
        return 0  # Return 0, don't abort sync
```

### Logging Fails

**Behavior:** Continue silently (logging is non-critical)

```python
def _report_progress(self, message: str) -> None:
    """Report progress via callback and logging."""
    # Try to log, but don't fail if logging fails
    try:
        self.logger.info(message)
    except Exception:
        pass  # Logging failure is non-critical
    
    # Always call progress callback
    if self.progress_callback:
        try:
            self.progress_callback(message)
        except Exception:
            pass  # Callback failure is non-critical
```

### Critical Failures (Abort Sync)

**Scenarios that abort:**
1. Browser fails to launch
2. Source state file not found
3. Source closet URL invalid/unreachable
4. Network completely unavailable

```python
def run(self) -> SyncResult:
    """Execute complete sync workflow."""
    start_time = time.time()
    stats = SyncStats()
    
    try:
        # Validate prerequisites
        if not self.source_state_file.exists():
            raise FileNotFoundError(
                f"Source authentication not found: {self.source_state_file}"
            )
        
        self._report_progress("Starting closet sync...")
        
        # Launch browser
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self.source_state_file)
            )
            page = context.new_page()
            
            try:
                # Scan source closet
                discovered = self.scan_source(page)
                stats.total_scanned = len(discovered)
                
                # Download new listings
                successful, failed = self.download_new(page, discovered)
                stats.new_imported = len(successful)
                stats.failed = failed
                stats.already_downloaded = (
                    stats.total_scanned - len(successful) - len(failed)
                )
                
            finally:
                context.close()
                browser.close()
        
        # Build inventory (non-critical)
        self.build_inventory()
        
        # Queue ready items (non-critical)
        queued = self.queue_ready(successful)
        stats.queued = queued
        
        stats.elapsed_seconds = time.time() - start_time
        self._report_progress("Sync complete")
        
        return SyncResult(success=True, stats=stats)
        
    except Exception as error:
        # Critical failure - abort sync
        stats.elapsed_seconds = time.time() - start_time
        error_msg = str(error)
        self.logger.error(f"Sync failed: {error_msg}", exc_info=True)
        
        return SyncResult(
            success=False,
            stats=stats,
            error_message=error_msg
        )
```

---

## 11. Reuse Existing Logic (No Copying)

### Confirmed Reuse Strategy

**✅ REUSE (Import and call):**
- `scraper.discover.discover_closet()` - Import and call directly
- `scraper.listing_scraper.scrape_listing()` - Import and call directly
- `inventory.inventory_manager.InventoryManager` - Instantiate and use
- `inventory.upload_queue.UploadQueueManager` - Instantiate and use
- `login.open_logged_in_browser()` - NOT USED (we use sync_playwright directly)

**❌ DO NOT COPY:**
- No scraping logic copied
- No upload logic copied
- No inventory logic copied
- No queue logic copied

**Import Statement in `pipeline/closet_sync.py`:**
```python
from scraper.discover import DiscoveredListing, discover_closet
from scraper.listing_scraper import scrape_listing
from inventory.inventory_manager import InventoryManager
from inventory.upload_queue import UploadQueueManager
from runtime_paths import DOWNLOADS_DIR, LOGS_DIR, SOURCE_STATE_FILE
```

---

## 12. Implementation Phases and Estimated Diff Size

### Phase 1: Create `pipeline/closet_sync.py`
**Estimated Size:** ~350 lines

**Structure:**
```
Lines 1-30:    Imports and dataclasses (SyncStats, SyncResult)
Lines 31-80:   ClosetSync.__init__() and helper methods
Lines 81-130:  scan_source() method
Lines 131-220: download_new() method
Lines 221-250: build_inventory() method
Lines 251-300: queue_ready() method
Lines 301-350: run() method and logging setup
```

**Diff Preview:**
```diff
+++ pipeline/closet_sync.py
@@ -0,0 +1,350 @@
+from __future__ import annotations
+
+import logging
+import time
+from dataclasses import dataclass, field
+from pathlib import Path
+from typing import Callable
+
+from playwright.sync_api import Page, sync_playwright
+from scraper.discover import DiscoveredListing, discover_closet
+from scraper.listing_scraper import scrape_listing
+from inventory.inventory_manager import InventoryManager
+from inventory.upload_queue import UploadQueueManager
+from runtime_paths import DOWNLOADS_DIR, LOGS_DIR, SOURCE_STATE_FILE
+
+
+@dataclass
+class SyncStats:
+    """Statistics for sync operation."""
+    total_scanned: int = 0
+    already_downloaded: int = 0
+    new_imported: int = 0
+    queued: int = 0
+    failed: list[tuple[str, str]] = field(default_factory=list)
+    elapsed_seconds: float = 0.0
+
+# ... rest of implementation
```

### Phase 2: Modify `dashboard/dashboard.py`
**Estimated Size:** +80 lines (4 new methods, 1 UI section)

**Changes:**
```diff
--- dashboard/dashboard.py
+++ dashboard/dashboard.py
@@ -8,6 +8,7 @@
 import tkinter as tk
 from pathlib import Path
 from tkinter import messagebox, ttk
+from tkinter import simpledialog
 
 from dashboard.activity_log import ActivityLog
 from dashboard.inventory_panel import InventoryPanel
@@ -24,6 +25,7 @@
 from dashboard.styles import apply_styles
 from dashboard.thumbnail_panel import Thumbn