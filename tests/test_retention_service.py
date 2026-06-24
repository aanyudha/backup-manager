"""Tests for retention-based backup pruning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.backup_metadata import BackupMetadata
from app.models.profile import MySQLBackupProfile
from app.repositories.backup_metadata_repository import BackupMetadataRepository
from app.services.retention_service import RetentionService


def build_profile(tmp_path: Path, *, enabled: bool, days: int | None) -> MySQLBackupProfile:
    """Create a MySQL profile with configurable retention settings."""
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    return MySQLBackupProfile(
        name="Primary DB",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="",
        database_mode="single",
        databases=["appdb"],
        mysqldump_path=str(fake_dump),
        destination=str(tmp_path / "backups"),
        retention_enabled=enabled,
        retention_days=days,
    )


def build_metadata(path: Path, *, profile_id: str, age_days: int) -> BackupMetadata:
    """Create a metadata entry aged by the requested number of days."""
    finished_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    return BackupMetadata(
        profile_id=profile_id,
        profile_name="Primary DB",
        backup_type="mysql",
        output_file=str(path),
        sha256="deadbeef",
        file_size_bytes=path.stat().st_size,
        started_at=finished_at - timedelta(seconds=1),
        finished_at=finished_at,
        duration_seconds=1.0,
        success=True,
        message="ok",
    )


def test_retention_disabled_deletes_nothing(tmp_path: Path) -> None:
    """Disabled retention should not delete metadata-tracked files."""
    profile = build_profile(tmp_path, enabled=False, days=None)
    artifact = tmp_path / "backup.sql.gz"
    artifact.write_bytes(b"backup")
    repository = BackupMetadataRepository(tmp_path / "config")
    repository.add(build_metadata(artifact, profile_id=profile.id, age_days=30))

    outcome = RetentionService().apply_profile_retention(profile, repository)

    assert outcome.deleted_entries == []
    assert outcome.warnings == []
    assert artifact.exists()


def test_retention_enabled_deletes_old_file_and_marks_metadata(tmp_path: Path) -> None:
    """Expired files should be removed and flagged in metadata."""
    profile = build_profile(tmp_path, enabled=True, days=7)
    artifact = tmp_path / "backup.sql.gz"
    artifact.write_bytes(b"backup")
    repository = BackupMetadataRepository(tmp_path / "config")
    repository.add(build_metadata(artifact, profile_id=profile.id, age_days=30))

    outcome = RetentionService().apply_profile_retention(profile, repository)
    stored = repository.list()

    assert len(outcome.deleted_entries) == 1
    assert outcome.warnings == []
    assert artifact.exists() is False
    assert stored[0].deleted_by_retention is True
    assert stored[0].deleted_at is not None


def test_retention_does_not_delete_unknown_files(tmp_path: Path) -> None:
    """Files outside metadata should never be touched by retention."""
    profile = build_profile(tmp_path, enabled=True, days=7)
    unknown = tmp_path / "unknown.sql.gz"
    unknown.write_bytes(b"backup")
    repository = BackupMetadataRepository(tmp_path / "config")

    outcome = RetentionService().apply_profile_retention(profile, repository)

    assert outcome.deleted_entries == []
    assert outcome.warnings == []
    assert unknown.exists()


def test_retention_days_zero_deletes_nothing(tmp_path: Path) -> None:
    """Non-positive retention windows should be treated as a no-op."""
    payload = build_profile(tmp_path, enabled=False, days=None).model_dump()
    payload["retention_enabled"] = True
    payload["retention_days"] = 0
    profile = MySQLBackupProfile.model_construct(**payload)
    artifact = tmp_path / "backup.sql.gz"
    artifact.write_bytes(b"backup")
    repository = BackupMetadataRepository(tmp_path / "config")
    repository.add(build_metadata(artifact, profile_id=profile.id, age_days=30))

    outcome = RetentionService().apply_profile_retention(profile, repository)

    assert outcome.deleted_entries == []
    assert outcome.warnings == []
    assert artifact.exists()


def test_retention_network_transient_delete_error_returns_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Transient UNC delete failures should become warnings instead of hard failures."""
    profile = build_profile(tmp_path, enabled=True, days=7)
    profile.destination_type = "network"
    artifact = tmp_path / "backup.sql.gz"
    artifact.write_bytes(b"backup")
    repository = BackupMetadataRepository(tmp_path / "config")
    repository.add(build_metadata(artifact, profile_id=profile.id, age_days=30))
    original_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == artifact:
            raise OSError(59, "An unexpected network error occurred")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    outcome = RetentionService().apply_profile_retention(profile, repository)

    assert outcome.deleted_entries == []
    assert len(outcome.warnings) == 1
    assert "An unexpected network error occurred" in outcome.warnings[0]
    assert artifact.exists()
