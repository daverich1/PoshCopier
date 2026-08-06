# TASK-001 Implementation - Exact Diff Blocks

This document shows the exact changes that will be applied to [`dashboard/dashboard.py`](../dashboard/dashboard.py:1).

## Change 1: Add RecoveryPanel Import

**Location**: Line 13 (after `from dashboard.inventory_panel import InventoryPanel`)

```diff
<<<<<<< SEARCH
:start_line:13
-------
from dashboard.inventory_panel import InventoryPanel
from dashboard.controls import ControlsPanel
=======
from dashboard.inventory_panel import InventoryPanel
from dashboard.recovery_panel import RecoveryPanel
from dashboard.controls import ControlsPanel
>>>>>>> REPLACE
```

**Result**: Adds import for `RecoveryPanel` class between `InventoryPanel` and `ControlsPanel` imports.

---

## Change 2: Create recovery_tab Frame

**Location**: Line 110-113 (after `inventory_tab` definition)

```diff
<<<<<<< SEARCH
:start_line:110
-------
        inventory_tab = ttk.Frame(
            notebook,
            padding=0,
        )

        notebook.add(
=======
        inventory_tab = ttk.Frame(
            notebook,
            padding=0,
        )
        recovery_tab = ttk.Frame(
            notebook,
            padding=0,
        )

        notebook.add(
>>>>>>> REPLACE
```

**Result**: Creates `recovery_tab` Frame immediately after `inventory_tab`, before the `notebook.add()` calls.

---

## Change 3: Add Recovery Tab to Notebook

**Location**: Line 119-122 (after inventory tab is added to notebook)

```diff
<<<<<<< SEARCH
:start_line:119
-------
        notebook.add(
            inventory_tab,
            text="Inventory",
        )
        settings = ttk.LabelFrame(
=======
        notebook.add(
            inventory_tab,
            text="Inventory",
        )
        notebook.add(
            recovery_tab,
            text="Recovery",
        )
        settings = ttk.LabelFrame(
>>>>>>> REPLACE
```

**Result**: Adds Recovery tab to notebook after Inventory tab, before the settings LabelFrame.

---

## Change 4: Instantiate and Pack RecoveryPanel

**Location**: Line 354-361 (after inventory panel instantiation)

```diff
<<<<<<< SEARCH
:start_line:354
-------
        self.inventory_panel = InventoryPanel(
            inventory_tab
        )
        self.inventory_panel.pack(
            fill="both",
            expand=True,
        )
        
    def validate_settings(
=======
        self.inventory_panel = InventoryPanel(
            inventory_tab
        )
        self.inventory_panel.pack(
            fill="both",
            expand=True,
        )

        self.recovery_panel = RecoveryPanel(
            recovery_tab
        )
        self.recovery_panel.pack(
            fill="both",
            expand=True,
        )
        
    def validate_settings(
>>>>>>> REPLACE
```

**Result**: Instantiates `RecoveryPanel` with `recovery_tab` as parent and packs it with `fill="both"` and `expand=True`, following the same pattern as `InventoryPanel`.

---

## Summary

### Statistics
- **File modified**: `dashboard/dashboard.py`
- **Total changes**: 4 diff blocks
- **Lines added**: 14
- **Lines modified**: 0
- **Lines deleted**: 0

### Changes Overview
1. ✅ Import `RecoveryPanel` class
2. ✅ Create `recovery_tab` Frame widget
3. ✅ Add Recovery tab to notebook (positioned after Inventory)
4. ✅ Instantiate and pack `RecoveryPanel` component

### Verification Command
After applying changes, run:
```bash
python -m py_compile dashboard\dashboard.py
```

Expected result: No output (successful compilation)

### Expected Behavior
- Dashboard will display 3 tabs: "Pipeline", "Inventory", "Recovery"
- Recovery tab will appear after Inventory tab
- Clicking Recovery tab will display the Recovery Center interface
- All existing Pipeline and Inventory functionality will remain unchanged

### Rollback
If issues occur, revert all 4 changes in reverse order.
