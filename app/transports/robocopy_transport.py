"""Windows robocopy transport."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.base import BaseTransport, ProgressCallback


class RobocopyTransport(BaseTransport):
    """Run robocopy for fast Windows folder synchronization."""

    def __init__(self, log_service: LogService, platform_service: PlatformService) -> None:
        super().__init__(log_service)
        self.platform_service = platform_service

    def build_command(self, profile: FolderBackupProfile) -> list[str]:
        """Build the robocopy command for the selected mode."""
        if not self.platform_service.is_windows():
            raise RuntimeError("robocopy is only supported on Windows.")
        source = str(Path(profile.source))
        destination = str(Path(profile.destination))
        base = [
            "robocopy",
            source,
            destination,
            "*.*",
            "/E",
            "/DCOPY:DA",
            "/COPY:DAT",
            "/R:10",
            "/W:5",
            "/MT:16",
            "/FFT",
            "/ETA",
            "/TEE",
        ]
        if profile.mode == "mirror_with_delete":
            return [
                "robocopy",
                source,
                destination,
                "*.*",
                "/MIR",
                "/DCOPY:DA",
                "/COPY:DAT",
                "/R:10",
                "/W:5",
                "/MT:16",
                "/FFT",
                "/ETA",
                "/TEE",
            ]
        base.append("/XO")
        return base

    def run(self, profile: FolderBackupProfile, progress: ProgressCallback | None = None):
        """Execute robocopy and normalize its success semantics."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        Path(profile.destination).mkdir(parents=True, exist_ok=True)
        command = self.build_command(profile)
        logger.info("Command: %s", " ".join(command))
        if progress:
            progress("Running robocopy...")

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        success = completed.returncode < 8
        message = (completed.stdout or completed.stderr or "").strip() or "robocopy finished."
        logger.info("Robocopy exit code %s", completed.returncode)
        logger.info(message)
        if progress:
            progress(message)

        return self.build_result(
            success=success,
            profile=profile,
            started_at=started_at,
            message=message,
            log_file=str(log_path),
            exit_code=completed.returncode,
            output_file=profile.destination,
        )

