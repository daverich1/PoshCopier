from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build


class BuildSecurityTests(unittest.TestCase):
    def _create_release_layout(self, root: Path) -> tuple[Path, Path]:
        dashboard_dir = root / "PoshCopier"
        pipeline_dir = dashboard_dir / "PoshCopierPipeline"

        for directory in (
            dashboard_dir / "_internal",
            pipeline_dir / "_internal",
            dashboard_dir / "pw-browsers",
            dashboard_dir / "downloads",
            dashboard_dir / "logs",
        ):
            directory.mkdir(parents=True, exist_ok=True)

        (dashboard_dir / "PoshCopier.exe").touch()
        (pipeline_dir / "PoshCopierPipeline.exe").touch()
        (dashboard_dir / "downloads" / "discovered_listings.json").write_text(
            "[]",
            encoding="utf-8",
        )

        return dashboard_dir, pipeline_dir

    def test_release_verification_accepts_layout_without_session_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard_dir, pipeline_dir = self._create_release_layout(
                Path(temp_dir)
            )

            with (
                patch.object(build, "DASHBOARD_BUILD_DIR", dashboard_dir),
                patch.object(build, "EMBEDDED_PIPELINE_DIR", pipeline_dir),
            ):
                build.verify_release()

    def test_release_verification_rejects_every_session_state_filename(self):
        relative_paths = [
            Path(filename)
            for filename in build.SESSION_STATE_FILENAMES
        ] + [
            Path("PoshCopierPipeline") / filename
            for filename in build.SESSION_STATE_FILENAMES
        ]

        for relative_path in relative_paths:
            with self.subTest(relative_path=relative_path):
                with tempfile.TemporaryDirectory() as temp_dir:
                    dashboard_dir, pipeline_dir = self._create_release_layout(
                        Path(temp_dir)
                    )
                    (dashboard_dir / relative_path).write_text(
                        "{}",
                        encoding="utf-8",
                    )

                    with (
                        patch.object(build, "DASHBOARD_BUILD_DIR", dashboard_dir),
                        patch.object(build, "EMBEDDED_PIPELINE_DIR", pipeline_dir),
                    ):
                        with self.assertRaises(build.BuildError):
                            build.verify_release()

    def test_release_assembly_has_no_session_copy_source(self):
        source = inspect.getsource(build.assemble_release_folder)

        for filename in build.SESSION_STATE_FILENAMES:
            self.assertNotIn(filename, source)


if __name__ == "__main__":
    unittest.main()
