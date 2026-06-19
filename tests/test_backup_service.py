"""Tests for backup post-processing and metadata persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.profile import MySQLBackupProfile
from app.models.result import BackupResult
from app.repositories.backup_metadata_repository import BackupMetadataRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.platform_service import PlatformService


class StubMySQLEngine:
    """Return a prebuilt backup result."""

    def __init__(self, result: BackupResult) -> None:
        self.result = result

    def run(self, profile: MySQLBackupProfile, progress=None) -> BackupResult:  # type: ignore[no-untyped-def]
        if progress:
            progress("engine finished")
        return self.result


def build_profile(tmp_path: Path) -> MySQLBackupProfile:
    """Create a MySQL profile for backup service tests."""
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
    )


def build_result(profile: MySQLBackupProfile, output_file: str | None, *, success: bool) -> BackupResult:
    """Create a deterministic backup result."""
    started_at = datetime.now(timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    return BackupResult(
        success=success,
        backup_type="mysql",
        profile_id=profile.id,
        profile_name=profile.name,
        started_at=started_at,
        finished_at=finished_at,
        message="ok" if success else "failed",
        log_file=str(Path(profile.destination).parent / "logs" / "backup.log"),
        output_file=output_file,
    )


def test_backup_service_writes_metadata_after_successful_backup(tmp_path: Path) -> None:
    """Successful file backups should persist verification metadata."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    repository.create(profile)
    artifact = tmp_path / "backups" / "backup.sql.gz"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"backup bytes")
    result = build_result(profile, str(artifact), success=True)
    Path(result.log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(result.log_file).write_text("", encoding="utf-8")

    service = BackupService(
        repository,
        PlatformService(),
        log_service,
        metadata_repository=metadata_repository,
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)
    stored = metadata_repository.list()

    assert final_result.success is True
    assert final_result.sha256 is not None
    assert len(stored) == 1
    assert stored[0].output_file == str(artifact)


def test_backup_service_skips_metadata_for_failed_backup(tmp_path: Path) -> None:
    """Failed backups should not write verification metadata."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    repository.create(profile)
    artifact = tmp_path / "backups" / "backup.sql.gz"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"backup bytes")
    result = build_result(profile, str(artifact), success=False)
    Path(result.log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(result.log_file).write_text("", encoding="utf-8")

    service = BackupService(
        repository,
        PlatformService(),
        log_service,
        metadata_repository=metadata_repository,
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)

    assert final_result.success is False
    assert metadata_repository.list() == []


def test_backup_service_missing_output_file_does_not_crash(tmp_path: Path) -> None:
    """Successful results without a real artifact should stay successful."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    repository.create(profile)
    missing_artifact = tmp_path / "backups" / "missing.sql.gz"
    result = build_result(profile, str(missing_artifact), success=True)
    Path(result.log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(result.log_file).write_text("", encoding="utf-8")

    service = BackupService(
        repository,
        PlatformService(),
        log_service,
        metadata_repository=metadata_repository,
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)

    assert final_result.success is True
    assert final_result.message == "ok"
    assert metadata_repository.list() == []
