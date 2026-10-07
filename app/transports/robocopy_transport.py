"""Windows robocopy transport."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

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
        """Build the robocopy command for the selected mode.

        Source and destination are passed through exactly as configured so
        mapped-drive destinations such as ``Z:\\cctv`` are never rewritten.
        """
        if not self.platform_service.is_windows():
            raise RuntimeError("robocopy is only supported on Windows.")
        source = profile.source
        destination = profile.destination
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
        """Execute robocopy and normalize its success semantics.

        Robocopy creates the destination folder itself, so no Python ``mkdir``,
        temp file, or write probe runs before the command.
        """
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        command = self.build_command(profile)
        logger.info("Command: %s", " ".join(command))
        if progress:
            progress(f"Source: {profile.source}")
            progress(f"Destination: {profile.destination}")

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()
        output_text = "\n".join(part for part in (stdout_text, stderr_text) if part)
        logger.info("Robocopy exit code %s", completed.returncode)
        if output_text:
            logger.info("Robocopy output:\n%s", output_text)

        success = completed.returncode < 8
        if success:
            status_lines = [
                f"Robocopy exit code: {completed.returncode}",
                "Backup completed successfully.",
            ]
        else:
            status_lines = ["Robocopy backup failed.", f"Exit code: {completed.returncode}"]
            if output_text:
                status_lines.append(output_text)
        message = "\n".join(status_lines)
        logger.info(message)
        if progress:
            for line in status_lines:
                progress(line)

        return self.build_result(
            success=success,
            profile=profile,
            started_at=started_at,
            message=message,
            log_file=str(log_path),
            exit_code=completed.returncode,
            output_file=profile.destination,
        )

