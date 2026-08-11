from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from inventory.upload_queue import QueueStatus
from pipeline.upload_queue_processor import ProcessResult
from runtime_paths import LOGS_DIR


REPORTS_DIR = LOGS_DIR / "batch_reports"


def build_batch_report(
    results: Iterable[ProcessResult],
    queue_summary: dict[str, Any],
) -> dict[str, Any]:
    items = list(results)
    counts = {status.value: 0 for status in QueueStatus}
    failures: list[dict[str, Any]] = []

    for result in items:
        counts[result.status.value] += 1
        if result.status in (QueueStatus.FAILED, QueueStatus.PUBLISH_UNVERIFIED):
            failures.append(
                {
                    "listing_id": result.listing_id,
                    "status": result.status.value,
                    "message": result.message,
                    "exit_code": result.exit_code,
                }
            )

    duration_seconds = sum(max(0.0, result.duration_seconds) for result in items)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "processed": len(items),
        "duration_seconds": round(duration_seconds, 1),
        "counts": counts,
        "queue_remaining": int(queue_summary.get("remaining", 0)),
        "failures": failures,
    }


def render_batch_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# PoshCopier Batch Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Processed: {report['processed']}",
        f"Duration: {report['duration_seconds']:.1f} seconds",
        f"Queue remaining: {report['queue_remaining']}",
        "",
        "## Results",
        "",
        f"- Uploaded: {counts['uploaded']}",
        f"- Already exists: {counts['already_exists']}",
        f"- Skipped: {counts['skipped']}",
        f"- Failed: {counts['failed']}",
        f"- Publish unverified: {counts['publish_unverified']}",
        f"- Cancelled: {counts['cancelled']}",
    ]

    failures = report["failures"]
    if failures:
        lines.extend(["", "## Needs attention", ""])
        for failure in failures:
            lines.append(
                f"- `{failure['listing_id']}` — {failure['status']}: {failure['message']}"
            )
    else:
        lines.extend(["", "No failures or unverified publishes."])

    return "\n".join(lines) + "\n"


def save_batch_report(
    results: Iterable[ProcessResult],
    queue_summary: dict[str, Any],
    reports_dir: Path = REPORTS_DIR,
) -> tuple[Path, Path]:
    report = build_batch_report(results, queue_summary)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = reports_dir / f"batch-{stamp}.json"
    markdown_path = reports_dir / f"batch-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_batch_report(report), encoding="utf-8")
    return json_path, markdown_path
