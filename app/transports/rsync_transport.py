"""rsync-based folder transport."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.base import BaseTransport, ProgressCallback


class RsyncTransport(BaseTransport):
    """Execute rsync for local or remote folder synchronization."""

    def __init__(self, log_service: LogService, platform_service: PlatformService) -> None:
        super().__init__(log_service)
        self.platform_service = platform_service

    @staticmethod
    def _looks_like_rsync_remote(value: str) -> bool:
        """Return whether a path resembles rsync remote syntax."""
        cleaned = value.strip()
        if not cleaned or cleaned.startswith("\\\\"):
            return False
        if re.match(r"^[A-Za-z]:[\\/]", cleaned):
            return False
        return bool(
            re.match(r"^[^@\s:/\\]+@[^:\s]+:.+", cleaned)
            or re.match(r"^[A-Za-z0-9._-]+:.+", cleaned)
        )

    def build_command(self, profile: FolderBackupProfile) -> list[str]:
        """Create the rsync command for the given profile."""
        if not self.platform_service.command_exists("rsync"):
            raise RuntimeError("rsync is not installed.")

        command = ["rsync", "-a"]
        if profile.mode == "mirror_with_delete":
            command.extend(["--delete", "--progress"])
        else:
            command.extend(["--update", "--progress"])
        command.extend(profile.rsync_extra_args)
        command.extend([profile.source, profile.destination])
        return command

    def run(self, profile: FolderBackupProfile, progress: ProgressCallback | None = None):
        """Run rsync and return a normalized result."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        destination = profile.destination
        if profile.destination_type == "network" or not self._looks_like_rsync_remote(destination):
            Path(destination).mkdir(parents=True, exist_ok=True)

        command = self.build_command(profile)
        logger.info("Command: %s", " ".join(command))
        if progress:
            progress("Running rsync...")

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        success = completed.returncode == 0
        message = (completed.stdout or completed.stderr or "").strip() or "rsync finished."
        logger.info("rsync exit code %s", completed.returncode)
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
