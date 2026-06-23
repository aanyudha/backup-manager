"""Tests for folder auto-engine resolution and transport routing."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.engines.folder_backup_engine import FolderBackupEngine
from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService
from app.services.platform_service import PlatformService


def build_engine(tmp_path: Path) -> tuple[FolderBackupEngine, PlatformService]:
    """Create a folder engine with a patchable platform service."""
    platform_service = PlatformService()
    return FolderBackupEngine(platform_service, LogService(tmp_path / "logs")), platform_service


def build_profile(tmp_path: Path, **overrides) -> FolderBackupProfile:
    """Create a valid folder profile for engine tests."""
    payload = {
        "id": "folder-1",
        "name": "Documents",
        "source": str(tmp_path / "source"),
        "destination": str(tmp_path / "destination"),
        "engine": "auto",
        "mode": "copy_new_changed",
    }
    payload.update(overrides)
    return FolderBackupProfile(**payload)


def build_result(profile: FolderBackupProfile, message: str) -> BackupResult:
    """Create a stable backup result for routing assertions."""
    now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
    return BackupResult(
        success=True,
        backup_type="folder",
        profile_id=profile.id,
        profile_name=profile.name,
        started_at=now,
        finished_at=now,
        message=message,
        log_file=None,
        output_file=profile.destination,
    )


def test_auto_resolves_ftp_when_ftp_fields_exist(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/exports",
    )

    assert engine.resolve_engine(profile) == "ftp"


def test_auto_resolves_sftp_when_sftp_fields_exist(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        sftp_host="sftp.example.com",
        sftp_username="backup",
        sftp_password="secret",
        sftp_remote_path="/exports",
    )

    assert engine.resolve_engine(profile) == "sftp"


def test_auto_prefers_sftp_when_both_remote_configs_exist(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        sftp_host="sftp.example.com",
        sftp_username="backup",
        sftp_password="secret",
        sftp_remote_path="/sftp",
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/ftp",
    )

    assert engine.resolve_engine(profile) == "sftp"


def test_auto_resolves_rsync_when_source_looks_remote(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(tmp_path, source="backup@example.com:/srv/data")

    assert engine.resolve_engine(profile) == "rsync"


def test_auto_resolves_robocopy_on_windows_when_available(tmp_path: Path, monkeypatch) -> None:
    engine, platform_service = build_engine(tmp_path)
    profile = build_profile(tmp_path)
    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: command == "robocopy")

    assert engine.resolve_engine(profile) == "robocopy"


def test_auto_falls_back_to_local_copy(tmp_path: Path, monkeypatch) -> None:
    engine, platform_service = build_engine(tmp_path)
    profile = build_profile(tmp_path)
    monkeypatch.setattr(platform_service, "is_windows", lambda: False)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: False)

    assert engine.resolve_engine(profile) == "local_copy"


def test_explicit_engine_values_are_preserved(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)

    assert engine.resolve_engine(build_profile(tmp_path, engine="ftp", source="", ftp_host="ftp.example.com", ftp_username="backup", ftp_password="secret", ftp_remote_path="/exports")) == "ftp"
    assert engine.resolve_engine(build_profile(tmp_path, engine="sftp", source="", sftp_host="sftp.example.com", sftp_username="backup", sftp_password="secret", sftp_remote_path="/exports")) == "sftp"


def test_auto_with_ftp_fields_does_not_route_to_local_copy(tmp_path: Path, monkeypatch) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/exports",
    )
    expected = build_result(profile, "Downloaded 1 file(s) from FTP.")

    monkeypatch.setattr(
        "app.engines.folder_backup_engine.FtpTransport.run",
        lambda self, current_profile, progress=None: expected,
    )
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.LocalCopyTransport.run",
        lambda self, current_profile, progress=None: (_ for _ in ()).throw(
            AssertionError("local_copy should not run when FTP fields exist")
        ),
    )

    result = engine.run(profile)

    assert result == expected
