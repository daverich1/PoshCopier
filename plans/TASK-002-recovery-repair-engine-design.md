# TASK-002: Recovery Repair Engine Design (REVISED)

## Executive Summary

This document outlines a **simplified Recovery Repair Engine** that recreates missing `listing.json` files in broken inventory folders. The engine leverages existing scraping infrastructure to re-fetch listing data from source URLs.

**Scope:** Initial implementation supports only folders with **missing listing.json** (not corrupted or incomplete JSON).

---

## Problem Statement

The current recovery system ([`inventory/recovery_manager.py`](../inventory/recovery_manager.py:1)) can:
- ✅ Detect broken folders (missing or invalid `listing.json`)
- ✅ Display broken folders in the Recovery Panel UI
- ✅ Delete safe-to-remove broken folders
- ❌ **Cannot repair** broken folders by recreating missing data

**Failure Scenario Addressed:**
1. **Missing `listing.json`** - Folder exists with images but no metadata file

**Future Scenarios (Not in this task):**
- Corrupted `listing.json` - Invalid JSON syntax
- Incomplete `listing.json` - Valid JSON but missing required fields

---

## Current System Analysis

### Existing Components

#### 1. Detection System
- **File:** [`inventory/recovery_manager.py`](../inventory/recovery_manager.py:1)
- **Class:** `RecoveryManager`
- **Key Methods:**
  - [`scan_broken_folders()`](../inventory/recovery_manager.py:41) - Identifies broken folders
  - [`_build_recovery_item()`](../inventory/recovery_manager.py:76) - Creates recovery metadata

#### 2. Health Validation
- **File:** [`inventory/inventory_health.py`](../inventory/inventory_health.py:1)
- **Class:** `InventoryHealth`
- **Key Methods:**
  - [`scan_listing()`](../inventory/inventory_health.py:105) - Validates listing completeness
  - Required fields: `title`, `description`, `brand`, `price`, `category`, `condition`, `source_url`, `size`

#### 3. Scraping Engine
- **File:** [`scraper/listing_scraper.py`](../scraper/listing_scraper.py:1)
- **Key Function:** [`scrape_listing(page, listing_url)`](../scraper/listing_scraper.py:356)
- **Capabilities:**
  - Fetches listing from source URL
  - Extracts all required fields
  - Downloads images
  - Saves complete listing JSON

#### 4. Save/Load Infrastructure
- **File:** [`scraper/save_listing.py`](../scraper/save_listing.py:1)
- **Key Functions:**
  - [`save_listing(listing)`](../scraper/save_listing.py:118) - Atomic JSON write
  - Merges existing data with new data (preserves `copied` status)

---

## Proposed Architecture

### Design Principles

1. **Non-Destructive** - Preserve existing images
2. **Source-Based** - Re-scrape from original URL
3. **Simple** - One listing at a time with user confirmation
4. **Safe** - Validate before saving
5. **Focused** - Only handle missing listing.json

### Repair Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User selects broken folder in Recovery Panel            │
│    - Only enabled if problem is "Missing listing.json"     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Try to determine source URL                              │
│    - Extract from folder name (if it's a listing ID)       │
│    - If not found, prompt user with simpledialog           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Confirm repair with user (messagebox.askyesno)          │
│    - Show folder name and source URL                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Launch browser and re-scrape listing                     │
│    - Use existing scrape_listing() function                 │
│    - Verify listing is available                            │
│    - Extract all metadata                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Merge with existing images                               │
│    - Preserve existing local images if present              │
│    - Don't re-download images                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Save repaired listing.json                               │
│    - Use existing save_listing() function                   │
│    - Atomic write with safety                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Validate repaired listing                                │
│    - Run InventoryHealth.scan_listing()                     │
│    - Verify all required fields present                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Show result and refresh                                  │
│    - Success: messagebox.showinfo, refresh panel           │
│    - Failure: messagebox.showerror                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Required Functions

### New Module: `inventory/repair_engine.py`

**Simplified Public API:**

```python
class RepairEngine:
    """Repairs broken inventory folders by re-scraping source listings."""
    
    def __init__(self, downloads_dir: Path = DOWNLOADS_DIR):
        """Initialize repair engine with downloads directory."""
        
    def repair(
        self,
        item: RecoveryItem,
        source_url: str | None = None,
    ) -> tuple[bool, str]:
        """
        Repair a broken listing by re-scraping from source.
        
        Args:
            item: RecoveryItem to repair (must have missing listing.json)
            source_url: Source URL to scrape from (required if not auto-detected)
            
        Returns:
            Tuple of (success: bool, message: str)
            - success=True: Repair succeeded, folder is now valid
            - success=False: Repair failed, message contains reason
            
        Workflow:
            1. Validate item has missing listing.json
            2. Determine source URL (auto-detect or use provided)
            3. Launch browser and scrape listing
            4. Preserve existing images if present
            5. Save listing.json using save_listing()
            6. Validate repair with InventoryHealth
            7. Return result
        """
```

**Internal Helper Methods:**

```python
    def _extract_source_url(self, item: RecoveryItem) -> str | None:
        """
        Extract source URL from folder name.
        
        Strategy:
        1. Assume folder name is the listing ID
        2. Construct URL: https://poshmark.com/listing/{listing_id}
        3. Return None if folder name doesn't look like a listing ID
        """
        
    def _is_valid_listing_id(self, folder_name: str) -> bool:
        """
        Check if folder name looks like a valid listing ID.
        
        Listing IDs are typically alphanumeric, 20-24 characters.
        """
        
    def _construct_source_url(self, listing_id: str) -> str:
        """
        Construct source URL from listing ID.
        
        Pattern: https://poshmark.com/listing/{listing_id}
        """
        
    def _get_existing_images(self, folder_path: Path) -> list[str]:
        """
        Get list of existing image files in folder.
        
        Returns absolute paths to existing images.
        """
        
    def _merge_with_existing_images(
        self,
        scraped_listing: dict,
        existing_images: list[str],
    ) -> dict:
        """
        Merge scraped data with existing local images.
        
        If folder has existing images, use them instead of scraped images.
        This prevents re-downloading images that already exist.
        """
        
    def _validate_repair(self, listing_dir: Path) -> tuple[bool, str]:
        """
        Validate repaired listing using InventoryHealth.
        
        Returns:
            (success: bool, message: str)
        """
```

**No Data Classes Needed:**
- Use simple tuple return `(bool, str)` for repair result
- Reuse existing `RecoveryItem` and `ListingHealth` classes

---

## Reusable Existing Code

### 1. Scraping Infrastructure ✅
- **Function:** [`scrape_listing(page, listing_url)`](../scraper/listing_scraper.py:356)
- **Usage:** Core repair logic - re-fetch all listing data
- **No modifications needed**

### 2. Save Infrastructure ✅
- **Function:** [`save_listing(listing)`](../scraper/save_listing.py:118)
- **Usage:** Atomic write of repaired JSON
- **Already handles merging with existing data**

### 3. Health Validation ✅
- **Class:** [`InventoryHealth`](../inventory/inventory_health.py:98)
- **Method:** [`scan_listing(listing_dir)`](../inventory/inventory_health.py:105)
- **Usage:** Validate repair was successful

### 4. Recovery Detection ✅
- **Class:** [`RecoveryManager`](../inventory/recovery_manager.py:31)
- **Method:** [`scan_broken_folders()`](../inventory/recovery_manager.py:41)
- **Usage:** Identify candidates for repair

### 5. Browser Management ✅
- **File:** [`login.py`](../login.py:1)
- **Function:** `open_logged_in_browser(playwright, state_file)`
- **Usage:** Get authenticated browser for scraping

---

## UI Changes Required

### Recovery Panel Enhancements
**File:** [`dashboard/recovery_panel.py`](../dashboard/recovery_panel.py:1)

#### New UI Elements:
```python
# In __init__, after creating delete_button:
self.repair_button = ttk.Button(
    actions,
    text="Repair Listing",
    command=self.repair_selected_listing,
    state="disabled",
)
self.repair_button.pack(side="left", padx=(8, 0))

# In __init__, add RepairEngine instance:
from inventory.repair_engine import RepairEngine
self.repair_engine = RepairEngine()
```

#### New Method:
```python
def repair_selected_listing(self) -> None:
    """
    Repair the selected broken listing.
    
    Workflow:
    1. Validate item is selected and has missing listing.json
    2. Try to extract source URL automatically
    3. If no URL, use tkinter.simpledialog.askstring() to prompt user
    4. Use messagebox.askyesno() to confirm repair
    5. Launch browser and call repair_engine.repair()
    6. Show messagebox with success/failure
    7. Refresh panel if successful
    """
    from tkinter import simpledialog, messagebox
    from playwright.sync_api import sync_playwright
    from login import open_logged_in_browser, DESTINATION_STATE_FILE
    
    item = self.selected_item
    if item is None:
        return
    
    # Only repair missing listing.json
    if item.problem != "Missing listing.json":
        messagebox.showwarning(
            "Cannot Repair",
            "This repair tool only handles missing listing.json files."
        )
        return
    
    # Try to auto-detect source URL
    source_url = self.repair_engine._extract_source_url(item)
    
    # If not found, prompt user
    if not source_url:
        source_url = simpledialog.askstring(
            "Source URL Required",
            f"Enter the source URL for:\n{item.folder_name}",
            parent=self,
        )
        
        if not source_url:
            return  # User cancelled
    
    # Confirm repair
    confirmed = messagebox.askyesno(
        "Confirm Repair",
        f"Repair this listing?\n\n"
        f"Folder: {item.folder_name}\n"
        f"Source: {source_url}\n\n"
        f"This will re-scrape the listing and create listing.json.",
    )
    
    if not confirmed:
        return
    
    # Perform repair with browser
    try:
        with sync_playwright() as playwright:
            browser, context, page = open_logged_in_browser(
                playwright,
                DESTINATION_STATE_FILE,
            )
            
            try:
                success, message = self.repair_engine.repair(
                    item,
                    source_url,
                    page,
                )
                
                if success:
                    messagebox.showinfo(
                        "Repair Successful",
                        f"Successfully repaired: {item.folder_name}\n\n"
                        f"The listing is now ready for use.",
                    )
                    self.refresh()
                else:
                    messagebox.showerror(
                        "Repair Failed",
                        f"Could not repair: {item.folder_name}\n\n"
                        f"Reason: {message}",
                    )
            finally:
                context.close()
                browser.close()
                
    except Exception as error:
        messagebox.showerror(
            "Repair Error",
            f"An error occurred during repair:\n\n{str(error)}",
        )
```

#### Modified Method:
```python
def _on_selected(self, _event=None) -> None:
    # ... existing code ...
    
    # NEW: Enable repair button only for missing listing.json
    can_repair = (item.problem == "Missing listing.json")
    self.repair_button.configure(
        state="normal" if can_repair else "disabled",
    )
```

**Use Built-in Dialogs:**
- `tkinter.simpledialog.askstring()` - For URL input
- `tkinter.messagebox.askyesno()` - For confirmation
- `tkinter.messagebox.showinfo()` - For success
- `tkinter.messagebox.showerror()` - For failure

---

## Error Handling

### Simple Error Strategy

**All errors handled via return tuple:**
```python
# Success
return (True, "Listing repaired successfully")

# Failure - various reasons
return (False, "Source URL is required but not provided")
return (False, "Failed to scrape listing: listing not available")
return (False, "Scraped listing missing required fields")
return (False, f"Browser error: {str(error)}")
```

**No Custom Exception Classes:**
- Catch all exceptions in `repair()` method
- Return `(False, error_message)` for any failure
- Let UI handle displaying errors via messagebox

---

## Files Requiring Modification

### New Files (Create)
1. ✨ **`inventory/repair_engine.py`** - Core repair logic (NEW)

### Modified Files
1. 📝 **`dashboard/recovery_panel.py`** - Add repair button and workflow

### Files to Read (No Modification)
- [`inventory/recovery_manager.py`](../inventory/recovery_manager.py:1) - Import RecoveryItem
- [`inventory/inventory_health.py`](../inventory/inventory_health.py:1) - Use for validation
- [`scraper/listing_scraper.py`](../scraper/listing_scraper.py:1) - Use scrape_listing()
- [`scraper/save_listing.py`](../scraper/save_listing.py:1) - Use save_listing()
- [`login.py`](../login.py:1) - Use open_logged_in_browser()
- [`runtime_paths.py`](../runtime_paths.py:1) - Import DOWNLOADS_DIR

---

## Implementation Steps

### Step 1: Create Core Repair Engine
- [ ] Create `inventory/repair_engine.py`
- [ ] Implement `RepairEngine.__init__()`
- [ ] Implement `RepairEngine.repair()` method
- [ ] Implement helper methods:
  - `_extract_source_url()`
  - `_is_valid_listing_id()`
  - `_construct_source_url()`
  - `_get_existing_images()`
  - `_merge_with_existing_images()`
  - `_validate_repair()`

### Step 2: Integrate with Recovery Panel
- [ ] Modify `dashboard/recovery_panel.py`
- [ ] Add repair button to UI
- [ ] Implement `repair_selected_listing()` method
- [ ] Update `_on_selected()` to enable/disable repair button
- [ ] Add RepairEngine instance to RecoveryPanel

### Step 3: Validation
- [ ] Run `python -m py_compile inventory/repair_engine.py`
- [ ] Run `python -m py_compile dashboard/recovery_panel.py`
- [ ] Fix any syntax errors
- [ ] Manual test with broken folder

---

## Manual Testing

### Test Case 1: Missing listing.json with images
1. Create test folder: `downloads/test-listing-123/`
2. Add some image files to folder
3. Open Recovery Panel
4. Select the broken folder
5. Click "Repair Listing"
6. Enter source URL when prompted
7. Confirm repair
8. Verify listing.json is created
9. Verify images are preserved
10. Verify folder disappears from broken list

### Test Case 2: Missing listing.json, auto-detect URL
1. Create folder with listing ID as name: `downloads/63f8a1b2c3d4e5f6g7h8i9j0/`
2. Add images
3. Open Recovery Panel
4. Select folder
5. Click "Repair Listing"
6. Verify URL is auto-constructed (no prompt)
7. Confirm repair
8. Verify success

### Test Case 3: Repair failure - unavailable listing
1. Create folder with invalid listing ID
2. Try to repair
3. Verify error message shown
4. Verify folder remains in broken list

---

## Constraints & Limitations

### What This Implementation Does:
✅ Repairs folders with missing listing.json  
✅ Preserves existing images  
✅ Auto-detects source URL from folder name  
✅ Prompts for URL if needed  
✅ Validates repaired listing  
✅ Simple, focused implementation  

### What This Implementation Does NOT Do:
❌ Repair corrupted JSON (future task)  
❌ Repair incomplete JSON (future task)  
❌ Batch repair multiple listings  
❌ Download missing images  
❌ Create backups (save_listing handles safety)  
❌ Repair history/logging  
❌ Undo functionality  
❌ Progress bars or async operations  

---

## Success Criteria

✅ **Repair engine can:**
1. Accept a RecoveryItem with missing listing.json
2. Extract or accept source URL
3. Re-scrape listing from source
4. Preserve existing local images
5. Save repaired listing.json
6. Validate repair succeeded
7. Return success/failure status

✅ **UI can:**
1. Show "Repair Listing" button for missing JSON
2. Prompt for URL if needed (simpledialog)
3. Confirm repair (messagebox)
4. Show success/failure (messagebox)
5. Refresh panel after successful repair

✅ **Code quality:**
1. Passes `py_compile` validation
2. Follows existing project patterns
3. Reuses existing infrastructure
4. No unrelated changes
5. Clear, maintainable code

---

## Revised Implementation Plan Summary

**Files to Create:**
1. `inventory/repair_engine.py` - RepairEngine class with repair() method

**Files to Modify:**
1. `dashboard/recovery_panel.py` - Add repair button and workflow

**Key Design Decisions:**
- Simple tuple return `(bool, str)` instead of complex data classes
- Use built-in tkinter dialogs instead of custom dialog classes
- Support only missing listing.json in initial version
- Preserve existing images, don't re-download
- Auto-construct URL from folder name (listing ID pattern)
- No batch repair, no async, no progress bars
- Validate with existing InventoryHealth class

**Next Step:**
Wait for approval, then implement the two files.

---

**Document Version:** 2.0 (REVISED)  
**Created:** 2026-08-06  
**Revised:** 2026-08-06  
**Status:** Awaiting Implementation Approval
