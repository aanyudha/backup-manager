"""Helpers for local staging before copying to UNC destinations."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import sub

from app.services.log_service import LogService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService


@dataclass(slots=True)
class RobocopyResult:
    """Normalized robocopy execution details."""

    command: list[str]
    returncode: int
    output: str

    @property
    def success(self) -> bool:
        """Return whether robocopy reported success."""
        return self.returncode < 8


class StagingService:
    """Create and manage temporary staging folders for remote backups."""

    def __init__(
        self,
        *,
        path_service: PathService | None = None,
        platform_service: PlatformService | None = None,
        log_service: LogService | None = None,
    ) -> None:
        self.path_service = path_service or PathService()
        self.platform_service = platform_service or PlatformService()
        self.log_service = log_service

    def create_staging_folder(self, profile_name_or_id: str) -> Path:
        """Create a timestamped staging folder under the runtime temp root."""
        safe_name = self.log_service.safe_name(profile_name_or_id) if self.log_service is not None else sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            profile_name_or_id.strip(),
        ).strip("_") or "backup"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        staging_path = self.path_service.temp_dir() / "heisenberg_staging" / safe_name / timestamp
        staging_path.mkdir(parents=True, exist_ok=False)
        return staging_path

    @staticmethod
    def cleanup_staging_folder(path: Path | str) -> None:
        """Remove one staging folder tree when it still exists."""
        shutil.rmtree(Path(path), ignore_errors=True)

    def copy_staging_to_destination_with_robocopy(
        self,
        staging: Path | str,
        destination: Path | str,
    ) -> RobocopyResult:
        """Copy staged files into the destination root with robocopy."""
        if not self.platform_service.is_windows():
            raise RuntimeError("Staging robocopy fallback is supported only on Windows.")
        if not self.platform_service.command_exists("robocopy"):
            raise RuntimeError("robocopy is required for UNC staging fallback.")

        staging_path = Path(staging)
        destination_path = Path(destination)
        command = [
            "robocopy",
            str(staging_path),
            str(destination_path),
            "*.*",
            "/E",
            "/DCOPY:DA",
            "/COPY:DAT",
            "/R:3",
            "/W:3",
            "/MT:8",
            "/FFT",
            "/TEE",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        output = (completed.stdout or completed.stderr or "").strip() or "robocopy finished."
        return RobocopyResult(
            command=command,
            returncode=completed.returncode,
            output=output,
        )
