"""Regression tests for upload queue progress summaries."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dashboard.upload_queue_panel import UploadQueuePanel
from inventory.upload_queue import (
    QueueEntry,
    QueueStatus,
    UploadQueueManager,
    UploadQueueState,
)


class UploadQueueProgressTests(unittest.TestCase):
    def test_progress_summary_counts_terminal_entries_as_completed(self):
        manager = UploadQueueManager()
        statuses = (
            QueueStatus.UPLOADED,
            QueueStatus.ALREADY_EXISTS,
            QueueStatus.FAILED,
            QueueStatus.SKIPPED,
            QueueStatus.CANCELLED,
            QueueStatus.PUBLISH_UNVERIFIED,
            QueueStatus.WAITING,
            QueueStatus.PENDING,
            QueueStatus.RUNNING,
        )
        manager.state = UploadQueueState(
            queue_id="test",
            entries=[
                QueueEntry(str(index), f"Item {index}", Path("listing.json"), status)
                for index, status in enumerate(statuses)
            ],
        )

        summary = manager.progress_summary()

        self.assertEqual(summary["completed"], 6)
        self.assertEqual(summary["remaining"], 3)
        self.assertAlmostEqual(summary["percent"], 6 / 9 * 100)

    def test_panel_refresh_does_not_create_completion_report(self):
        summary = {
            "total": 1,
            "waiting": 1,
            "pending": 0,
            "running": 0,
            "uploaded": 0,
            "already_exists": 0,
            "failed": 0,
            "skipped": 0,
            "remaining": 1,
            "percent": 0.0,
        }
        manager = Mock()
        manager.load.return_value = SimpleNamespace(entries=[object()])
        manager.progress_summary.return_value = summary
        variables = {
            name: Mock()
            for name in (
                "total_var",
                "waiting_var",
                "pending_var",
                "running_var",
                "uploaded_var",
                "already_exists_var",
                "failed_var",
                "skipped_var",
                "remaining_var",
                "percent_var",
            )
        }
        panel = SimpleNamespace(
            queue_manager=manager,
            progress_bar={},
            _hide_empty_state=Mock(),
            _show_empty_state=Mock(),
            _populate_tree=Mock(),
            _update_button_states=Mock(),
            **variables,
        )

        with patch("dashboard.upload_queue_panel.save_batch_report") as save_report:
            UploadQueuePanel.refresh(panel)

        save_report.assert_not_called()
        panel._hide_empty_state.assert_called_once_with()
        self.assertEqual(panel.progress_bar["value"], 0.0)


if __name__ == "__main__":
    unittest.main()
