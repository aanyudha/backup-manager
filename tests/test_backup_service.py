"""Tests for backup post-processing and metadata persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.backup_metadata import BackupMetadata
from app.models.profile import MySQLBackupProfile
from app.models.result import BackupResult
from app.repositories.backup_metadata_repository import BackupMetadataRepository
from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.services.retention_service import RetentionOutcome
from app.services.verification_service import VerificationOutcome


class StubMySQLEngine:
    """Return a prebuilt backup result."""

    def __init__(self, result: BackupResult) -> None:
        self.result = result

    def run(self, profile: MySQLBackupProfile, progress=None) -> BackupResult:  # type: ignore[no-untyped-def]
        if progress:
            progress("engine finished")
        return self.result


class StubVerificationService:
    """Return a prebuilt verification outcome or raise a configured error."""

    def __init__(
        self,
        *,
        outcome: VerificationOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome or VerificationOutcome()
        self.error = error

    def build_metadata_outcome(self, result: BackupResult, *, destination_type: str = "local") -> VerificationOutcome:
        if self.error is not None:
            raise self.error
        return self.outcome


class StubRetentionService:
    """Return a prebuilt retention outcome or raise a configured error."""

    def __init__(
        self,
        *,
        outcome: RetentionOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome or RetentionOutcome(deleted_entries=[], warnings=[])
        self.error = error

    def apply_profile_retention(self, profile, metadata_repository) -> RetentionOutcome:  # type: ignore[no-untyped-def]
        if self.error is not None:
            raise self.error
        return self.outcome


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


def build_result(
    profile: MySQLBackupProfile,
    output_file: str | None,
    *,
    success: bool,
    message: str | None = None,
) -> BackupResult:
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
        message=message or (
            "MySQL backup completed successfully."
            if success
            else "MySQL backup failed: mysqldump exited with an error."
        ),
        log_file=str(Path(profile.destination).parent / "logs" / "backup.log"),
        output_file=output_file,
    )


def build_metadata(profile: MySQLBackupProfile, artifact: Path) -> BackupMetadata:
    """Create stored verification metadata for one artifact."""
    started_at = datetime.now(timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    return BackupMetadata(
        profile_id=profile.id,
        profile_name=profile.name,
        backup_type="mysql",
        output_file=str(artifact),
        sha256="deadbeef",
        file_size_bytes=artifact.stat().st_size,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=2.0,
        success=True,
        message="ok",
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
    assert final_result.message == "MySQL backup completed successfully."
    assert metadata_repository.list() == []


def test_mysql_success_with_network_verification_warning_stays_successful(tmp_path: Path) -> None:
    """Transient UNC verification errors should not flip a successful dump to failed."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    profile.destination_type = "network"
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
        verification_service=StubVerificationService(
            error=OSError(59, "An unexpected network error occurred")
        ),
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert final_result.success is True
    assert final_result.message.startswith(
        "MySQL backup completed successfully, but post-backup verification failed:"
    )
    assert "Verification warning: OSError" in log_text
    assert metadata_repository.list() == []


def test_mysql_engine_failure_remains_failed_when_post_processing_is_skipped(tmp_path: Path) -> None:
    """Real MySQL dump failures must remain failed even if helpers are injected."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    repository.create(profile)
    result = build_result(
        profile,
        None,
        success=False,
        message="MySQL backup failed: mysqldump exited with an error.",
    )
    Path(result.log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(result.log_file).write_text("", encoding="utf-8")

    service = BackupService(
        repository,
        PlatformService(),
        log_service,
        metadata_repository=metadata_repository,
        verification_service=StubVerificationService(
            error=OSError(59, "should never be touched")
        ),
        retention_service=StubRetentionService(
            error=RuntimeError("should never be touched")
        ),
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)

    assert final_result.success is False
    assert final_result.message == "MySQL backup failed: mysqldump exited with an error."
    assert metadata_repository.list() == []


def test_metadata_repository_failure_does_not_hide_successful_mysql_backup(tmp_path: Path) -> None:
    """Metadata persistence failures should stay non-fatal after a successful dump."""
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
        verification_service=StubVerificationService(
            outcome=VerificationOutcome(metadata=build_metadata(profile, artifact))
        ),
        mysql_engine=StubMySQLEngine(result),
    )
    service.metadata_repository.add = lambda metadata: (_ for _ in ()).throw(RuntimeError("config write failed"))  # type: ignore[method-assign]

    final_result = service.run_profile(profile.id)
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert final_result.success is True
    assert "metadata step: RuntimeError: config write failed" in final_result.message
    assert "Metadata warning: RuntimeError: config write failed" in log_text


def test_retention_warning_on_network_destination_stays_successful(tmp_path: Path) -> None:
    """Retention warnings on network destinations should not fail the backup."""
    repository = ProfileRepository(tmp_path / "config")
    metadata_repository = BackupMetadataRepository(tmp_path / "config")
    log_service = LogService(tmp_path / "logs")
    profile = build_profile(tmp_path)
    profile.destination_type = "network"
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
        verification_service=StubVerificationService(),
        retention_service=StubRetentionService(
            outcome=RetentionOutcome(
                deleted_entries=[],
                warnings=[rf"{artifact}: OSError: [WinError 59] An unexpected network error occurred"],
            )
        ),
        mysql_engine=StubMySQLEngine(result),
    )

    final_result = service.run_profile(profile.id)
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert final_result.success is True
    assert "retention step:" in final_result.message
    assert "Retention warning:" in log_text
