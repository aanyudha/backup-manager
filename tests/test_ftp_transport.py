"""Tests for the FTP folder transport."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

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
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: 0,
    )

    result = transport.run(profile)
    assert result.log_file is not None
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert "secret" not in log_text
    assert "********" in log_text


def test_ftp_transport_logs_destination_and_first_file_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)

    class DummyFtp:
        def retrbinary(self, command: str, callback) -> None:
            callback(b"payload")

        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_iter_remote_entries",
        lambda ftp, remote_root: [(PurePosixPath("/exports/folder/file.txt"), {"type": "file"})],
    )
    monkeypatch.setattr(transport, "_remote_size", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr(transport, "_remote_timestamp", lambda ftp, remote_path, facts: None)

    result = transport.run(profile)

    assert result.log_file is not None
    with open(result.log_file, encoding="utf-8") as handle:
        log_text = handle.read()

    expected_local = Path(profile.destination) / "folder" / "file.txt"
    expected_parent = expected_local.parent
    expected_destination = Path(profile.destination)

    assert f"Destination Root:\n{expected_destination}" in log_text
    assert "Remote File:\n/exports/folder/file.txt" in log_text
    assert f"Local File:\n{expected_local}" in log_text
    assert f"Operation:\nmkdir destination root\n\nTarget:\n{expected_destination}\n\nResult:\nOK" in log_text
    assert f"Operation:\nmkdir parent\n\nTarget:\n{expected_parent}\n\nResult:\nOK" in log_text
    assert f"Operation:\nopen destination file\n\nTarget:\n{expected_local}\n\nResult:\nOK" in log_text
    assert f"Operation:\nwrite chunk\n\nTarget:\n{expected_local}\n\nResult:\nOK" in log_text
    assert f"Operation:\nflush\n\nTarget:\n{expected_local}\n\nResult:\nOK" in log_text
    assert f"Operation:\nclose\n\nTarget:\n{expected_local}\n\nResult:\nOK" in log_text


def test_ftp_transport_surfaces_local_write_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)
    original_open = Path.open

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_iter_remote_entries",
        lambda ftp, remote_root: [(PurePosixPath("/exports/file.txt"), {"type": "file"})],
    )
    monkeypatch.setattr(transport, "_remote_size", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr(transport, "_remote_timestamp", lambda ftp, remote_path, facts: None)

    def failing_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.name == "file.txt":
            raise PermissionError("simulated local write failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr("app.transports.ftp_transport.Path.open", failing_open)

    with pytest.raises(RuntimeError, match="FTP Write Failure"):
        transport.run(profile)

    log_files = sorted((tmp_path / "logs").glob("Remote_FTP_*.log"))
    assert log_files
    with open(log_files[0], encoding="utf-8") as handle:
        log_text = handle.read()

    expected_local = Path(profile.destination) / "file.txt"
    assert "Remote File:\n/exports/file.txt" in log_text
    assert f"Local File:\n{expected_local}" in log_text
    assert f"Target:\n{expected_local}" in log_text
    assert "Operation:\nopen destination file" in log_text
    assert f"Operation:\nopen destination file\n\nTarget:\n{expected_local}\n\nResult:\nFAILED" in log_text
    assert "Exception:\n<class 'PermissionError'>\nsimulated local write failure" in log_text


def test_ftp_transport_stops_after_first_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)
    retrbinary_commands: list[str] = []
    opened_files: list[str] = []

    class DummyHandle:
        def __init__(self, path: Path) -> None:
            self.path = path

        def write(self, data: bytes) -> int:
            if self.path.name == "first.txt":
                raise OSError("simulated write failure")
            return len(data)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    class DummyFtp:
        def retrbinary(self, command: str, callback) -> None:
            retrbinary_commands.append(command)
            callback(b"payload")

        def quit(self) -> None:
            return None

    def fake_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        opened_files.append(self.name)
        return DummyHandle(self)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_iter_remote_entries",
        lambda ftp, remote_root: [
            (PurePosixPath("/exports/first.txt"), {"type": "file"}),
            (PurePosixPath("/exports/second.txt"), {"type": "file"}),
        ],
    )
    monkeypatch.setattr(transport, "_remote_size", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr(transport, "_remote_timestamp", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr("app.transports.ftp_transport.Path.open", fake_open)

    with pytest.raises(RuntimeError, match="Operation:\nwrite chunk"):
        transport.run(profile)

    assert retrbinary_commands == ["RETR /exports/first.txt"]
    assert opened_files == ["first.txt"]


def test_ftp_transport_logs_first_file_only_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)

    class DummyFtp:
        def retrbinary(self, command: str, callback) -> None:
            callback(b"payload")

        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_iter_remote_entries",
        lambda ftp, remote_root: [
            (PurePosixPath("/exports/first.txt"), {"type": "file"}),
            (PurePosixPath("/exports/second.txt"), {"type": "file"}),
        ],
    )
    monkeypatch.setattr(transport, "_remote_size", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr(transport, "_remote_timestamp", lambda ftp, remote_path, facts: None)

    result = transport.run(profile)

    assert result.log_file is not None
    log_text = Path(result.log_file).read_text(encoding="utf-8")

    assert log_text.count("Remote File:\n") == 1
    assert log_text.count("Local File:\n") == 1
    assert "Remote File:\n/exports/first.txt" in log_text


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
    assert restored.source_type == "ftp"
    assert restored.engine == "ftp"
    assert restored.ftp_host == "ftp.example.com"
    assert restored.ftp_port == 21
    assert restored.ftp_username == "backup"
    assert restored.ftp_password == "secret"
    assert restored.ftp_remote_path == "/exports"
    assert restored.ftp_passive is True
