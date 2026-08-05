from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


PROJECT_DIR = Path(__file__).resolve().parent

BUILD_DIR = PROJECT_DIR / "build"
DIST_DIR = PROJECT_DIR / "dist"

DASHBOARD_BUILD_DIR = DIST_DIR / "PoshCopier"
PIPELINE_BUILD_DIR = DIST_DIR / "PoshCopierPipeline"
EMBEDDED_PIPELINE_DIR = (
    DASHBOARD_BUILD_DIR
    / "PoshCopierPipeline"
)

APP_ENTRY = PROJECT_DIR / "app.py"
PIPELINE_ENTRY = PROJECT_DIR / "pipeline_entry.py"

PLAYWRIGHT_BROWSERS_DIR = (
    PROJECT_DIR
    / "pw-browsers"
)
DOWNLOADS_DIR = PROJECT_DIR / "downloads"

SOURCE_STATE_FILE = (
    PROJECT_DIR
    / "source_state.json"
)
DESTINATION_STATE_FILE = (
    PROJECT_DIR
    / "destination_state.json"
)
DATABASE_FILE = PROJECT_DIR / "poshcopier.db"

DASHBOARD_SPEC = (
    PROJECT_DIR
    / "PoshCopier.spec"
)
PIPELINE_SPEC = (
    PROJECT_DIR
    / "PoshCopierPipeline.spec"
)


class BuildError(RuntimeError):
    pass


def print_section(
    title: str,
) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def require_file(
    path: Path,
) -> None:
    if not path.is_file():
        raise BuildError(
            f"Required file was not found:\n{path}"
        )


def require_directory(
    path: Path,
) -> None:
    if not path.is_dir():
        raise BuildError(
            f"Required folder was not found:\n{path}"
        )


def run_command(
    command: Iterable[str],
) -> None:
    command_list = [
        str(value)
        for value in command
    ]

    print()
    print(
        ">",
        subprocess.list2cmdline(
            command_list
        ),
    )

    completed = subprocess.run(
        command_list,
        cwd=str(PROJECT_DIR),
        check=False,
    )

    if completed.returncode != 0:
        raise BuildError(
            "Command failed with exit code "
            f"{completed.returncode}."
        )


def remove_path(
    path: Path,
) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def clean_build_output() -> None:
    print_section(
        "CLEANING OLD BUILD OUTPUT"
    )

    remove_path(
        BUILD_DIR
    )
    remove_path(
        DIST_DIR
    )
    remove_path(
        DASHBOARD_SPEC
    )
    remove_path(
        PIPELINE_SPEC
    )

    print(
        "Old build output removed."
    )


def validate_source_project() -> None:
    print_section(
        "VALIDATING SOURCE PROJECT"
    )

    for path in (
        APP_ENTRY,
        PIPELINE_ENTRY,
        PROJECT_DIR / "run_pipeline.py",
        PROJECT_DIR / "runtime_paths.py",
        PROJECT_DIR / "login.py",
        PROJECT_DIR / "pipeline_control.py",
        PROJECT_DIR / "dashboard" / "dashboard.py",
    ):
        require_file(path)

    for path in (
        PLAYWRIGHT_BROWSERS_DIR,
        DOWNLOADS_DIR,
    ):
        require_directory(path)

    for path in (
        SOURCE_STATE_FILE,
        DESTINATION_STATE_FILE,
    ):
        require_file(path)

    require_file(
        DOWNLOADS_DIR
        / "discovered_listings.json"
    )

    print(
        "Required project files are present."
    )


def build_pipeline() -> None:
    print_section(
        "BUILDING POSHCOPIER PIPELINE"
    )

    run_command(
        (
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--console",
            "--name",
            "PoshCopierPipeline",
            "--collect-all",
            "playwright",
            "--collect-all",
            "PIL",
            str(PIPELINE_ENTRY),
        )
    )

    require_file(
        PIPELINE_BUILD_DIR
        / "PoshCopierPipeline.exe"
    )
    require_directory(
        PIPELINE_BUILD_DIR
        / "_internal"
    )

    print(
        "Pipeline executable built successfully."
    )


def build_dashboard() -> None:
    print_section(
        "BUILDING POSHCOPIER DASHBOARD"
    )

    run_command(
        (
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "PoshCopier",
            "--collect-all",
            "PIL",
            str(APP_ENTRY),
        )
    )

    require_file(
        DASHBOARD_BUILD_DIR
        / "PoshCopier.exe"
    )
    require_directory(
        DASHBOARD_BUILD_DIR
        / "_internal"
    )

    print(
        "Dashboard executable built successfully."
    )


def copy_directory_contents(
    source: Path,
    destination: Path,
) -> None:
    require_directory(
        source
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    for child in source.iterdir():
        if child.name in {
            "downloads",
            "logs",
            "__pycache__",
        }:
            continue

        target = destination / child.name

        if child.is_dir():
            shutil.copytree(
                child,
                target,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                ),
            )
        else:
            shutil.copy2(
                child,
                target,
            )


def assemble_release_folder() -> None:
    print_section(
        "ASSEMBLING FINAL APPLICATION"
    )

    remove_path(
        EMBEDDED_PIPELINE_DIR
    )

    shutil.copytree(
        PIPELINE_BUILD_DIR,
        EMBEDDED_PIPELINE_DIR,
    )

    print(
        "Embedded pipeline copied."
    )

    final_browsers = (
        DASHBOARD_BUILD_DIR
        / "pw-browsers"
    )
    remove_path(
        final_browsers
    )

    shutil.copytree(
        PLAYWRIGHT_BROWSERS_DIR,
        final_browsers,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
        ),
    )

    print(
        "Playwright browsers copied."
    )

    final_downloads = (
        DASHBOARD_BUILD_DIR
        / "downloads"
    )
    remove_path(
        final_downloads
    )

    copy_directory_contents(
        DOWNLOADS_DIR,
        final_downloads,
    )

    print(
        "Downloaded listing data copied."
    )

    shutil.copy2(
        SOURCE_STATE_FILE,
        DASHBOARD_BUILD_DIR
        / SOURCE_STATE_FILE.name,
    )
    shutil.copy2(
        DESTINATION_STATE_FILE,
        DASHBOARD_BUILD_DIR
        / DESTINATION_STATE_FILE.name,
    )

    print(
        "Login state files copied."
    )

    if DATABASE_FILE.exists():
        shutil.copy2(
            DATABASE_FILE,
            DASHBOARD_BUILD_DIR
            / DATABASE_FILE.name,
        )
        print(
            "Runtime database copied."
        )
    else:
        print(
            "Runtime database not present; "
            "the app will create it when needed."
        )

    (
        DASHBOARD_BUILD_DIR
        / "logs"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Logs folder created."
    )


def verify_release() -> None:
    print_section(
        "VERIFYING FINAL APPLICATION"
    )

    required_files = (
        DASHBOARD_BUILD_DIR
        / "PoshCopier.exe",
        EMBEDDED_PIPELINE_DIR
        / "PoshCopierPipeline.exe",
        DASHBOARD_BUILD_DIR
        / "source_state.json",
        DASHBOARD_BUILD_DIR
        / "destination_state.json",
        DASHBOARD_BUILD_DIR
        / "downloads"
        / "discovered_listings.json",
    )

    required_directories = (
        DASHBOARD_BUILD_DIR
        / "_internal",
        EMBEDDED_PIPELINE_DIR
        / "_internal",
        DASHBOARD_BUILD_DIR
        / "pw-browsers",
        DASHBOARD_BUILD_DIR
        / "downloads",
        DASHBOARD_BUILD_DIR
        / "logs",
    )

    for path in required_files:
        require_file(path)
        print(
            "OK:",
            path.relative_to(
                DASHBOARD_BUILD_DIR
            ),
        )

    for path in required_directories:
        require_directory(path)
        print(
            "OK:",
            path.relative_to(
                DASHBOARD_BUILD_DIR
            ),
        )

    accidental_paths = (
        DASHBOARD_BUILD_DIR
        / "downloads"
        / "downloads",
        DASHBOARD_BUILD_DIR
        / "downloads"
        / "logs",
    )

    for path in accidental_paths:
        if path.exists():
            raise BuildError(
                "Accidental nested runtime folder found:\n"
                f"{path}"
            )

    print()
    print(
        "Final application folder:"
    )
    print(
        DASHBOARD_BUILD_DIR
    )


def main() -> None:
    try:
        validate_source_project()
        clean_build_output()
        build_pipeline()
        build_dashboard()
        assemble_release_folder()
        verify_release()

    except (
        BuildError,
        OSError,
    ) as error:
        print()
        print("=" * 72)
        print("BUILD FAILED")
        print("=" * 72)
        print(error)
        raise SystemExit(1) from error

    print()
    print("=" * 72)
    print("BUILD COMPLETE")
    print("=" * 72)
    print(
        "Launch:"
    )
    print(
        DASHBOARD_BUILD_DIR
        / "PoshCopier.exe"
    )


if __name__ == "__main__":
    main()
