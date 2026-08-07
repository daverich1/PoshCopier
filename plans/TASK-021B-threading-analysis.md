# TASK-021B: Threading Analysis and Architecture Comparison

## Critical Issues Identified

### Issue 1: Round-Robin Page Assignment is NOT Exclusive

**Problem:**
```python
assigned_page = worker_pages[idx % num_workers]
executor.submit(worker_func, assigned_page, ...)
```

This does NOT guarantee exclusive page ownership. Example timeline:
- t=0: Task 1 (Page A), Task 2 (Page B), Task 3 (Page C) start
- t=5: Task 2 finishes
- t=6: Executor starts Task 4 → assigned Page A (idx=4, 4%3=1, but Page A is idx 0)
- **RACE CONDITION**: Task 1 and Task 4 both use Page A simultaneously

**Root Cause:** ThreadPoolExecutor reuses threads. When a worker finishes, it picks up the next task immediately. Round-robin assignment is based on task index, not worker thread identity.

### Issue 2: Playwright Sync API Threading Model

## A. Is sync Playwright Page safe to use from another thread?

**Answer: NO - Playwright sync API is NOT thread-safe.**

**Evidence:**
1. Playwright sync API uses a single event loop per `sync_playwright()` context
2. Each Page/BrowserContext is bound to that event loop
3. Python Playwright sync API documentation states: "Sync API is not thread-safe"
4. The sync API is a wrapper around async API using `greenlet` for synchronous execution
5. All operations on a Page must occur in the same thread that created the `sync_playwright()` context

**Implications:**
- Page created in ClosetSync thread CANNOT be safely used from ThreadPoolExecutor worker threads
- BrowserContext created in ClosetSync thread CANNOT be safely shared across threads
- Attempting cross-thread usage may cause:
  - Deadlocks
  - Segmentation faults
  - Undefined behavior
  - Silent failures

## B. Is sharing one BrowserContext across threads supported?

**Answer: NO**

Same reasoning as above. BrowserContext is bound to the event loop of the thread that created it.

## C. Architecture Alternatives Analysis

### Option 1: One Playwright Instance Per Worker Thread

**Description:**
Each worker thread creates its own `sync_playwright()` → browser → context → page using the same `storage_state` file for authentication.

```python
def worker_thread(listing, storage_state_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        try:
            scrape_listing(page, listing.url)
        finally:
            context.close()
            browser.close()
```

**Safety:** ✅ SAFE
- Each thread has isolated Playwright instance
- No shared state between threads
- Each Page/Context bound to its own thread

**Required Code Changes:** MODERATE
- Modify worker function to create full Playwright stack
- Pass `storage_state_path` instead of Page
- Add proper cleanup in worker
- Modify `download_new()` to use ThreadPoolExecutor without page pool

**Authentication Handling:** ✅ SIMPLE
- All workers read same `source_state.json` file
- Playwright loads authentication state independently per context
- No coordination needed

**Memory Overhead:** ⚠️ HIGH
- 3 browsers × ~100-150 MB each = 300-450 MB
- 3 contexts × ~20-30 MB each = 60-90 MB
- Total: ~400-550 MB additional memory

**Compatibility with scrape_listing():** ✅ PERFECT
- No changes needed to `scrape_listing()`
- Receives Page object as expected
- All existing behavior preserved

**Estimated Complexity:** MODERATE
- Implementation: 50-75 lines of code changes
- Testing: Straightforward
- Risk: Low (well-understood pattern)

**Pros:**
- Thread-safe by design
- Simple authentication
- No changes to scraper
- Proven pattern

**Cons:**
- High memory usage
- Slower startup (3 browser launches)
- More resource intensive

---

### Option 2: Separate Subprocess Workers

**Description:**
Use `multiprocessing.Pool` or `subprocess` to run scraper in separate processes.

```python
def subprocess_worker(listing_url, storage_state_path):
    # Each subprocess imports and runs scraper
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        try:
            scrape_listing(page, listing_url)
        finally:
            context.close()
            browser.close()

# In main process:
with multiprocessing.Pool(3) as pool:
    pool.starmap(subprocess_worker, tasks)
```

**Safety:** ✅ SAFE
- Complete process isolation
- No shared memory
- Each process has own Python interpreter

**Required Code Changes:** HIGH
- Create subprocess entry point
- Implement IPC for progress reporting
- Handle subprocess failures
- Coordinate result collection
- May need separate script file

**Authentication Handling:** ✅ SIMPLE
- Same as Option 1
- Each subprocess reads `source_state.json`

**Memory Overhead:** ⚠️ VERY HIGH
- 3 processes × full Python interpreter = ~150-200 MB
- 3 browsers × ~100-150 MB = 300-450 MB
- Total: ~500-700 MB additional memory

**Compatibility with scrape_listing():** ✅ PERFECT
- No changes needed
- Each subprocess imports and uses existing code

**Estimated Complexity:** HIGH
- Implementation: 100-150 lines
- IPC complexity for progress updates
- Error handling across process boundaries
- Testing more complex
- Risk: Medium

**Pros:**
- Maximum isolation
- Crash in one worker doesn't affect others
- True parallelism (no GIL)

**Cons:**
- Highest memory usage
- Complex IPC for progress reporting
- Slower startup
- More moving parts
- Overkill for this use case

---

### Option 3: Async Playwright in One Event Loop

**Description:**
Convert to async Playwright API, run all downloads concurrently in single event loop.

```python
async def download_worker(page, listing):
    await page.goto(listing.url)
    # ... async scraping ...

async def download_all(context, listings):
    # Create page pool
    pages = [await context.new_page() for _ in range(3)]
    
    # Process in batches of 3
    for i in range(0, len(listings), 3):
        batch = listings[i:i+3]
        tasks = [download_worker(pages[j], listing) 
                 for j, listing in enumerate(batch)]
        await asyncio.gather(*tasks)
    
    # Cleanup
    for page in pages:
        await page.close()
```

**Safety:** ✅ SAFE
- Single thread, single event loop
- No threading issues
- Cooperative concurrency

**Required Code Changes:** ⚠️ VERY HIGH
- Convert `scrape_listing()` to async (100+ lines)
- Convert all Playwright calls to async/await
- Convert `download_new()` to async
- Convert `run()` to async or use `asyncio.run()`
- May need to convert other methods
- All callers must handle async

**Authentication Handling:** ✅ SIMPLE
- Same context, same authentication
- No coordination needed

**Memory Overhead:** ✅ LOW
- Single browser
- 3 pages × ~10-20 MB = 30-60 MB
- Most efficient option

**Compatibility with scrape_listing():** ❌ REQUIRES REWRITE
- Must convert entire function to async
- All Playwright calls change: `page.goto()` → `await page.goto()`
- All helper functions must be async
- Breaking change to API

**Estimated Complexity:** VERY HIGH
- Implementation: 200-300 lines changed
- Must convert entire scraper module
- Testing complex (async testing)
- Risk: High (major refactor)

**Pros:**
- Lowest memory usage
- True concurrency without threads
- Single browser instance
- Most efficient resource usage

**Cons:**
- Massive code changes
- Breaking API changes
- High risk of bugs
- Long development time
- Requires async expertise

---

### Option 4: Keep Downloads Sequential

**Description:**
Current implementation - download one listing at a time.

**Safety:** ✅ SAFE
- No concurrency issues
- Well-tested

**Required Code Changes:** ✅ NONE
- Already implemented

**Authentication Handling:** ✅ SIMPLE
- Already working

**Memory Overhead:** ✅ MINIMAL
- Single browser, single page

**Compatibility with scrape_listing():** ✅ PERFECT
- No changes needed

**Estimated Complexity:** ✅ TRIVIAL
- No work required

**Pros:**
- Zero risk
- Zero development time
- Proven stable
- Simple to understand

**Cons:**
- Slower for large batches
- No parallelism benefits
- User requested speedup

---

## Comparison Matrix

| Criterion | Option 1: Thread-Per-Browser | Option 2: Subprocess | Option 3: Async | Option 4: Sequential |
|-----------|------------------------------|----------------------|-----------------|----------------------|
| **Thread Safety** | ✅ Safe | ✅ Safe | ✅ Safe | ✅ Safe |
| **Code Changes** | Moderate (50-75 lines) | High (100-150 lines) | Very High (200-300 lines) | None |
| **Memory Usage** | High (400-550 MB) | Very High (500-700 MB) | Low (30-60 MB) | Minimal |
| **Complexity** | Moderate | High | Very High | Trivial |
| **Risk** | Low | Medium | High | None |
| **scrape_listing() Changes** | None | None | Complete rewrite | None |
| **Development Time** | 2-4 hours | 4-8 hours | 16-24 hours | 0 hours |
| **Speedup** | ~3x | ~3x | ~3x | 1x (baseline) |
| **Maintenance** | Easy | Medium | Hard | Easy |

---

## RECOMMENDED ARCHITECTURE: Option 1 (Thread-Per-Browser)

### Rationale

**Best balance of:**
1. **Safety**: Fully thread-safe, no shared Playwright objects
2. **Simplicity**: No changes to `scrape_listing()` or scraper module
3. **Feasibility**: Moderate code changes, low risk
4. **Performance**: Achieves desired 3x speedup
5. **Compatibility**: Works with existing codebase

**Why not others:**
- **Option 2 (Subprocess)**: Overkill, higher memory, complex IPC, no significant benefit over Option 1
- **Option 3 (Async)**: Too risky, massive refactor, breaks existing API, long development time
- **Option 4 (Sequential)**: Doesn't meet user's speedup requirement

### Implementation Strategy for Option 1

**Architecture:**
```
ClosetSync Thread (main)
├── ThreadPoolExecutor (max_workers=3)
    ├── Worker Thread 1
    │   └── sync_playwright() → browser → context → page
    ├── Worker Thread 2
    │   └── sync_playwright() → browser → context → page
    └── Worker Thread 3
        └── sync_playwright() → browser → context → page
```

**Key Design:**
1. Each worker thread creates full Playwright stack
2. Worker receives: `(listing, storage_state_path, index, total, lock)`
3. Worker creates browser, scrapes, closes browser, returns result
4. Main thread collects results from futures
5. No shared Playwright objects between threads

**Memory Trade-off:**
- 400-550 MB additional memory is acceptable for:
  - Desktop application (not server)
  - Temporary during sync operation
  - Modern systems have 8-16 GB RAM
  - User explicitly requested speedup

**Code Structure:**
```python
def _download_worker(
    self,
    listing: DiscoveredListing,
    storage_state_path: Path,
    index: int,
    total: int,
    lock: threading.Lock,
) -> tuple[str | None, tuple[str, str] | None]:
    """Worker that creates its own browser."""
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(storage_state_path),
                viewport={"width": 1440, "height": 1000},
            )
            page = context.new_page()
            
            try:
                # Thread-safe progress
                with lock:
                    display_title = listing.title[:50]
                    if len(listing.title) > 50:
                        display_title += "..."
                    self._report_progress(
                        f"Downloading {index}/{total}: {display_title}"
                    )
                
                # Scrape (saves to disk)
                scrape_listing(page, listing.url)
                
                with lock:
                    self.logger.info(f"Downloaded: {listing.listing_id}")
                
                return (listing.listing_id, None)
            
            finally:
                context.close()
                browser.close()
    
    except Exception as error:
        with lock:
            self.logger.error(f"Failed: {listing.listing_id}: {error}")
        return (None, (listing.listing_id, str(error)))

def download_new(self, page, discovered):
    # ... existing filtering logic ...
    
    if len(to_download) == 1:
        # Sequential for single item
        # ... existing code ...
    
    # Parallel download
    successful = []
    failed = []
    lock = threading.Lock()
    
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        futures = [
            executor.submit(
                self._download_worker,
                listing,
                self.source_state_file,
                idx,
                len(to_download),
                lock,
            )
            for idx, listing in enumerate(to_download, start=1)
        ]
        
        for future in futures:
            success_id, fail_tuple = future.result()
            if success_id:
                successful.append(success_id)
            elif fail_tuple:
                failed.append(fail_tuple)
    
    return successful, failed
```

**Benefits:**
- ✅ No page pool management complexity
- ✅ No exclusive ownership tracking needed
- ✅ Each worker fully independent
- ✅ Clean resource lifecycle
- ✅ Simple error handling
- ✅ No changes to scraper

**Trade-offs Accepted:**
- ⚠️ Higher memory usage (acceptable for desktop app)
- ⚠️ Slower startup per task (3-4 seconds per browser launch, but parallelized)

---

## Conclusion

**Recommended: Option 1 - Thread-Per-Browser**

This architecture:
1. Solves both identified concurrency issues
2. Maintains thread safety
3. Requires moderate, manageable code changes
4. Preserves existing scraper API
5. Achieves desired performance improvement
6. Has acceptable memory overhead for desktop application
7. Low risk, straightforward implementation

**Next Steps:**
1. Get approval for Option 1 architecture
2. Implement thread-per-browser design
3. Test with syntax check
4. Document memory usage expectations
