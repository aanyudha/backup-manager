"""Retention helpers for pruning known backup artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.backup_metadata import BackupMetadata
from app.models.profile import Profile
from app.repositories.backup_metadata_repository import BackupMetadataRepository
from app.services.network_error_service import is_network_transient_error


@dataclass(frozen=True)
class RetentionOutcome:
    """Deleted entries plus non-fatal retention warnings."""

    deleted_entries: list[BackupMetadata]
    warnings: list[str]


class RetentionService:
    """Delete expired backup files that were previously recorded in metadata."""

    def apply_profile_retention(
        self,
        profile: Profile,
        metadata_repository: BackupMetadataRepository,
    ) -> RetentionOutcome:
        """Delete expired artifacts for one profile and mark their metadata."""
        if not profile.retention_enabled:
            return RetentionOutcome(deleted_entries=[], warnings=[])
        if profile.retention_days is None or profile.retention_days <= 0:
            return RetentionOutcome(deleted_entries=[], warnings=[])

        deleted_entries: list[BackupMetadata] = []
        warnings: list[str] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=profile.retention_days)
        for metadata in metadata_repository.list():
            if metadata.profile_id != profile.id or metadata.deleted_by_retention:
                continue
            if metadata.finished_at > cutoff:
                continue

            output_path = Path(metadata.output_file)
            try:
                if not output_path.exists() or not output_path.is_file():
                    continue

                output_path.unlink()
                metadata.deleted_by_retention = True
                metadata.deleted_at = datetime.now(timezone.utc)
                metadata_repository.update(metadata)
                deleted_entries.append(metadata)
            except Exception as exc:
                if is_network_transient_error(exc, output_path, destination_type=profile.destination_type):
                    warnings.append(f"{output_path}: {type(exc).__name__}: {exc}")
                    continue
                raise

        return RetentionOutcome(deleted_entries=deleted_entries, warnings=warnings)
