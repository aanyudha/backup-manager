"""Folder restore engine for overwrite-style local restores."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.engines.base import ProgressCallback
from app.models.restore_result import RestoreResult
from app.services.log_service import LogService


class FolderRestoreEngine:
    """Restore files from one local folder into another."""

    def __init__(self, log_service: LogService) -> None:
        self.log_service = log_service

    def validate_paths(self, source: str, destination: str) -> tuple[Path, Path]:
        """Validate and normalize restore paths."""
        source_path = Path(source).expanduser()
        destination_path = Path(destination).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Backup source folder not found: {source_path}")
        if not source_path.is_dir():
            raise ValueError(f"Backup source must be a folder: {source_path}")
        if destination_path.exists() and not destination_path.is_dir():
            raise ValueError(f"Restore destination must be a folder: {destination_path}")
        self.ensure_destination_writable(destination_path)
        return source_path, destination_path

    def ensure_destination_writable(self, destination_path: Path) -> None:
        """Create the destination when needed and verify that it can be written."""
        probe_path = destination_path / ".restore_write_test"
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
            with probe_path.open("wb") as handle:
                handle.write(b"ok")
        except OSError as exc:
            raise PermissionError(f"Restore destination is not writable: {destination_path}") from exc
        finally:
            try:
                probe_path.unlink(missing_ok=True)
            except Exception:
                pass

    def run(
        self,
        *,
        source: str,
        destination: str,
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        """Recursively copy a folder into the destination, overwriting existing files."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_restore_logger(started_at)
        source_path, destination_path = self.validate_paths(source, destination)
        logger.info("Starting folder restore.")
        logger.info("Source: %s", source_path)
        logger.info("Destination: %s", destination_path)

        if progress:
            progress(f"Restoring files from {source_path}...")

        copied_files = 0
        created_directories = 0
        for item in source_path.rglob("*"):
            relative_path = item.relative_to(source_path)
            target_path = destination_path / relative_path
            if item.is_dir():
                if not target_path.exists():
                    target_path.mkdir(parents=True, exist_ok=True)
                    created_directories += 1
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_path)
            copied_files += 1

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        message = (
            "Folder restore completed successfully. "
            f"Copied {copied_files} file(s) and created {created_directories} folder(s)."
        )
        logger.info("Copied files: %s", copied_files)
        logger.info("Created folders: %s", created_directories)
        logger.info("Duration: %.2f seconds", duration)
        logger.info("Result: %s", message)
        if progress:
            progress(message)

        return RestoreResult(
            success=True,
            restore_type="folder",
            source=str(source_path),
            destination=str(destination_path),
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            message=message,
            log_file=str(log_path),
        )
