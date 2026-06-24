"""Tests for the FTP folder transport."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

from app.engines.folder_backup_engine import FolderBackupEngine
from app.models.profile import FolderBackupProfile, parse_profile
from app.models.result import BackupResult
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.services.staging_service import RobocopyResult
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
    expected_destination = Path(profile.destination)

    assert f"Destination Root:\n{expected_destination}" in log_text
    assert "Remote File:\n/exports/folder/file.txt" in log_text
    assert f"Local File:\n{expected_local}" in log_text
    assert "Operation:\n" not in log_text


def test_ftp_transport_skips_mkdir_destination_root_when_destination_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)
    destination = Path(profile.destination)
    destination.mkdir(parents=True, exist_ok=True)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []

    class DummyFtp:
        def quit(self) -> None:
            return None

    def guarded_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        if self == destination:
            raise AssertionError("destination root mkdir should be skipped")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: 0,
    )
    monkeypatch.setattr("app.transports.ftp_transport.Path.mkdir", guarded_mkdir)

    result = transport.run(profile)

    assert result.success is True
    assert destination not in mkdir_targets


def test_ftp_transport_creates_destination_root_only_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)
    destination = Path(profile.destination)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []

    class DummyFtp:
        def quit(self) -> None:
            return None

    def tracking_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: 0,
    )
    monkeypatch.setattr("app.transports.ftp_transport.Path.mkdir", tracking_mkdir)

    result = transport.run(profile)

    assert result.success is True
    assert destination.exists()
    assert destination in mkdir_targets


def test_ftp_transport_creates_file_parent_only_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(tmp_path)
    destination = Path(profile.destination)
    destination.mkdir(parents=True, exist_ok=True)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []

    class DummyFtp:
        def retrbinary(self, command: str, callback) -> None:
            callback(b"payload")

        def quit(self) -> None:
            return None

    def tracking_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_iter_remote_entries",
        lambda ftp, remote_root: [(PurePosixPath("/exports/folder/file.txt"), {"type": "file"})],
    )
    monkeypatch.setattr(transport, "_remote_size", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr(transport, "_remote_timestamp", lambda ftp, remote_path, facts: None)
    monkeypatch.setattr("app.transports.ftp_transport.Path.mkdir", tracking_mkdir)

    result = transport.run(profile)

    expected_parent = destination / "folder"
    assert result.success is True
    assert expected_parent.exists()
    assert mkdir_targets.count(expected_parent) == 1


def test_existing_unc_destination_does_not_trigger_mkdir_destination_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = r"\\192.168.23.6\Backup\1.55\folder"
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(
        tmp_path,
        destination=destination,
        destination_type="network",
    )
    original_exists = Path.exists
    original_is_dir = Path.is_dir
    original_mkdir = Path.mkdir

    class DummyFtp:
        def quit(self) -> None:
            return None

    def fake_exists(self) -> bool:  # type: ignore[no-untyped-def]
        if str(self) == destination:
            return True
        return original_exists(self)

    def fake_is_dir(self) -> bool:  # type: ignore[no-untyped-def]
        if str(self) == destination:
            return True
        return original_is_dir(self)

    def fail_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(self) == destination:
            raise AssertionError("UNC destination root mkdir should be skipped")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        transport.staging_service,
        "create_staging_folder",
        lambda profile_name_or_id: (tmp_path / "temp" / "stage-a").mkdir(parents=True, exist_ok=True) or (tmp_path / "temp" / "stage-a"),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "copy_staging_to_destination_with_robocopy",
        lambda staging, current_destination: RobocopyResult(["robocopy"], 1, "copied"),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "cleanup_staging_folder",
        lambda path: None,
    )
    monkeypatch.setattr("app.transports.ftp_transport.Path.exists", fake_exists)
    monkeypatch.setattr("app.transports.ftp_transport.Path.is_dir", fake_is_dir)
    monkeypatch.setattr("app.transports.ftp_transport.Path.mkdir", fail_mkdir)

    result = transport.run(profile)

    assert result.success is True


def test_ftp_transport_avoids_winerror_59_when_unc_destination_root_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = r"\\192.168.23.6\Backup\1.55\folder"
    transport = FtpTransport(LogService(tmp_path / "logs"))
    profile = build_ftp_profile(
        tmp_path,
        destination=destination,
        destination_type="network",
    )
    original_exists = Path.exists
    original_is_dir = Path.is_dir
    original_mkdir = Path.mkdir

    class DummyFtp:
        def quit(self) -> None:
            return None

    def fake_exists(self) -> bool:  # type: ignore[no-untyped-def]
        if str(self) == destination:
            return True
        return original_exists(self)

    def fake_is_dir(self) -> bool:  # type: ignore[no-untyped-def]
        if str(self) == destination:
            return True
        return original_is_dir(self)

    def winerror_59(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(self) == destination:
            raise OSError(59, "An unexpected network error occurred")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        transport.staging_service,
        "create_staging_folder",
        lambda profile_name_or_id: (tmp_path / "temp" / "stage-b").mkdir(parents=True, exist_ok=True) or (tmp_path / "temp" / "stage-b"),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "copy_staging_to_destination_with_robocopy",
        lambda staging, current_destination: RobocopyResult(["robocopy"], 1, "copied"),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "cleanup_staging_folder",
        lambda path: None,
    )
    monkeypatch.setattr("app.transports.ftp_transport.Path.exists", fake_exists)
    monkeypatch.setattr("app.transports.ftp_transport.Path.is_dir", fake_is_dir)
    monkeypatch.setattr("app.transports.ftp_transport.Path.mkdir", winerror_59)

    result = transport.run(profile)

    assert result.success is True


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


def test_ftp_transport_uses_local_staging_for_windows_unc_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    transport = FtpTransport(LogService(tmp_path / "logs"), platform_service=platform_service)
    profile = build_ftp_profile(
        tmp_path,
        source_type="ftp",
        destination=r"\\192.168.23.6\Backup\1.55\folder",
        destination_type="network",
    )
    staging_path = tmp_path / "temp" / "heisenberg_staging" / "folder-1" / "run"
    staged_roots: list[Path] = []
    cleanup_calls: list[Path] = []
    copy_calls: list[tuple[Path, Path]] = []
    progress_messages: list[str] = []

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: (staged_roots.append(local) or 1),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "create_staging_folder",
        lambda profile_name_or_id: (staging_path.mkdir(parents=True, exist_ok=True) or staging_path),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "copy_staging_to_destination_with_robocopy",
        lambda staging, destination: (
            copy_calls.append((Path(staging), Path(destination)))
            or RobocopyResult(["robocopy", str(staging), str(destination)], 1, "copied")
        ),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "cleanup_staging_folder",
        lambda path: cleanup_calls.append(Path(path)),
    )

    result = transport.run(profile, progress_messages.append)

    assert result.success is True
    assert result.output_file == profile.destination
    assert staged_roots == [staging_path]
    assert copy_calls == [(staging_path, Path(profile.destination))]
    assert cleanup_calls == [staging_path]
    assert "Using local staging for network destination reliability." in progress_messages
    log_text = Path(result.log_file or "").read_text(encoding="utf-8")
    assert "Strategy:\nlocal staging + robocopy" in log_text
    assert f"Staging Folder:\n{staging_path}" in log_text
    assert "Robocopy Exit Code:\n1" in log_text


def test_ftp_transport_keeps_staging_folder_when_robocopy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    transport = FtpTransport(LogService(tmp_path / "logs"), platform_service=platform_service)
    profile = build_ftp_profile(
        tmp_path,
        source_type="ftp",
        destination=r"\\192.168.23.6\Backup\1.55\folder",
        destination_type="network",
    )
    staging_path = tmp_path / "temp" / "heisenberg_staging" / "folder-1" / "run"
    cleanup_calls: list[Path] = []

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(transport, "_download_tree", lambda ftp, remote, local, logger, *args, **kwargs: 1)
    monkeypatch.setattr(
        transport.staging_service,
        "create_staging_folder",
        lambda profile_name_or_id: (staging_path.mkdir(parents=True, exist_ok=True) or staging_path),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "copy_staging_to_destination_with_robocopy",
        lambda staging, destination: RobocopyResult(["robocopy"], 8, "failed"),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "cleanup_staging_folder",
        lambda path: cleanup_calls.append(Path(path)),
    )

    with pytest.raises(RuntimeError, match="Staging Folder Kept"):
        transport.run(profile)

    assert staging_path.exists()
    assert cleanup_calls == []


def test_ftp_transport_local_destination_does_not_use_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    transport = FtpTransport(LogService(tmp_path / "logs"), platform_service=platform_service)
    profile = build_ftp_profile(tmp_path, source_type="ftp")
    local_roots: list[Path] = []

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr(transport, "_connect", lambda current: DummyFtp())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda ftp, remote, local, logger, *args, **kwargs: (local_roots.append(local) or 0),
    )
    monkeypatch.setattr(
        transport.staging_service,
        "create_staging_folder",
        lambda profile_name_or_id: (_ for _ in ()).throw(AssertionError("staging should not be used")),
    )

    result = transport.run(profile)

    assert result.success is True
    assert local_roots == [Path(profile.destination)]


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
