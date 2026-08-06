from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inventory.inventory_health import InventoryHealth
from inventory.recovery_manager import RecoveryItem
from runtime_paths import DOWNLOADS_DIR


@dataclass(frozen=True)
class ImageSnapshot:
    """Snapshot of an image file for verification."""
    path: Path
    size: int
    mtime: float


class RepairEngine:
    """
    Repairs broken inventory folders by regenerating missing listing.json files.
    
    Supports only folders where listing.json is missing.
    """

    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
    ) -> None:
        self.downloads_dir = downloads_dir
        self.health = InventoryHealth(downloads_dir)

    def repair(
        self,
        item: RecoveryItem,
        source_url: str | None = None,
    ) -> tuple[bool, str]:
        """
        Repair a broken inventory folder.

        Args:
            item: The RecoveryItem to repair
            source_url: Optional source URL to scrape from

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            return self._repair_internal(item, source_url)
        except Exception as error:
            return False, f"Repair failed: {str(error)}"

    def _repair_internal(
        self,
        item: RecoveryItem,
        source_url: str | None,
    ) -> tuple[bool, str]:
        # Only support missing listing.json
        if item.problem != "Missing listing.json":
            return False, (
                f"Cannot repair: {item.problem}. "
                "Only 'Missing listing.json' is supported."
            )

        # Refuse to overwrite existing listing.json
        if item.listing_file.exists():
            return False, (
                "Repair blocked: listing.json already exists. "
                "Delete it manually if you want to regenerate it."
            )

        # Determine source URL - try auto-discovery first
        url_to_use = source_url or item.source_url
        url_source = "provided" if source_url else "from item"
        
        if not url_to_use:
            # Try to auto-discover from discovered_listings.json
            url_to_use = self._lookup_url_from_discovery(item.folder_name)
            if url_to_use:
                url_source = "auto-discovered"

        if not url_to_use:
            return False, (
                "Cannot repair: No source URL available. "
                "Please provide a source URL to scrape from."
            )

        # Validate folder exists
        if not item.folder_path.exists():
            return False, f"Folder not found: {item.folder_path}"

        # Snapshot existing images before repair (absolute paths, size, mtime)
        target_folder = item.folder_path.resolve()
        image_snapshots_before = self._snapshot_images(target_folder)
        image_count_before = len(image_snapshots_before)

        # Scrape to temporary folder
        temp_listing_file = None
        temp_folder = None
        
        try:
            temp_listing_file = self._scrape_to_temp_folder(url_to_use)
            
            if not temp_listing_file or not temp_listing_file.exists():
                return False, (
                    "Scraping completed but listing.json was not created."
                )
            
            # Get the temp folder from the listing file path
            temp_folder = temp_listing_file.parent
            
            # Load and modify the listing data
            listing_data = self._load_json(temp_listing_file)
            
            # Update listing_id to match target folder
            listing_data["listing_id"] = target_folder.name
            
            # Update local_images to point to existing images (relative names)
            listing_data["local_images"] = [
                snapshot.path.name for snapshot in image_snapshots_before
            ]
            
            # Write to target folder atomically
            self._atomic_write_json(item.listing_file, listing_data)
            
        finally:
            # Clean up temp folder
            if temp_folder and temp_folder.exists():
                try:
                    shutil.rmtree(temp_folder)
                except Exception:
                    pass

        # Verify the listing.json was actually created
        if not item.listing_file.is_file():
            return False, (
                f"Repair failed: listing.json was not created in the target folder.\n"
                f"Target folder: {target_folder}\n"
                f"Target listing.json: {item.listing_file}\n"
                f"File exists: {item.listing_file.exists()}"
            )

        # Verify original images are still intact (exact paths, size, mtime)
        verification_failed, error_message = self._verify_images_unchanged(
            target_folder,
            image_snapshots_before,
        )
        
        if verification_failed:
            # Rollback: delete the listing.json we just created
            try:
                item.listing_file.unlink(missing_ok=True)
            except Exception:
                pass
            
            return False, (
                f"{error_message}\n"
                f"Target folder: {target_folder}\n"
                f"Target listing.json: {item.listing_file}"
            )

        # Validate the repair
        validation = self.health.scan_listing(item.folder_path)

        # Fatal failures: roll back listing.json
        if not validation.json_valid:
            # Rollback: delete the listing.json
            try:
                item.listing_file.unlink(missing_ok=True)
            except Exception:
                pass
            
            return False, (
                f"Repair failed: Generated listing.json is not valid.\n"
                f"Target folder: {target_folder}\n"
                f"Target listing.json: {item.listing_file}\n"
                f"File exists: {item.listing_file.exists()}"
            )

        if not validation.has_images:
            # Rollback: delete the listing.json
            try:
                item.listing_file.unlink(missing_ok=True)
            except Exception:
                pass
            
            return False, (
                f"Repair failed: No images found after repair.\n"
                f"Target folder: {target_folder}\n"
                f"Target listing.json: {item.listing_file}"
            )

        # Partial recovery: keep listing.json if only missing editable metadata
        if validation.missing_fields:
            # JSON is valid and images exist, so keep the partial recovery
            url_note = f" (URL {url_source})" if url_source == "auto-discovered" else ""
            return True, (
                f"Listing metadata was recovered{url_note}, but it still needs attention. "
                f"Missing fields: {', '.join(validation.missing_fields)}. "
                f"Preserved {image_count_before} existing image(s)."
            )

        # Check if fully ready for upload
        if not validation.ready_for_upload:
            # This shouldn't happen if json_valid, has_images, and no missing_fields
            # But if it does, keep the partial recovery
            url_note = f" (URL {url_source})" if url_source == "auto-discovered" else ""
            return True, (
                f"Listing metadata was recovered{url_note}, but it still needs attention. "
                f"Preserved {image_count_before} existing image(s)."
            )

        # Final verification: listing.json must exist
        if not item.listing_file.is_file():
            return False, (
                f"Repair failed: listing.json does not exist after all validations.\n"
                f"Target folder: {target_folder}\n"
                f"Target listing.json: {item.listing_file}"
            )

        # Success!
        url_note = f" (URL {url_source})" if url_source == "auto-discovered" else ""
        return True, (
            f"Repair successful{url_note}! "
            f"Preserved {image_count_before} existing image(s). "
            f"Listing is ready for upload."
        )

    def _scrape_to_temp_folder(
        self,
        source_url: str,
    ) -> Path | None:
        """
        Scrape listing to a temporary folder.
        
        Returns:
            Path to the created listing.json file, or None if scraping failed
        """
        from playwright.sync_api import sync_playwright
        from scraper.listing_scraper import scrape_listing

        # Create a unique temp folder
        temp_dir = Path(tempfile.mkdtemp(prefix="repair_"))
        
        # Temporarily override DOWNLOADS_DIR to point to temp
        import runtime_paths
        original_downloads = runtime_paths.DOWNLOADS_DIR
        
        try:
            # Point downloads to temp directory
            runtime_paths.DOWNLOADS_DIR = temp_dir
            
            # Scrape with browser
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    listing_data = scrape_listing(page, source_url)
                finally:
                    browser.close()
            
            # Get the actual path from the returned listing data
            listing_json_path = listing_data.get("listing_json")
            
            if not listing_json_path:
                return None
            
            listing_json_file = Path(listing_json_path)
            
            if not listing_json_file.exists():
                return None
            
            return listing_json_file
            
        finally:
            # Restore original DOWNLOADS_DIR
            runtime_paths.DOWNLOADS_DIR = original_downloads

    def _lookup_url_from_discovery(
        self,
        folder_name: str,
    ) -> str | None:
        """
        Search for listing URL in discovered_listings.json.
        
        Args:
            folder_name: The folder name (should match listing_id)
        
        Returns:
            URL if found, None otherwise
        """
        discovery_file = self.downloads_dir / "discovered_listings.json"
        
        if not discovery_file.exists():
            return None
        
        try:
            discovery_data = self._load_json(discovery_file)
            
            if not discovery_data or "listings" not in discovery_data:
                return None
            
            listings: list[dict[str, Any]] = discovery_data.get("listings", [])
            
            # Search for matching listing_id
            for listing in listings:
                if listing.get("listing_id") == folder_name:
                    url = listing.get("url")
                    if url:
                        return url
            
            return None
            
        except Exception:
            return None

    def _snapshot_images(
        self,
        folder: Path,
    ) -> list[ImageSnapshot]:
        """
        Create snapshots of existing images with absolute paths, size, and mtime.
        
        Args:
            folder: Absolute resolved path to target folder
        
        Returns:
            List of ImageSnapshot objects
        """
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        
        if not folder.exists():
            return []

        snapshots = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in extensions:
                try:
                    stat = path.stat()
                    snapshots.append(
                        ImageSnapshot(
                            path=path.resolve(),
                            size=stat.st_size,
                            mtime=stat.st_mtime,
                        )
                    )
                except Exception:
                    # Skip files we can't stat
                    pass

        return snapshots

    def _verify_images_unchanged(
        self,
        target_folder: Path,
        snapshots_before: list[ImageSnapshot],
    ) -> tuple[bool, str]:
        """
        Verify that original images are still intact.
        
        Args:
            target_folder: Absolute resolved path to target folder
            snapshots_before: List of ImageSnapshot from before repair
        
        Returns:
            Tuple of (verification_failed: bool, error_message: str)
            Returns (False, "") if verification passed
        """
        if not snapshots_before:
            # No images to verify
            return False, ""
        
        # Check each original image still exists with same size and mtime
        for snapshot in snapshots_before:
            if not snapshot.path.exists():
                return True, (
                    f"Repair failed: Original image was deleted or moved: "
                    f"{snapshot.path.name}"
                )
            
            try:
                current_stat = snapshot.path.stat()
                
                if current_stat.st_size != snapshot.size:
                    return True, (
                        f"Repair failed: Original image was modified (size changed): "
                        f"{snapshot.path.name}"
                    )
                
                if current_stat.st_mtime != snapshot.mtime:
                    return True, (
                        f"Repair failed: Original image was modified (mtime changed): "
                        f"{snapshot.path.name}"
                    )
                    
            except Exception as e:
                return True, (
                    f"Repair failed: Cannot verify image {snapshot.path.name}: {e}"
                )
        
        # All images verified unchanged
        return False, ""

    def _get_existing_images(
        self,
        folder: Path,
    ) -> list[Path]:
        """Get list of existing image files in folder."""
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        
        if not folder.exists():
            return []

        images = [
            path
            for path in sorted(folder.iterdir())
            if (
                path.is_file()
                and path.suffix.lower() in extensions
            )
        ]

        return images

    def _load_json(
        self,
        path: Path,
    ) -> dict[str, Any]:
        """Load JSON from file."""
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
        
        if not isinstance(payload, dict):
            raise TypeError("JSON root must be an object.")
        
        return payload

    def _atomic_write_json(
        self,
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        """Write JSON atomically to avoid corruption."""
        # Resolve paths to absolute
        path = path.resolve()
        parent = path.parent
        
        # Ensure parent directory exists
        parent.mkdir(parents=True, exist_ok=True)
        
        # Collect diagnostics
        diagnostics = {
            "target_path": str(path),
            "parent_path": str(parent),
            "parent_exists": parent.exists(),
            "parent_is_dir": parent.is_dir(),
        }
        
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(parent),
        )
        
        diagnostics["temp_file"] = temporary_name
        
        try:
            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                
                handle.flush()
                os.fsync(handle.fileno())
            
            # Capture state before replace
            temp_path = Path(temporary_name)
            diagnostics["temp_exists_before"] = temp_path.exists()
            diagnostics["temp_size"] = temp_path.stat().st_size if temp_path.exists() else 0
            diagnostics["target_exists_before"] = path.exists()
            
            # Use os.replace for atomic operation on Windows
            os.replace(temporary_name, str(path))
            
            # Verify target after replace
            diagnostics["target_exists_after"] = path.exists()
            diagnostics["target_is_file"] = path.is_file()
            
            # If target doesn't exist after replace, raise with diagnostics
            if not path.is_file():
                raise RuntimeError(
                    f"Atomic write failed: target file does not exist after replace. "
                    f"Diagnostics: {diagnostics}"
                )
            
        except Exception as e:
            # Clean up temp file
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
            
            # Re-raise with diagnostics if not already included
            if "Diagnostics:" not in str(e):
                raise RuntimeError(
                    f"Atomic write failed: {type(e).__name__}: {e}. "
                    f"Diagnostics: {diagnostics}"
                ) from e
            else:
                raise
