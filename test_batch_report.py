from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inventory.batch_report import build_batch_report, save_batch_report
from inventory.upload_queue import QueueStatus
from pipeline.upload_queue_processor import ProcessResult


def result(listing_id: str, status: QueueStatus, seconds: float, message: str = "ok") -> ProcessResult:
    return ProcessResult(listing_id, status, 0, message, "start", "finish", seconds)


class BatchReportTests(unittest.TestCase):
    def test_report_counts_and_flags_attention_items(self):
        report = build_batch_report(
            [
                result("one", QueueStatus.UPLOADED, 2.5),
                result("two", QueueStatus.ALREADY_EXISTS, 1.0),
                result("three", QueueStatus.FAILED, 3.0, "timed out"),
            ],
            {"remaining": 4},
        )

        self.assertEqual(report["processed"], 3)
        self.assertEqual(report["duration_seconds"], 6.5)
        self.assertEqual(report["counts"]["uploaded"], 1)
        self.assertEqual(report["queue_remaining"], 4)
        self.assertEqual(report["failures"][0]["listing_id"], "three")

    def test_save_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path = save_batch_report(
                [result("one", QueueStatus.UPLOADED, 1.0)],
                {"remaining": 0},
                Path(directory),
            )

            self.assertEqual(json.loads(json_path.read_text())["processed"], 1)
            self.assertIn("No failures", markdown_path.read_text())


if __name__ == "__main__":
    unittest.main()
