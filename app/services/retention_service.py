"""Retention helpers for pruning known backup artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.backup_metadata import BackupMetadata
from app.models.profile import Profile
from app.repositories.backup_metadata_repository import BackupMetadataRepository


class RetentionService:
    """Delete expired backup files that were previously recorded in metadata."""

    def apply_profile_retention(
        self,
        profile: Profile,
        metadata_repository: BackupMetadataRepository,
    ) -> list[BackupMetadata]:
        """Delete expired artifacts for one profile and mark their metadata."""
        if not profile.retention_enabled:
            return []
        if profile.retention_days is None or profile.retention_days <= 0:
            return []

        deleted_entries: list[BackupMetadata] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=profile.retention_days)
        for metadata in metadata_repository.list():
            if metadata.profile_id != profile.id or metadata.deleted_by_retention:
                continue
            if metadata.finished_at > cutoff:
                continue

            output_path = Path(metadata.output_file)
            if not output_path.exists() or not output_path.is_file():
                continue

            output_path.unlink()
            metadata.deleted_by_retention = True
            metadata.deleted_at = datetime.now(timezone.utc)
            metadata_repository.update(metadata)
            deleted_entries.append(metadata)

        return deleted_entries
