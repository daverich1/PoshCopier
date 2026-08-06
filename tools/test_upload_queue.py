#!/usr/bin/env python3
"""
Upload Queue Smoke Test

Tests basic functionality of UploadQueueManager:
- Load existing queue or create new
- Add inventory items
- Save and reload
- Verify data integrity
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from inventory.inventory_manager import InventoryManager
from inventory.upload_queue import UploadQueueManager


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def print_progress_summary(summary: dict) -> None:
    """Print progress summary in a readable format."""
    print(f"  Total entries:    {summary['total']}")
    print(f"  Waiting:          {summary['waiting']}")
    print(f"  Pending:          {summary['pending']}")
    print(f"  Running:          {summary['running']}")
    print(f"  Uploaded:         {summary['uploaded']}")
    print(f"  Already exists:   {summary['already_exists']}")
    print(f"  Failed:           {summary['failed']}")
    print(f"  Skipped:          {summary['skipped']}")
    print(f"  Cancelled:        {summary['cancelled']}")
    print(f"  Completed:        {summary['completed']}")
    print(f"  Remaining:        {summary['remaining']}")
    print(f"  Progress:         {summary['percent']:.1f}%")


def main() -> int:
    """Run the smoke test."""
    
    print_section("Upload Queue Smoke Test")
    
    # Step 1: Load UploadQueueManager
    print_section("Step 1: Load UploadQueueManager")
    
    manager = UploadQueueManager()
    existing_state = manager.load()
    
    if existing_state:
        print("✓ Existing queue found")
        print(f"  Queue ID:  {existing_state.queue_id}")
        print(f"  Version:   {existing_state.version}")
        print(f"  Created:   {existing_state.created_at}")
        print(f"  Updated:   {existing_state.updated_at}")
        print(f"  Mode:      {existing_state.mode}")
    else:
        print("✓ No existing queue found (will create new)")
    
    # Step 2: Print initial state
    print_section("Step 2: Initial Queue State")
    
    if existing_state:
        print(f"Queue ID:  {existing_state.queue_id}")
        print(f"Version:   {existing_state.version}")
        print(f"Total entries: {len(existing_state.entries)}")
        print("\nProgress Summary:")
        summary = manager.progress_summary()
        print_progress_summary(summary)
    else:
        print("No queue state yet")
    
    # Step 3: Find inventory items ready for upload
    print_section("Step 3: Find Inventory Items")
    
    inventory_manager = InventoryManager()
    all_items = inventory_manager.load_items()
    
    print(f"Total inventory items: {len(all_items)}")
    
    ready_items = [item for item in all_items if item.ready_for_upload]
    print(f"Items ready for upload: {len(ready_items)}")
    
    # Take up to 5 items
    items_to_add = ready_items[:5]
    print(f"Items to add to queue: {len(items_to_add)}")
    
    if items_to_add:
        print("\nItems selected:")
        for i, item in enumerate(items_to_add, 1):
            print(f"  {i}. {item.listing_id} - {item.title[:50]}")
    else:
        print("\n⚠ No items ready for upload found")
        print("   Test will continue with empty queue operations")
    
    # Step 4: Add items to queue
    print_section("Step 4: Add Items to Queue")
    
    if items_to_add:
        added_count, errors = manager.add_items(items_to_add)
        print(f"✓ Added {added_count} items to queue")
        
        if errors:
            print(f"\nWarnings/Errors ({len(errors)}):")
            for error in errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more")
    else:
        print("Skipping add (no items available)")
    
    # Step 5: Save queue
    print_section("Step 5: Save Queue")
    
    if manager.state:
        manager.save()
        print("✓ Queue saved to disk")
        print(f"  File: {manager.state_file}")
    else:
        print("No state to save")
    
    # Step 6: Capture state before reload
    print_section("Step 6: Capture State Before Reload")
    
    if manager.state:
        before_count = len(manager.state.entries)
        before_queue_id = manager.state.queue_id
        before_version = manager.state.version
        
        # Capture entry details
        before_entries = []
        for entry in manager.state.entries:
            before_entries.append({
                'listing_id': entry.listing_id,
                'title': entry.title,
                'status': entry.status.value,
                'created_at': entry.created_at,
            })
        
        print(f"Entry count:  {before_count}")
        print(f"Queue ID:     {before_queue_id}")
        print(f"Version:      {before_version}")
    else:
        print("No state to capture")
        before_count = 0
        before_queue_id = ""
        before_version = 0
        before_entries = []
    
    # Step 7: Reload from disk
    print_section("Step 7: Reload from Disk")
    
    manager2 = UploadQueueManager()
    reloaded_state = manager2.load()
    
    if reloaded_state:
        print("✓ Queue reloaded successfully")
        print(f"  Queue ID:  {reloaded_state.queue_id}")
        print(f"  Version:   {reloaded_state.version}")
        print(f"  Entries:   {len(reloaded_state.entries)}")
    else:
        print("✗ Failed to reload queue")
    
    # Step 8: Verify data integrity
    print_section("Step 8: Verify Data Integrity")
    
    all_checks_passed = True
    
    # Check 1: Entry count matches
    if reloaded_state:
        after_count = len(reloaded_state.entries)
        if after_count == before_count:
            print(f"✓ Entry count matches: {after_count}")
        else:
            print(f"✗ Entry count mismatch: before={before_count}, after={after_count}")
            all_checks_passed = False
        
        # Check 2: Queue ID preserved
        after_queue_id = reloaded_state.queue_id
        if after_queue_id == before_queue_id:
            print(f"✓ Queue ID preserved: {after_queue_id}")
        else:
            print(f"✗ Queue ID mismatch: before={before_queue_id}, after={after_queue_id}")
            all_checks_passed = False
        
        # Check 3: Version preserved
        after_version = reloaded_state.version
        if after_version == before_version:
            print(f"✓ Version preserved: {after_version}")
        else:
            print(f"✗ Version mismatch: before={before_version}, after={after_version}")
            all_checks_passed = False
        
        # Check 4: Listing IDs preserved
        after_listing_ids = {entry.listing_id for entry in reloaded_state.entries}
        before_listing_ids = {entry['listing_id'] for entry in before_entries}
        
        if after_listing_ids == before_listing_ids:
            print(f"✓ Listing IDs preserved: {len(after_listing_ids)} entries")
        else:
            print(f"✗ Listing IDs mismatch")
            missing = before_listing_ids - after_listing_ids
            extra = after_listing_ids - before_listing_ids
            if missing:
                print(f"  Missing: {missing}")
            if extra:
                print(f"  Extra: {extra}")
            all_checks_passed = False
        
        # Check 5: Timestamps preserved
        timestamps_ok = True
        for before_entry in before_entries:
            # Find matching entry in reloaded state
            after_entry = None
            for entry in reloaded_state.entries:
                if entry.listing_id == before_entry['listing_id']:
                    after_entry = entry
                    break
            
            if after_entry:
                if after_entry.created_at != before_entry['created_at']:
                    print(f"✗ Timestamp mismatch for {before_entry['listing_id']}")
                    timestamps_ok = False
                    all_checks_passed = False
                    break
        
        if timestamps_ok:
            print(f"✓ Timestamps preserved for all entries")
        
        # Check 6: Statuses preserved
        statuses_ok = True
        for before_entry in before_entries:
            # Find matching entry in reloaded state
            after_entry = None
            for entry in reloaded_state.entries:
                if entry.listing_id == before_entry['listing_id']:
                    after_entry = entry
                    break
            
            if after_entry:
                # Note: RUNNING status should be converted to PENDING on load
                expected_status = before_entry['status']
                if expected_status == 'running':
                    expected_status = 'pending'
                
                if after_entry.status.value != expected_status:
                    print(f"✗ Status mismatch for {before_entry['listing_id']}: "
                          f"expected={expected_status}, got={after_entry.status.value}")
                    statuses_ok = False
                    all_checks_passed = False
                    break
        
        if statuses_ok:
            print(f"✓ Statuses preserved for all entries")
    else:
        if before_count > 0:
            print("✗ Queue state lost after reload")
            all_checks_passed = False
        else:
            print("✓ No state to verify (empty queue)")
    
    # Step 9: Final summary
    print_section("Final Summary")
    
    if reloaded_state:
        print(f"Queue ID:  {reloaded_state.queue_id}")
        print(f"Version:   {reloaded_state.version}")
        print(f"Total entries: {len(reloaded_state.entries)}")
        print("\nProgress Summary:")
        summary = manager2.progress_summary()
        print_progress_summary(summary)
    
    # Final result
    print_section("Test Result")
    
    if all_checks_passed:
        print("✓ PASS - All checks passed")
        print("\nThe upload queue is working correctly:")
        print("  - State persistence works")
        print("  - Data integrity maintained")
        print("  - All fields preserved correctly")
        return 0
    else:
        print("✗ FAIL - Some checks failed")
        print("\nPlease review the diagnostics above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
