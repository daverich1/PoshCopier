# PoshCopier - Coding Standards

## Python Version

- **Target**: Python 3.10+
- **Future Imports**: All modules use `from __future__ import annotations` for postponed evaluation of type hints

## Code Style

### Type Hints

**Required** for all function signatures:

```python
def scrape_listing(
    page: Page,
    listing_url: str,
) -> dict[str, Any]:
    ...
```

**Use modern syntax** with `from __future__ import annotations`:
- `list[str]` instead of `List[str]`
- `dict[str, Any]` instead of `Dict[str, Any]`
- `Path | None` instead of `Optional[Path]`

### Function Definitions

**Multi-line parameter formatting**:

```python
def function_with_many_params(
    param1: str,
    param2: int,
    param3: bool = False,
) -> ReturnType:
    """Docstring here."""
    ...
```

**Return type annotations** are mandatory:

```python
def get_value() -> str:
    return "value"

def no_return() -> None:
    print("side effect only")
```

### Imports

**Order**:
1. Future imports
2. Standard library
3. Third-party packages
4. Local modules

**Example**:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from scraper.parser import extract_title
from runtime_paths import DOWNLOADS_DIR
```

### Naming Conventions

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: Prefix with `_` (e.g., `_internal_helper()`)

**Examples**:

```python
SELL_URL = "https://poshmark.com/create-listing"

class InventoryManager:
    def load_items(self) -> list[InventoryItem]:
        ...
    
    def _build_item(self, payload: dict[str, Any]) -> InventoryItem:
        ...
```

### Path Handling

**Always use `pathlib.Path`**, never string concatenation:

```python
from pathlib import Path

listing_dir = DOWNLOADS_DIR / listing_id
listing_file = listing_dir / "listing.json"

if listing_file.exists():
    content = listing_file.read_text(encoding="utf-8")
```

### String Formatting

**Prefer f-strings** for readability:

```python
# Good
message = f"Processing listing {listing_id}: {title}"

# Avoid
message = "Processing listing {}: {}".format(listing_id, title)
```

### Error Handling

**Specific exceptions** with meaningful messages:

```python
if not title:
    raise RuntimeError(
        "The listing title is missing."
    )

try:
    payload = json.loads(content)
except json.JSONDecodeError as error:
    raise ValueError(
        f"Invalid JSON in {listing_file}"
    ) from error
```

**Graceful degradation** in loops:

```python
for listing_url in listing_urls:
    try:
        scrape_listing(page, listing_url)
    except Exception as error:
        log_error(error)
        continue  # Process next listing
```

### Data Classes

**Use `@dataclass`** for data structures:

```python
from dataclasses import dataclass, field

@dataclass
class InventoryItem:
    listing_id: str
    title: str
    brand: str
    price: str
    uploaded: bool = False
    health_messages: list[str] = field(default_factory=list)
```

**Use `slots=True`** for performance when appropriate:

```python
@dataclass(slots=True)
class DiscoveredListing:
    listing_id: str
    url: str
    title: str
```

**Use `frozen=True`** for immutable data:

```python
@dataclass(frozen=True, slots=True)
class PipelineControlState:
    paused: bool = False
    stop_after_current: bool = False
```

### File I/O

**Always specify encoding**:

```python
# Reading
content = file_path.read_text(encoding="utf-8")

# Writing
file_path.write_text(content, encoding="utf-8")
```

**Atomic writes** for critical files:

```python
import os
import tempfile

def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        
        Path(temp_name).replace(path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
```

### JSON Handling

**Consistent formatting**:

```python
json.dump(
    payload,
    handle,
    indent=2,
    ensure_ascii=False,
)
```

**Validation after loading**:

```python
payload = json.loads(content)

if not isinstance(payload, dict):
    raise TypeError("Expected a JSON object")

listing_id = str(payload.get("listing_id", "")).strip()
if not listing_id:
    raise ValueError("listing_id is required")
```

### Browser Automation

**Multiple selector strategies** for robustness:

```python
def fill_title(page: Page, title: str) -> None:
    selectors = [
        'input[placeholder*="selling" i]',
        'input[name="title"]',
        'input[id*="title" i]',
    ]
    
    for selector in selectors:
        if try_fill(page.locator(selector), title):
            print("Title entered.")
            return
    
    raise RuntimeError("Could not find the title field.")
```

**Wait for elements**:

```python
field.wait_for(state="visible", timeout=5000)
field.scroll_into_view_if_needed()
field.fill(value)
```

### Logging and Status

**Structured status events** for dashboard:

```python
def emit_status(key: str, value: str) -> None:
    """Emit STATUS:KEY=VALUE for dashboard parsing."""
    print(f"STATUS:{key}={value}", flush=True)

# Usage
emit_status("current_listing", listing_id)
emit_status("progress", "45")
```

**Print statements** for user feedback:

```python
print(f"Scraping: {listing_url}")
print("Title entered.")
print(f"✓ Listing uploaded: {title}")
```

### Configuration

**Use constants** at module level:

```python
SELL_URL = "https://poshmark.com/create-listing"
DESTINATION_CLOSET_URL = "https://poshmark.com/closet/dveshop"
DEFAULT_POLL_SECONDS = 0.5
```

**Runtime paths** from centralized module:

```python
from runtime_paths import (
    APP_DIR,
    DOWNLOADS_DIR,
    LOGS_DIR,
    DATABASE_FILE,
)
```

## Project-Specific Patterns

### Listing ID Extraction

```python
def extract_listing_id(listing_url: str) -> str:
    clean_url = clean_listing_url(listing_url)
    return clean_url.rsplit("-", 1)[-1]
```

### URL Canonicalization

```python
def clean_listing_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path.rstrip("/"),
        "",  # No query
        "",  # No fragment
    ))
```

### Filename Sanitization

```python
def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return cleaned.strip("_")[:80] or "unknown"
```

### Timestamp Generation

```python
from datetime import datetime, timezone

def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

## GUI Standards

### Tkinter Widgets

**Use ttk widgets** for modern appearance:

```python
from tkinter import ttk

frame = ttk.Frame(parent, padding=12)
label = ttk.Label(frame, text="Status:", style="Title.TLabel")
button = ttk.Button(frame, text="Start", command=self.on_start)
```

**Configure grid weights** for responsive layouts:

```python
frame.columnconfigure(1, weight=1)
frame.rowconfigure(0, weight=1)
```

### Event Handling

**Bind cleanup to window close**:

```python
self.root.protocol("WM_DELETE_WINDOW", self.on_close)
```

**Poll queues periodically**:

```python
def _poll_output_queue(self) -> None:
    try:
        while True:
            line = self.output_queue.get_nowait()
            self.process_line(line)
    except queue.Empty:
        pass
    
    self.root.after(100, self._poll_output_queue)
```

## Testing Patterns

### Dry Run Mode

Support dry run mode to test without side effects:

```python
if mode == "dry_run":
    print("[DRY RUN] Would upload listing")
    return

# Actual upload code
publish_listing(page)
```

### Error Simulation

```python
if "--test-error" in sys.argv:
    raise RuntimeError("Simulated error for testing")
```

## Documentation

### Module Docstrings

Not consistently used in current codebase, but recommended for complex modules.

### Function Docstrings

Use for complex functions:

```python
def emit_status(key: str, value: str) -> None:
    """Emit a structured dashboard event as STATUS:KEY=VALUE."""
    print(f"STATUS:{key}={value}", flush=True)
```

### Inline Comments

Use sparingly for non-obvious logic:

```python
# Wait for upload to complete before proceeding
page.wait_for_timeout(2500)
```

## Build and Packaging

### PyInstaller Specs

- Separate specs for dashboard and pipeline
- Include data files (assets, icons)
- Configure console visibility
- Embed dependencies

### Version Control

**Ignore runtime files** (see [`.gitignore`](../.gitignore)):
- `__pycache__/`, `*.pyc`
- `downloads/`, `logs/`
- `poshcopier.db`
- `source_state.json`, `destination_state.json`
- `build/`, `dist/`, `*.spec`
- `pw-browsers/`

## Performance Considerations

- Use `slots=True` in dataclasses for memory efficiency
- Cache thumbnails to avoid regeneration
- Atomic file writes to prevent corruption
- Single-threaded pipeline to avoid race conditions
- Lazy loading of inventory items

## Security Considerations

- Store authentication in local JSON files (not in code)
- Never commit `source_state.json` or `destination_state.json`
- Validate all user inputs
- Sanitize filenames to prevent path traversal
- Use HTTPS for all Poshmark requests
