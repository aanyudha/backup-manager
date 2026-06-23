"""Tests for the FTP folder transport."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.engines.folder_backup_engine import FolderBackupEngine
from app.models.profile import FolderBackupProfile, parse_profile
from app.models.result import BackupResult
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.ftp_transport import FtpTransport


def build_ftp_profile(tmp_path: Path, **overrides) -> FolderBackupProfile:
    """Create a valid FTP-backed folder profile."""
    payload = {
        "name": "Remote FTP",
        "source": "",
        "destination": str(tmp_path / "downloads"),
        "engine": "ftp",
        "mode": "copy_new_changed",
        "ftp_host": "ftp.example.com",
        "ftp_port": 21,
        "ftp_username": "backup",
        "ftp_password": "secret",
        "ftp_remote_path": "/exports",
        "ftp_passive": True,
    }
    payload.update(overrides)
    return FolderBackupProfile(**payload)


def build_result(profile: FolderBackupProfile) -> BackupResult:
    """Create a stable folder backup result."""
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    return BackupResult(
        success=True,
        backup_type="folder",
        profile_id=profile.id,
        profile_name=profile.name,
        started_at=now,
        finished_at=now,
        message="Downloaded 1 file(s) from FTP.",
        log_file=None,
        output_file=profile.destination,
    )


def test_ftp_transport_rejects_missing_host(tmp_path: Path) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path).model_copy(update={"ftp_host": None})

    with pytest.raises(RuntimeError, match="FTP host is required"):
        transport.run(profile)


def test_ftp_transport_rejects_mirror_mode(tmp_path: Path) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path, mode="mirror_with_delete")

    result = transport.run(profile)

    assert result.success is False
    assert "mirror_with_delete is not supported for FTP" in result.message


def test_ftp_password_is_masked_in_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(transport, "_download_tree", lambda ftp, remote, local, logger: 0)

    result = transport.run(profile)
    assert result.log_file is not None
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert "secret" not in log_text
    assert "********" in log_text


def test_folder_backup_engine_routes_ftp_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = build_ftp_profile(tmp_path)
    engine = FolderBackupEngine(PlatformService(), LogService(tmp_path / "logs"))
    expected = build_result(profile)

    monkeypatch.setattr(
        "app.engines.folder_backup_engine.FtpTransport.run",
        lambda self, current_profile, progress=None: expected,
    )

    result = engine.run(profile)

    assert result == expected


def test_folder_profile_serialization_round_trips_ftp_fields(tmp_path: Path) -> None:
    profile = build_ftp_profile(tmp_path)
    serialized = profile.model_dump(mode="json")

    restored = parse_profile(serialized)

    assert isinstance(restored, FolderBackupProfile)
    assert "ftp_tls" not in serialized
    assert restored.engine == "ftp"
    assert restored.ftp_host == "ftp.example.com"
    assert restored.ftp_port == 21
    assert restored.ftp_username == "backup"
    assert restored.ftp_password == "secret"
    assert restored.ftp_remote_path == "/exports"
    assert restored.ftp_passive is True
