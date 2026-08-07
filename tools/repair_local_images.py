"""
Repair missing or invalid local_images metadata in listing.json files.

Scans all listing folders under downloads/ and repairs listing.json files
whose image metadata is missing, empty, invalid, or mismatched.

Usage:
    python tools/repair_local_images.py          # Dry-run (report only)
    python tools/repair_local_images.py --apply  # Perform repairs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime_paths import DOWNLOADS_DIR


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def natural_sort_key(filename: str) -> list:
    """
    Convert filename to list of strings and integers for natural sorting.
    
    This ensures: image_1.jpg < image_2.jpg < ... < image_10.jpg
    """
    parts = []
    for part in re.split(r'(\d+)', filename):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part.lower())
    return parts


def find_image_files(folder: Path) -> list[Path]:
    """
    Find all image files in the folder with supported extensions.
    
    Returns naturally sorted list of absolute resolved paths.
    """
    if not folder.exists() or not folder.is_dir():
        return []
    
    image_files = []
    
    try:
        for item in folder.iterdir():
            if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS:
                image_files.append(item.resolve())
    except OSError:
        return []
    
    # Sort naturally
    image_files.sort(key=lambda p: natural_sort_key(p.name))
    
    return image_files


def needs_repair(
    listing_data: dict[str, Any],
    folder: Path,
    actual_images: list[Path]
) -> tuple[bool, str]:
    """
    Determine if local_images needs repair.
    
    Returns:
        (needs_repair: bool, reason: str)
    """
    local_images = listing_data.get("local_images")
    
    # Check if local_images is missing or not a list
    if local_images is None:
        return True, "local_images missing"
    
    if not isinstance(local_images, list):
        return True, "local_images not a list"
    
    # Check if empty
    if not local_images:
        if actual_images:
            return True, "local_images empty but images exist"
        else:
            return False, "no images"
    
    # Check count mismatch
    if len(local_images) != len(actual_images):
        return True, f"count mismatch ({len(local_images)} vs {len(actual_images)})"
    
    # Check if paths exist and are in the listing folder
    valid_count = 0
    folder_resolved = folder.resolve()
    
    for image_path_str in local_images:
        try:
            image_path = Path(str(image_path_str)).resolve()
            
            # Check if path exists
            if not image_path.exists():
                return True, "contains non-existent paths"
            
            # Check if path is inside listing folder
            try:
                image_path.relative_to(folder_resolved)
            except ValueError:
                return True, "contains paths outside listing folder"
            
            valid_count += 1
            
        except (OSError, ValueError):
            return True, "contains invalid paths"
    
    # All checks passed
    return False, "valid"


def create_backup(json_path: Path) -> Path:
    """
    Create a backup of listing.json.
    
    First backup: listing.json.bak
    If .bak exists: listing.json.bak.YYYYMMDD_HHMMSS
    
    Returns the backup path created.
    """
    backup_path = json_path.parent / "listing.json.bak"
    
    if backup_path.exists():
        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = json_path.parent / f"listing.json.bak.{timestamp}"
    
    # Copy the file
    try:
        backup_path.write_bytes(json_path.read_bytes())
        return backup_path
    except OSError as e:
        raise RuntimeError(f"Failed to create backup: {e}")


def repair_listing(
    folder: Path,
    listing_data: dict[str, Any],
    actual_images: list[Path],
    dry_run: bool
) -> bool:
    """
    Repair the listing.json file.
    
    Sets local_images and downloaded_images to actual image paths.
    Preserves all other fields.
    Uses atomic write with tempfile + os.replace.
    
    Returns True if successful, False otherwise.
    """
    json_path = folder / "listing.json"
    
    if dry_run:
        print(f"  Action: Would repair (dry-run)")
        return True
    
    try:
        # Create backup
        backup_path = create_backup(json_path)
        print(f"  Backup: {backup_path.name}")
        
        # Update the data
        image_paths_str = [str(p) for p in actual_images]
        listing_data["local_images"] = image_paths_str
        listing_data["downloaded_images"] = image_paths_str
        
        # Atomic write
        fd, temp_path = tempfile.mkstemp(
            prefix=".listing.json.",
            suffix=".tmp",
            dir=str(folder)
        )
        
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(listing_data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            os.replace(temp_path, str(json_path))
            print(f"  Action: Repaired successfully")
            return True
            
        except Exception:
            # Clean up temp file if it still exists
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
            
    except Exception as e:
        print(f"  Action: FAILED - {e}")
        return False


def scan_and_repair(downloads_dir: Path, dry_run: bool) -> dict[str, int]:
    """
    Scan all listing folders and repair as needed.
    
    Returns statistics dictionary.
    """
    stats = {
        "folders_scanned": 0,
        "listing_json_found": 0,
        "already_correct": 0,
        "repaired": 0,
        "missing_listing_json": 0,
        "no_image_files": 0,
        "invalid_json": 0,
        "errors": 0,
    }
    
    if not downloads_dir.exists():
        print(f"ERROR: Downloads directory not found: {downloads_dir}")
        return stats
    
    # Get all direct child folders
    try:
        folders = [
            item for item in downloads_dir.iterdir()
            if item.is_dir()
        ]
    except OSError as e:
        print(f"ERROR: Cannot list downloads directory: {e}")
        return stats
    
    folders.sort()
    
    for folder in folders:
        stats["folders_scanned"] += 1
        json_path = folder / "listing.json"
        
        # Check if listing.json exists
        if not json_path.exists():
            stats["missing_listing_json"] += 1
            print(f"[SKIP] {folder.name} - No listing.json")
            continue
        
        stats["listing_json_found"] += 1
        
        # Load JSON safely
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                listing_data = json.load(f)
            
            if not isinstance(listing_data, dict):
                stats["invalid_json"] += 1
                print(f"[SKIP] {folder.name} - Invalid JSON (not a dict)")
                continue
                
        except (OSError, json.JSONDecodeError) as e:
            stats["invalid_json"] += 1
            print(f"[SKIP] {folder.name} - Invalid JSON: {e}")
            continue
        
        # Find actual image files
        actual_images = find_image_files(folder)
        
        if not actual_images:
            stats["no_image_files"] += 1
            print(f"[SKIP] {folder.name} - No image files found")
            continue
        
        # Check if repair is needed
        repair_needed, reason = needs_repair(listing_data, folder, actual_images)
        
        if not repair_needed:
            stats["already_correct"] += 1
            continue
        
        # Report repair details
        print(f"\n[REPAIR NEEDED] {folder.name}")
        print(f"  Reason: {reason}")
        
        # Count valid existing paths
        local_images = listing_data.get("local_images", [])
        if isinstance(local_images, list):
            valid_existing = sum(
                1 for p in local_images
                if Path(str(p)).exists()
            )
        else:
            valid_existing = 0
        
        print(f"  Old local_images count: {len(local_images) if isinstance(local_images, list) else 0}")
        print(f"  Valid existing paths: {valid_existing}")
        print(f"  Actual image files: {len(actual_images)}")
        
        # Perform repair
        success = repair_listing(folder, listing_data, actual_images, dry_run)
        
        if success:
            stats["repaired"] += 1
        else:
            stats["errors"] += 1
    
    return stats


def print_summary(stats: dict[str, int], dry_run: bool):
    """Print summary statistics."""
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Folders scanned:       {stats['folders_scanned']}")
    print(f"listing.json found:    {stats['listing_json_found']}")
    print(f"Already correct:       {stats['already_correct']}")
    
    if dry_run:
        print(f"Would repair:          {stats['repaired']}")
    else:
        print(f"Repaired:              {stats['repaired']}")
    
    print(f"Missing listing.json:  {stats['missing_listing_json']}")
    print(f"No image files:        {stats['no_image_files']}")
    print(f"Invalid JSON:          {stats['invalid_json']}")
    print(f"Errors:                {stats['errors']}")
    print("=" * 50)
    
    if dry_run:
        print("\nDRY-RUN MODE: No files were modified.")
        print("Run with --apply to perform repairs.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Repair missing or invalid local_images metadata in listing.json files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform repairs (default is dry-run)"
    )
    
    args = parser.parse_args()
    dry_run = not args.apply
    
    print("=" * 50)
    print("LOCAL IMAGES REPAIR UTILITY")
    print("=" * 50)
    print(f"Mode: {'DRY-RUN (report only)' if dry_run else 'APPLY (perform repairs)'}")
    print(f"Downloads directory: {DOWNLOADS_DIR}")
    print("=" * 50)
    print()
    
    # Scan and repair
    stats = scan_and_repair(DOWNLOADS_DIR, dry_run)
    
    # Print summary
    print_summary(stats, dry_run)
    
    # Exit code
    if stats["errors"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
