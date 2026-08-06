#!/usr/bin/env python3
"""
Upload Queue Processor Smoke Test

Tests UploadQueueProcessor end-to-end without the UI:
- Creates isolated temporary queue state file
- Selects ONE ready_for_upload item
- Configures queue for dry_run mode
- Runs UploadQueueProcessor with callbacks
- Verifies subprocess execution and output capture
- Ensures final status is SKIPPED or ALREADY_EXISTS (never UPLOADED)
- Validates timing fields and state persistence
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
from inventory.upload_queue import UploadQueueManager, QueueStatus
from pipeline.upload_queue_processor import UploadQueueProcessor, ProcessResult
from runtime_paths import LOGS_DIR


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def print_marker(status: str, message: str) -> None:
    """Print a status marker."""
    markers = {
        'ok': '[OK]',
        'fail': '[FAIL]',
        'info': '[INFO]',
    }
    marker = markers.get(status.lower(), '[INFO]')
    print(f"{marker} {message}")


def main() -> int:
    """Run the smoke test."""
    
    print_section("Upload Queue Processor Smoke Test")
    
    # Track test results
    test_passed = True
    captured_output: list[str] = []
    captured_progress: list[tuple[int, int]] = []
    captured_result: ProcessResult | None = None
    
    # Step 1: Create temporary queue file
    print_section("Step 1: Create Temporary Queue File")
    
    temp_queue_file = LOGS_DIR / "test_upload_queue_temp.json"
    
    # Clean up any existing temp file
    if temp_queue_file.exists():
        temp_queue_file.unlink()
        print_marker('info', f"Removed existing temp file: {temp_queue_file}")
    
    print_marker('ok', f"Temporary queue file: {temp_queue_file}")
    print_marker('info', "This test will NOT touch: logs/upload_queue.json")
    
    # Step 2: Load inventory and select ONE item
    print_section("Step 2: Load Inventory and Select ONE Item")
    
    inventory_manager = InventoryManager()
    all_items = inventory_manager.load_items()
    
    print_marker('info', f"Total inventory items: {len(all_items)}")
    
    ready_items = [item for item in all_items if item.ready_for_upload]
    print_marker('info', f"Items ready for upload: {len(ready_items)}")
    
    if not ready_items:
        print_marker('fail', "No items ready for upload - cannot run test")
        return 1
    
    # Select item with local_images field in listing.json
    import json
    
    selected_item = None
    image_count = 0
    
    # First pass: non-uploaded items with local_images in listing.json
    for item in ready_items:
        if item.uploaded:
            continue
        
        if not item.listing_path.exists():
            continue
        
        # Check listing.json for local_images or downloaded_images field
        try:
            listing_data = json.loads(item.listing_path.read_text(encoding='utf-8'))
            local_images = listing_data.get('local_images', [])
            if not local_images:
                local_images = listing_data.get('downloaded_images', [])
            
            if local_images and len(local_images) > 0:
                # Verify at least one image path exists
                valid_images = []
                for img_path_str in local_images:
                    img_path = Path(img_path_str)
                    if img_path.exists():
                        valid_images.append(img_path_str)
                
                if valid_images:
                    image_count = len(valid_images)
                    selected_item = item
                    break
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    
    # Second pass: already uploaded items with images (for ALREADY_EXISTS test)
    if selected_item is None:
        for item in ready_items:
            if not item.listing_path.exists():
                continue
            
            try:
                listing_data = json.loads(item.listing_path.read_text(encoding='utf-8'))
                local_images = listing_data.get('local_images', [])
                if not local_images:
                    local_images = listing_data.get('downloaded_images', [])
                
                if local_images and len(local_images) > 0:
                    # Verify at least one image path exists
                    valid_images = []
                    for img_path_str in local_images:
                        img_path = Path(img_path_str)
                        if img_path.exists():
                            valid_images.append(img_path_str)
                    
                    if valid_images:
                        image_count = len(valid_images)
                        selected_item = item
                        break
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
    
    # Verify we found a valid item
    if selected_item is None:
        print_marker('fail', "No ready item with local_images field found")
        print_marker('info', "Cannot run test without valid inventory item")
        print_marker('info', "Listings must have 'local_images' or 'downloaded_images' in listing.json")
        return 1
    
    # Print selection details
    if selected_item.uploaded:
        print_marker('ok', f"Selected already-uploaded item: {selected_item.title}")
        print_marker('info', "Expected result: ALREADY_EXISTS")
    else:
        print_marker('ok', f"Selected non-uploaded item: {selected_item.title}")
        print_marker('info', "Expected result: SKIPPED (dry_run mode)")
    
    print(f"  Listing ID:   {selected_item.listing_id}")
    print(f"  Title:        {selected_item.title}")
    print(f"  Uploaded:     {selected_item.uploaded}")
    print(f"  Listing Path: {selected_item.listing_path}")
    print(f"  Image Count:  {image_count}")
    
    # Step 3: Configure temporary queue
    print_section("Step 3: Configure Temporary Queue")
    
    queue_manager = UploadQueueManager(state_file=temp_queue_file)
    
    # Add the single item
    added_count, errors = queue_manager.add_items([selected_item])
    
    if added_count != 1:
        print_marker('fail', f"Failed to add item to queue: {errors}")
        test_passed = False
        return 1
    
    print_marker('ok', f"Added 1 item to queue")
    
    # Verify queue configuration
    if queue_manager.state is None:
        print_marker('fail', "Queue state is None after adding item")
        return 1
    
    print(f"  Queue ID:     {queue_manager.state.queue_id}")
    print(f"  Mode:         {queue_manager.state.mode}")
    print(f"  Retry Count:  {queue_manager.state.retry_count}")
    print(f"  Retry Delay:  {queue_manager.state.retry_delay}s")
    print(f"  Entries:      {len(queue_manager.state.entries)}")
    
    if queue_manager.state.mode != "dry_run":
        print_marker('fail', f"Queue mode is '{queue_manager.state.mode}', expected 'dry_run'")
        test_passed = False
        return 1
    
    print_marker('ok', "Queue configured for dry_run mode")
    print_marker('info', "This test will NEVER create a live Poshmark listing")
    
    # Step 4: Setup callbacks
    print_section("Step 4: Setup Processor Callbacks")
    
    def progress_callback(current: int, total: int) -> None:
        """Capture progress events."""
        captured_progress.append((current, total))
        print_marker('info', f"Progress: {current}/{total}")
    
    def output_callback(line: str) -> None:
        """Capture output lines."""
        captured_output.append(line)
        # Print STATUS lines for visibility
        if line.startswith("STATUS:"):
            print(f"  {line}")
    
    def completion_callback(result: ProcessResult) -> None:
        """Capture completion result."""
        nonlocal captured_result
        captured_result = result
        print_marker('info', f"Completion: {result.status.value}")
    
    print_marker('ok', "Callbacks registered")
    
    # Step 5: Run UploadQueueProcessor
    print_section("Step 5: Run UploadQueueProcessor")
    
    processor = UploadQueueProcessor(
        queue_manager=queue_manager,
        progress_callback=progress_callback,
        output_callback=output_callback,
        completion_callback=completion_callback,
    )
    
    print_marker('info', "Starting queue processing...")
    
    try:
        results = processor.process_queue()
    except Exception as e:
        print_marker('fail', f"Processor raised exception: {e}")
        test_passed = False
        return 1
    
    print_marker('ok', f"Processor completed, returned {len(results)} results")
    
    # Step 6: Verify subprocess execution
    print_section("Step 6: Verify Subprocess Execution")
    
    # Check that subprocess launched
    if not results:
        print_marker('fail', "No results returned from processor")
        test_passed = False
    else:
        print_marker('ok', f"Subprocess launched and completed")
    
    # Check that output was captured
    if not captured_output:
        print_marker('fail', "No output was captured")
        test_passed = False
    else:
        print_marker('ok', f"Captured {len(captured_output)} output lines")
    
    # Check for STATUS lines
    status_lines = [line for line in captured_output if line.startswith("STATUS:")]
    if not status_lines:
        print_marker('fail', "No STATUS lines found in output")
        test_passed = False
    else:
        print_marker('ok', f"Found {len(status_lines)} STATUS lines")
    
    # Check that ProcessResult was returned
    if captured_result is None:
        print_marker('fail', "No ProcessResult captured from completion callback")
        test_passed = False
    else:
        print_marker('ok', "ProcessResult captured from completion callback")
    
    # Step 7: Verify queue entry state
    print_section("Step 7: Verify Queue Entry State")
    
    # Reload queue to get fresh state
    queue_manager.load()
    
    if queue_manager.state is None or not queue_manager.state.entries:
        print_marker('fail', "Queue state is empty after processing")
        test_passed = False
        return 1
    
    entry = queue_manager.state.entries[0]
    
    print(f"  Listing ID:       {entry.listing_id}")
    print(f"  Status:           {entry.status.value}")
    print(f"  Attempt Count:    {entry.attempt_count}")
    print(f"  Started At:       {entry.started_at}")
    print(f"  Finished At:      {entry.finished_at}")
    print(f"  Duration:         {entry.duration_seconds:.2f}s")
    print(f"  Last Error:       {entry.last_error if entry.last_error else '(none)'}")
    
    # Verify attempt_count increased
    if entry.attempt_count < 1:
        print_marker('fail', f"Attempt count is {entry.attempt_count}, expected >= 1")
        test_passed = False
    else:
        print_marker('ok', f"Attempt count increased to {entry.attempt_count}")
    
    # Verify started_at is populated
    if not entry.started_at:
        print_marker('fail', "started_at is not populated")
        test_passed = False
    else:
        print_marker('ok', f"started_at is populated: {entry.started_at}")
    
    # Verify finished_at is populated
    if not entry.finished_at:
        print_marker('fail', "finished_at is not populated")
        test_passed = False
    else:
        print_marker('ok', f"finished_at is populated: {entry.finished_at}")
    
    # Verify duration_seconds is non-negative
    if entry.duration_seconds < 0:
        print_marker('fail', f"duration_seconds is negative: {entry.duration_seconds}")
        test_passed = False
    else:
        print_marker('ok', f"duration_seconds is non-negative: {entry.duration_seconds:.2f}s")
    
    # Verify final status - must be SKIPPED or ALREADY_EXISTS only
    expected_statuses = [QueueStatus.SKIPPED, QueueStatus.ALREADY_EXISTS]
    
    if entry.status == QueueStatus.UPLOADED:
        print_marker('fail', "Status is UPLOADED - test should NEVER upload!")
        test_passed = False
    elif entry.status == QueueStatus.FAILED:
        print_marker('fail', f"Status is FAILED: {entry.last_error}")
        test_passed = False
        
        # Print diagnostic information per requirement #10
        print("\n" + "=" * 70)
        print("  FAILURE DIAGNOSTICS (Requirement #10)")
        print("=" * 70)
        
        print("\n--- Captured stdout (last 50 lines) ---")
        for line in captured_output[-50:]:
            print(line)
        
        if captured_result:
            print(f"\n--- ProcessResult ---")
            print(f"Exit Code: {captured_result.exit_code}")
            print(f"Message: {captured_result.message}")
        
        print(f"\n--- Final Queue Entry ---")
        print(f"Status: {entry.status.value}")
        print(f"Last Error: {entry.last_error}")
        print(f"Attempt Count: {entry.attempt_count}")
        
        print("\n" + "=" * 70)
    elif entry.status in expected_statuses:
        print_marker('ok', f"Final status is {entry.status.value} (expected)")
    else:
        print_marker('fail', f"Unexpected status: {entry.status.value}")
        test_passed = False
    
    # Step 8: Verify state persistence
    print_section("Step 8: Verify State Persistence")
    
    # Create new manager and reload
    new_manager = UploadQueueManager(state_file=temp_queue_file)
    reloaded_state = new_manager.load()
    
    if reloaded_state is None:
        print_marker('fail', "Failed to reload queue state")
        test_passed = False
    else:
        print_marker('ok', "Queue state reloaded successfully")
        
        if not reloaded_state.entries:
            print_marker('fail', "Reloaded state has no entries")
            test_passed = False
        else:
            reloaded_entry = reloaded_state.entries[0]
            
            if reloaded_entry.status != entry.status:
                print_marker('fail', f"Reloaded status mismatch: {reloaded_entry.status.value} != {entry.status.value}")
                test_passed = False
            else:
                print_marker('ok', f"Reloaded status matches: {reloaded_entry.status.value}")
            
            if reloaded_entry.attempt_count != entry.attempt_count:
                print_marker('fail', f"Reloaded attempt_count mismatch: {reloaded_entry.attempt_count} != {entry.attempt_count}")
                test_passed = False
            else:
                print_marker('ok', f"Reloaded attempt_count matches: {reloaded_entry.attempt_count}")
    
    # Step 9: Verify log file exists
    print_section("Step 9: Verify Log File")
    
    log_file = LOGS_DIR / "upload_queue.log"
    
    if not log_file.exists():
        print_marker('fail', f"Log file does not exist: {log_file}")
        test_passed = False
    else:
        print_marker('ok', f"Log file exists: {log_file}")
        
        # Show last few lines
        try:
            log_content = log_file.read_text(encoding='utf-8')
            log_lines = log_content.splitlines()
            
            print(f"\n  Last 5 log entries:")
            for line in log_lines[-5:]:
                print(f"    {line}")
        except Exception as e:
            print_marker('info', f"Could not read log file: {e}")
    
    # Step 10: Cleanup
    print_section("Step 10: Cleanup")
    
    if temp_queue_file.exists():
        try:
            temp_queue_file.unlink()
            print_marker('ok', f"Removed temporary queue file: {temp_queue_file}")
        except Exception as e:
            print_marker('fail', f"Failed to remove temp file: {e}")
            test_passed = False
    else:
        print_marker('info', "Temporary queue file already removed")
    
    print_marker('info', "Log file upload_queue.log was NOT deleted (as required)")
    
    # Final result
    print_section("Final Result")
    
    if test_passed:
        print("\n  ██████╗  █████╗ ███████╗███████╗")
        print("  ██╔══██╗██╔══██╗██╔════╝██╔════╝")
        print("  ██████╔╝███████║███████╗███████╗")
        print("  ██╔═══╝ ██╔══██║╚════██║╚════██║")
        print("  ██║     ██║  ██║███████║███████║")
        print("  ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝")
        print("\n  All verifications passed!")
        return 0
    else:
        print("\n  ███████╗ █████╗ ██╗██╗     ")
        print("  ██╔════╝██╔══██╗██║██║     ")
        print("  █████╗  ███████║██║██║     ")
        print("  ██╔══╝  ██╔══██║██║██║     ")
        print("  ██║     ██║  ██║██║███████╗")
        print("  ╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝")
        print("\n  One or more verifications failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
