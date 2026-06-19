"""Base transport abstraction for folder backups."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone

from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService

ProgressCallback = Callable[[str], None]


class BaseTransport(ABC):
    """Common behavior for folder backup transports."""

    def __init__(self, log_service: LogService) -> None:
        self.log_service = log_service

    @abstractmethod
    def run(self, profile: FolderBackupProfile, progress: ProgressCallback | None = None) -> BackupResult:
        """Execute the folder backup transport."""

    def build_result(
        self,
        *,
        success: bool,
        profile: FolderBackupProfile,
        started_at: datetime,
        message: str,
        log_file: str | None,
        exit_code: int | None = None,
        output_file: str | None = None,
    ) -> BackupResult:
        """Create a consistent BackupResult for transport runs."""
        return BackupResult(
            success=success,
            backup_type="folder",
            profile_id=profile.id,
            profile_name=profile.name,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            exit_code=exit_code,
            message=message,
            log_file=log_file,
            output_file=output_file,
        )
