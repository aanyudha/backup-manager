"""Cross-platform local folder copy transport."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.transports.base import BaseTransport, ProgressCallback


class LocalCopyTransport(BaseTransport):
    """Copy files using the local filesystem."""

    def __init__(self, log_service: LogService) -> None:
        super().__init__(log_service)

    def run(self, profile: FolderBackupProfile, progress: ProgressCallback | None = None):
        """Copy files according to the selected synchronization mode."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        source = Path(profile.source).expanduser()
        destination = Path(profile.destination).expanduser()

        if not source.exists():
            raise FileNotFoundError(f"Source folder not found: {source}")
        destination.mkdir(parents=True, exist_ok=True)

        copied_files = 0
        deleted_files = 0
        logger.info("Starting local copy: %s -> %s (%s)", source, destination, profile.mode)
        if progress:
            progress(f"Copying files from {source} to {destination}...")

        for root, _, files in os.walk(source):
            root_path = Path(root)
            relative_root = root_path.relative_to(source)
            target_root = destination / relative_root
            target_root.mkdir(parents=True, exist_ok=True)

            for file_name in files:
                source_file = root_path / file_name
                target_file = target_root / file_name
                should_copy = not target_file.exists() or source_file.stat().st_mtime > target_file.stat().st_mtime
                if should_copy:
                    shutil.copy2(source_file, target_file)
                    copied_files += 1
                    logger.info("Copied %s", source_file)

        if profile.mode == "mirror_with_delete":
            for root, _, files in os.walk(destination, topdown=False):
                root_path = Path(root)
                relative_root = root_path.relative_to(destination)
                source_root = source / relative_root
                for file_name in files:
                    destination_file = root_path / file_name
                    source_file = source_root / file_name
                    if not source_file.exists():
                        destination_file.unlink()
                        deleted_files += 1
                        logger.info("Deleted %s", destination_file)
                if root_path != destination and not any(root_path.iterdir()) and not source_root.exists():
                    root_path.rmdir()

        message = f"Copied {copied_files} file(s)"
        if profile.mode == "mirror_with_delete":
            message += f"; deleted {deleted_files} file(s)"
        logger.info(message)
        if progress:
            progress(message)

        return self.build_result(
            success=True,
            profile=profile,
            started_at=started_at,
            message=message,
            log_file=str(log_path),
            output_file=str(destination),
        )

