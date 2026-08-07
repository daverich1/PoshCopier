from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, sync_playwright

from inventory.inventory_item import InventoryItem
from inventory.inventory_manager import InventoryManager
from inventory.upload_queue import UploadQueueManager
from runtime_paths import DOWNLOADS_DIR, LOGS_DIR, SOURCE_STATE_FILE
from scraper.discover import DiscoveredListing, discover_closet
from scraper.listing_scraper import scrape_listing


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
        self.source_closet_url = source_closet_url
        self.downloads_dir = downloads_dir
        self.source_state_file = source_state_file
        self.progress_callback = progress_callback

        self._setup_logging(log_file)

    def _setup_logging(self, log_file: Path | None) -> None:
        """Configure logging to file."""
        if log_file is None:
            log_file = LOGS_DIR / "closet_sync.log"

        log_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("closet_sync")
        self.logger.setLevel(logging.INFO)

        # Remove existing handlers
        self.logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _is_already_downloaded(self, listing_id: str) -> bool:
        """Check if listing already exists in downloads directory."""
        listing_file = self.downloads_dir / listing_id / "listing.json"
        return listing_file.exists()

    def _report_progress(self, message: str) -> None:
        """Report progress via callback and logging."""
        try:
            self.logger.info(message)
        except Exception:
            pass  # Logging failure is non-critical

        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                pass  # Callback failure is non-critical

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
        self._report_progress("Scanning source closet...")

        try:
            discovered = discover_closet(
                page,
                self.source_closet_url,
                max_scrolls=600,
                stable_rounds_required=8,
                scroll_pause_ms=1200,
                progress_path=None,
                downloads_dir=self.downloads_dir,
                incremental_threshold=50,
            )

            self._report_progress(f"Found {len(discovered)} listings in closet")
            return discovered

        except Exception as error:
            error_msg = f"Failed to scan closet: {error}"
            self.logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from error

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
        # Build set of existing listing IDs
        existing_ids = set()
        if self.downloads_dir.exists():
            for listing_dir in self.downloads_dir.iterdir():
                if listing_dir.is_dir():
                    listing_file = listing_dir / "listing.json"
                    if listing_file.exists():
                        existing_ids.add(listing_dir.name)

        # Filter to only new, available listings
        to_download = [
            item
            for item in discovered
            if item.available and item.listing_id not in existing_ids
        ]

        already_downloaded = len(discovered) - len(to_download)
        self._report_progress(f"{already_downloaded} already downloaded")
        self._report_progress(f"{len(to_download)} new listings to download")

        if not to_download:
            return [], []

        # Download each new listing sequentially
        successful = []
        failed = []

        for index, item in enumerate(to_download, start=1):
            try:
                # Truncate title for display
                display_title = item.title[:50]
                if len(item.title) > 50:
                    display_title += "..."

                self._report_progress(
                    f"Downloading {index}/{len(to_download)}: {display_title}"
                )

                # scrape_listing() automatically saves to disk
                scrape_listing(page, item.url)

                successful.append(item.listing_id)
                self.logger.info(f"Downloaded: {item.listing_id} - {item.title}")

            except Exception as error:
                error_msg = str(error)
                failed.append((item.listing_id, error_msg))
                self.logger.error(
                    f"Failed to download {item.listing_id}: {error_msg}"
                )
                # Continue with remaining listings

        return successful, failed

    def build_inventory(self) -> list[InventoryItem]:
        """
        Reload inventory from disk.

        Returns:
            Complete list of inventory items
        """
        try:
            manager = InventoryManager(self.downloads_dir)
            items = manager.load_items()
            self._report_progress(f"Inventory loaded: {len(items)} items")
            return items

        except Exception as error:
            self.logger.error(f"Inventory reload failed: {error}")
            self._report_progress("Warning: Inventory reload failed")
            return []  # Return empty list, don't abort sync

    def queue_ready(self, new_ids: list[str]) -> int:
        """
        Queue newly downloaded listings that are Ready.

        Args:
            new_ids: List of newly downloaded listing IDs

        Returns:
            Number of items queued
        """
        if not new_ids:
            return 0

        try:
            # Load inventory
            manager = InventoryManager(self.downloads_dir)
            all_items = manager.load_items()

            # Filter to new items that are ready
            new_items = [
                item
                for item in all_items
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

    def run(self) -> SyncResult:
        """
        Execute complete sync workflow.

        Returns:
            SyncResult with statistics and errors
        """
        start_time = time.time()
        stats = SyncStats()

        try:
            # Validate prerequisites
            if not self.source_state_file.exists():
                raise FileNotFoundError(
                    f"Source authentication not found: {self.source_state_file}"
                )

            self._report_progress("Starting closet sync...")
            self.logger.info(f"Source closet URL: {self.source_closet_url}")

            # Launch browser
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(self.source_state_file),
                    viewport={"width": 1440, "height": 1000},
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

            self.logger.info(
                f"Sync complete: {stats.new_imported} imported, "
                f"{len(stats.failed)} failed, {stats.queued} queued"
            )

            return SyncResult(success=True, stats=stats)

        except Exception as error:
            # Critical failure - abort sync
            stats.elapsed_seconds = time.time() - start_time
            error_msg = str(error)
            self.logger.error(f"Sync failed: {error_msg}", exc_info=True)

            return SyncResult(
                success=False,
                stats=stats,
                error_message=error_msg,
            )
