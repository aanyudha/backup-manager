"""Tests for the backup metadata repository."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.models.backup_metadata import BackupMetadata
from app.repositories.backup_metadata_repository import BackupMetadataRepository


def build_metadata(path: Path) -> BackupMetadata:
    """Create a stable metadata entry for repository tests."""
    now = datetime.now(timezone.utc)
    return BackupMetadata(
        profile_id="profile-1",
        profile_name="Primary DB",
        backup_type="mysql",
        output_file=str(path),
        sha256="abc123",
        file_size_bytes=42,
        started_at=now,
        finished_at=now,
        duration_seconds=0.0,
        success=True,
        message="ok",
    )


def test_metadata_repository_creates_file_and_round_trips_entries(tmp_path: Path) -> None:
    """The repository should auto-create and persist metadata entries."""
    repository = BackupMetadataRepository(tmp_path / "config")
    metadata = build_metadata(tmp_path / "backup.sql.gz")

    repository.add(metadata)
    stored = repository.list()

    assert repository.metadata_path.exists()
    assert len(stored) == 1
    assert stored[0].output_file == str(tmp_path / "backup.sql.gz")


def test_metadata_repository_update_marks_entry_as_deleted(tmp_path: Path) -> None:
    """Updates should replace existing metadata entries in place."""
    repository = BackupMetadataRepository(tmp_path / "config")
    metadata = build_metadata(tmp_path / "backup.sql.gz")
    repository.add(metadata)

    metadata.deleted_by_retention = True
    metadata.deleted_at = datetime.now(timezone.utc)
    repository.update(metadata)

    stored = repository.list()
    assert stored[0].deleted_by_retention is True
    assert stored[0].deleted_at is not None
