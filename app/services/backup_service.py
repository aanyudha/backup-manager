"""Service layer for running backups and updating persisted profile state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from app.engines.folder_backup_engine import FolderBackupEngine
from app.engines.mysql_backup_engine import MySQLBackupEngine
from app.models.profile import FolderBackupProfile, MySQLBackupProfile, Profile
from app.models.result import BackupResult
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.platform_service import PlatformService

ProgressCallback = Callable[[str], None]


class BackupService:
    """Coordinate backup execution for all profile types."""

    def __init__(
        self,
        repository: ProfileRepository,
        platform_service: PlatformService,
        log_service: LogService,
    ) -> None:
        self.repository = repository
        self.platform_service = platform_service
        self.log_service = log_service
        self.mysql_engine = MySQLBackupEngine(log_service)
        self.folder_engine = FolderBackupEngine(platform_service, log_service)

    def list_profiles(self) -> list[Profile]:
        """Return all persisted profiles."""
        return self.repository.list_profiles()

    def run_profile(self, profile_id: str, progress: ProgressCallback | None = None) -> BackupResult:
        """Run a profile by id and persist the latest execution status."""
        profile = self.repository.get_by_id(profile_id)
        if not profile:
            raise KeyError(f"Profile {profile_id} not found.")

        result = self._run(profile, progress)
        refreshed = self.repository.get_by_id(profile_id)
        if refreshed is None:
            raise KeyError(f"Profile {profile_id} disappeared during execution.")
        refreshed.last_run_at = result.finished_at.astimezone(timezone.utc)
        refreshed.last_status = "success" if result.success else "failed"
        refreshed.last_message = result.message
        refreshed.updated_at = result.finished_at.astimezone(timezone.utc)
        self.repository.update(refreshed)
        self.log_service.log_app(
            f"Profile '{profile.name}' finished with status={refreshed.last_status}: {result.message}"
        )
        return result

    def _run(self, profile: Profile, progress: ProgressCallback | None = None) -> BackupResult:
        """Dispatch a profile to the correct engine."""
        if isinstance(profile, MySQLBackupProfile):
            return self.mysql_engine.run(profile, progress)
        if isinstance(profile, FolderBackupProfile):
            return self.folder_engine.run(profile, progress)
        raise RuntimeError(f"Unsupported profile model: {type(profile).__name__}")

