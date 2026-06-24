"""Service layer for running backups and updating persisted profile state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.engines.folder_backup_engine import FolderBackupEngine
from app.engines.mysql_backup_engine import MySQLBackupEngine
from app.models.profile import FolderBackupProfile, MySQLBackupProfile, Profile
from app.models.result import BackupResult
from app.repositories.backup_metadata_repository import BackupMetadataRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.network_error_service import is_network_transient_error
from app.services.platform_service import PlatformService
from app.services.retention_service import RetentionService
from app.services.verification_service import VerificationService

ProgressCallback = Callable[[str], None]


class BackupService:
    """Coordinate backup execution for all profile types."""

    def __init__(
        self,
        repository: ProfileRepository,
        platform_service: PlatformService,
        log_service: LogService,
        *,
        metadata_repository: BackupMetadataRepository | None = None,
        verification_service: VerificationService | None = None,
        retention_service: RetentionService | None = None,
        mysql_engine: MySQLBackupEngine | None = None,
        folder_engine: FolderBackupEngine | None = None,
    ) -> None:
        self.repository = repository
        self.platform_service = platform_service
        self.log_service = log_service
        self.metadata_repository = metadata_repository or BackupMetadataRepository(repository.config_dir)
        self.verification_service = verification_service or VerificationService()
        self.retention_service = retention_service or RetentionService()
        self.mysql_engine = mysql_engine or MySQLBackupEngine(log_service)
        self.folder_engine = folder_engine or FolderBackupEngine(platform_service, log_service)
        self._run_lock = Lock()

    def list_profiles(self) -> list[Profile]:
        """Return all persisted profiles."""
        return self.repository.list_profiles()

    def is_running(self) -> bool:
        """Return whether a backup run is currently active."""
        return self._run_lock.locked()

    def run_profile(self, profile_id: str, progress: ProgressCallback | None = None) -> BackupResult:
        """Run a profile by id and persist the latest execution status."""
        if self._run_lock.locked() and progress:
            progress("Waiting for another backup to finish.")

        with self._run_lock:
            profile = self.repository.get_by_id(profile_id)
            if not profile:
                raise KeyError(f"Profile {profile_id} not found.")

            result = self._run(profile, progress)
            warnings = self._post_process_result(profile, result, progress)
            if warnings:
                result.message = self._build_warning_message(result, warnings)
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

    def _post_process_result(
        self,
        profile: Profile,
        result: BackupResult,
        progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Persist verification metadata and apply retention after a backup run."""
        if not result.success:
            return []

        warnings: list[str] = []

        try:
            warnings.extend(self._persist_backup_metadata(profile, result, progress))
        except Exception as exc:
            warning = self._format_post_backup_warning("verification", exc)
            warnings.append(warning)
            self._log_post_backup_warning(profile, result, "Verification", exc)

        try:
            retention_outcome = self.retention_service.apply_profile_retention(profile, self.metadata_repository)
            for entry in retention_outcome.deleted_entries:
                detail = (
                    f"Retention deleted {entry.output_file} "
                    f"(profile={profile.name}, retention_days={profile.retention_days})."
                )
                self._log_run_detail(result.log_file, detail)
                self.log_service.log_app(detail)
                if progress:
                    progress(detail)
            for warning in retention_outcome.warnings:
                warnings.append(f"retention step: {warning}")
                self._log_run_detail(result.log_file, f"Retention warning: {warning}")
                self.log_service.log_app(f"Profile '{profile.name}': Retention warning: {warning}")
        except Exception as exc:
            warning = self._format_post_backup_warning("retention", exc)
            warnings.append(warning)
            self._log_post_backup_warning(profile, result, "Retention", exc)

        return warnings

    def _persist_backup_metadata(
        self,
        profile: Profile,
        result: BackupResult,
        progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Compute and persist verification metadata for a completed file backup."""
        if not result.success or not result.output_file:
            return []

        warnings: list[str] = []
        output_path = Path(result.output_file)
        try:
            if not output_path.exists() or not output_path.is_file():
                return warnings
        except Exception as exc:
            if is_network_transient_error(exc, output_path, destination_type=profile.destination_type):
                warning = f"verification step: {type(exc).__name__}: {exc}"
                warnings.append(warning)
                self._log_run_detail(result.log_file, f"Verification warning: {type(exc).__name__}: {exc}")
                self.log_service.log_app(
                    f"Profile '{profile.name}': Verification warning: {type(exc).__name__}: {exc}"
                )
                return warnings
            raise

        verification_outcome = self.verification_service.build_metadata_outcome(
            result,
            destination_type=profile.destination_type,
        )
        if verification_outcome.warning:
            warnings.append(f"verification step: {verification_outcome.warning}")
            self._log_run_detail(result.log_file, f"Verification warning: {verification_outcome.warning}")
            self.log_service.log_app(
                f"Profile '{profile.name}': Verification warning: {verification_outcome.warning}"
            )
            return warnings

        metadata = verification_outcome.metadata
        if metadata is None:
            return warnings
        try:
            self.metadata_repository.add(metadata)
        except Exception as exc:
            warning = self._format_post_backup_warning("metadata", exc)
            warnings.append(warning)
            self._log_post_backup_warning(profile, result, "Metadata", exc)
            return warnings
        result.sha256 = metadata.sha256
        result.file_size_bytes = metadata.file_size_bytes

        detail = f"SHA256: {metadata.sha256} | Size: {metadata.file_size_bytes} bytes"
        self._log_run_detail(result.log_file, detail)
        self.log_service.log_app(f"Verified backup for '{result.profile_name}': {detail}")
        if progress:
            progress(detail)
        return warnings

    def _build_warning_message(self, result: BackupResult, warnings: list[str]) -> str:
        """Merge non-fatal post-backup warnings into the user-facing result message."""
        summary = "; ".join(warnings)
        if result.backup_type == "mysql" and result.success:
            if result.message == "MySQL backup completed successfully.":
                return f"MySQL backup completed successfully, but post-backup verification failed: {summary}"
            return f"{result.message} Post-backup verification warning: {summary}".strip()
        return f"{result.message} {' '.join(warnings)}".strip()

    @staticmethod
    def _format_post_backup_warning(step: str, exc: Exception) -> str:
        """Create a concise warning summary for UI-facing result messages."""
        return f"{step} step: {type(exc).__name__}: {exc}"

    def _log_post_backup_warning(
        self,
        profile: Profile,
        result: BackupResult,
        label: str,
        exc: Exception,
    ) -> None:
        """Record a non-fatal post-backup warning with the full exception text."""
        warning = f"{label} warning: {type(exc).__name__}: {exc}"
        self._log_run_detail(result.log_file, warning)
        self.log_service.log_app(f"Profile '{profile.name}': {warning}")

    def _log_run_detail(self, log_file: str | None, message: str) -> None:
        """Append a backup detail line to the run log when available."""
        if not log_file:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        with Path(log_file).open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} [INFO] {message}\n")
