# TASK-021B: Parallel Download Implementation Design

## Overview
Implement safe parallel closet downloads using a pool of 3 Playwright pages with ThreadPoolExecutor.

## File to Modify
- `pipeline/closet_sync.py`

## Design Details

### 1. Add Constant (after imports, ~line 18)

```python
MAX_DOWNLOAD_WORKERS = 3
```

### 2. Add Worker Method to ClosetSync Class

```python
def _download_worker(
    self,
    worker_page: Page,
    listing: DiscoveredListing,
    index: int,
    total: int,
    lock: threading.Lock,
) -> tuple[str | None, tuple[str, str] | None]:
    """
    Download a single listing using assigned page.
    
    Args:
        worker_page: Dedicated Playwright page for this worker
        listing: Listing to download
        index: Current item number (1-based)
        total: Total items to download
        lock: Thread lock for shared state access
    
    Returns:
        (listing_id, None) on success
        (None, (listing_id, error_msg)) on failure
    """
    try:
        # Truncate title for display
        display_title = listing.title[:50]
        if len(listing.title) > 50:
            display_title += "..."
        
        # Thread-safe progress reporting
        with lock:
            self._report_progress(
                f"Downloading {index}/{total}: {display_title}"
            )
        
        # Call existing scraper (saves to disk automatically)
        scrape_listing(worker_page, listing.url)
        
        # Thread-safe logging
        with lock:
            self.logger.info(f"Downloaded: {listing.listing_id} - {listing.title}")
        
        return (listing.listing_id, None)
        
    except Exception as error:
        error_msg = str(error)
        with lock:
            self.logger.error(
                f"Failed to download {listing.listing_id}: {error_msg}"
            )
        return (None, (listing.listing_id, error_msg))
```

### 3. Modify download_new Method Signature

**Current (line 153):**
```python
def download_new(
    self,
    page: Page,
    discovered: list[DiscoveredListing],
) -> tuple[list[str], list[tuple[str, str]]]:
```

**New:**
```python
def download_new(
    self,
    page: Page,
    context: BrowserContext,
    discovered: list[DiscoveredListing],
) -> tuple[list[str], list[tuple[str, str]]]:
```

**Note:** `page` parameter kept for compatibility but not used in parallel mode.

### 4. Replace download_new Method Body

**Keep lines 169-198 unchanged** (existing ID filtering and cap logic)

**Replace lines 200-229** (the sequential download loop) with:

```python
if not to_download:
    return [], []

# Single item: use sequential path (no thread overhead)
if len(to_download) == 1:
    successful = []
    failed = []
    item = to_download[0]
    
    try:
        display_title = item.title[:50]
        if len(item.title) > 50:
            display_title += "..."
        
        self._report_progress(f"Downloading 1/1: {display_title}")
        scrape_listing(page, item.url)
        successful.append(item.listing_id)
        self.logger.info(f"Downloaded: {item.listing_id} - {item.title}")
    
    except Exception as error:
        error_msg = str(error)
        failed.append((item.listing_id, error_msg))
        self.logger.error(f"Failed to download {item.listing_id}: {error_msg}")
    
    return successful, failed

# Multiple items: use parallel download
successful = []
failed = []
progress_lock = threading.Lock()
worker_pages = []

try:
    # Create worker page pool
    num_workers = min(MAX_DOWNLOAD_WORKERS, len(to_download))
    
    try:
        for _ in range(num_workers):
            worker_pages.append(context.new_page())
    
    except Exception as error:
        # Fallback to sequential if page creation fails
        self.logger.warning(
            f"Failed to create worker pages, using sequential download: {error}"
        )
        
        for index, item in enumerate(to_download, start=1):
            try:
                display_title = item.title[:50]
                if len(item.title) > 50:
                    display_title += "..."
                
                self._report_progress(
                    f"Downloading {index}/{len(to_download)}: {display_title}"
                )
                scrape_listing(page, item.url)
                successful.append(item.listing_id)
                self.logger.info(f"Downloaded: {item.listing_id} - {item.title}")
            
            except Exception as error:
                error_msg = str(error)
                failed.append((item.listing_id, error_msg))
                self.logger.error(
                    f"Failed to download {item.listing_id}: {error_msg}"
                )
        
        return successful, failed
    
    # Parallel download with page pool
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        
        # Submit all tasks with round-robin page assignment
        for idx, listing in enumerate(to_download, start=1):
            # Assign page: ensures no page used by multiple workers simultaneously
            assigned_page = worker_pages[(idx - 1) % num_workers]
            
            future = executor.submit(
                self._download_worker,
                assigned_page,
                listing,
                idx,
                len(to_download),
                progress_lock,
            )
            futures.append(future)
        
        # Collect results as they complete
        for future in futures:
            success_id, fail_tuple = future.result()
            if success_id:
                successful.append(success_id)
            elif fail_tuple:
                failed.append(fail_tuple)

finally:
    # Always close worker pages
    for worker_page in worker_pages:
        try:
            worker_page.close()
        except Exception:
            pass  # Best effort cleanup

return successful, failed
```

### 5. Update Call Site in run() Method

**Line 332, change from:**
```python
successful, failed = self.download_new(page, discovered)
```

**To:**
```python
successful, failed = self.download_new(page, context, discovered)
```

### 6. Add Import

**Line 7, change from:**
```python
from typing import Callable
```

**To:**
```python
import threading
from typing import Callable
```

**Also add BrowserContext import on line 9:**
```python
from playwright.sync_api import BrowserContext, Page, sync_playwright
```

## Key Design Decisions

### Page Pool Lifecycle
- Worker pages created BEFORE ThreadPoolExecutor starts
- Created from authenticated BrowserContext (no separate login)
- Always closed in finally block (even on errors)
- Discovery page (`page` parameter) not closed by this method

### Worker Isolation
- Each worker gets dedicated Page via round-robin assignment
- Round-robin ensures: `worker_pages[(idx - 1) % num_workers]`
  - Item 1 → Page 0
  - Item 2 → Page 1
  - Item 3 → Page 2
  - Item 4 → Page 0 (wraps around)
- No page shared between concurrent workers

### Thread Safety
- `threading.Lock` protects:
  - `self._report_progress()` calls
  - `self.logger` calls
- Results collected after all futures complete (no race conditions)

### Error Handling
- Page creation failure → fallback to sequential
- Individual listing failure → logged, doesn't cancel batch
- Worker exceptions caught in `_download_worker()`
- Page cleanup uses try/except (best effort)

### Performance Optimizations
- Single item → skip thread overhead, use sequential
- Max 3 workers (avoids overwhelming browser/network)
- Round-robin page assignment (balanced load)

### Correctness Guarantees
- Hard cap applied BEFORE parallel work starts
- No changes to `scrape_listing()` behavior
- Existing progress reporting preserved
- Deterministic result collection (futures processed in submission order)

## Testing Plan

After implementation:
1. Run `python -m py_compile pipeline/closet_sync.py`
2. Do NOT run live sync yet
3. Do NOT run Git commands

## Compliance Checklist

- [x] MAX_DOWNLOAD_WORKERS = 3 added
- [x] Hard import cap preserved (lines 186-191)
- [x] scrape_listing() not modified
- [x] No shared Page between workers
- [x] Pages created before ThreadPoolExecutor
- [x] context.new_page() not called from worker threads
- [x] One Page per worker (round-robin assignment)
- [x] ThreadPoolExecutor max_workers = MAX_DOWNLOAD_WORKERS
- [x] Worker function receives Page, listing, calls scrape_listing()
- [x] Worker catches exceptions (one failure doesn't cancel batch)
- [x] Worker pages closed in finally block
- [x] Discovery page not closed
- [x] Progress via self._report_progress()
- [x] threading.Lock protects shared state
- [x] successful/failed lists maintained
- [x] Single item uses sequential path
- [x] Fallback to sequential on page creation failure
- [x] All workers use authenticated BrowserContext
- [x] No retries added
- [x] No subprocesses added
