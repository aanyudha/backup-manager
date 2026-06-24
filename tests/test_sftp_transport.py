"""Tests for the SFTP folder transport."""

from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.services.staging_service import RobocopyResult
from app.transports.sftp_transport import SftpTransport


def build_sftp_profile(tmp_path: Path, **overrides) -> FolderBackupProfile:
    """Create a valid SFTP-backed folder profile."""
    payload = {
        "name": "Remote SFTP",
        "source": "",
        "destination": str(tmp_path / "downloads"),
        "engine": "sftp",
        "mode": "copy_new_changed",
        "sftp_host": "sftp.example.com",
        "sftp_port": 22,
        "sftp_username": "backup",
        "sftp_password": "secret",
        "sftp_remote_path": "/exports",
    }
    payload.update(overrides)
    return FolderBackupProfile(**payload)


class DummyTransportHandle:
    """Small transport stub for cleanup checks."""

    def close(self) -> None:
        return None


class DummyChannel:
    """Small channel stub that exposes a transport."""

    def get_transport(self) -> DummyTransportHandle:
        return DummyTransportHandle()


class DummySftpClient:
    """Tiny SFTP client stub for transport tests."""

    def __init__(self, entries: dict[str, list[SimpleNamespace]] | None = None) -> None:
        self.entries = entries or {}
        self.get_calls: list[tuple[str, str]] = []

    def listdir_attr(self, remote_root: str) -> list[SimpleNamespace]:
        return list(self.entries.get(remote_root, []))

    def get(self, remote_path: str, local_path: str) -> None:
        self.get_calls.append((remote_path, local_path))
        Path(local_path).write_text("payload", encoding="utf-8")

    def get_channel(self) -> DummyChannel:
        return DummyChannel()

    def close(self) -> None:
        return None


def test_sftp_transport_skips_mkdir_destination_root_when_destination_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = SftpTransport(LogService(tmp_path / "logs"))
    profile = build_sftp_profile(tmp_path)
    destination = Path(profile.destination)
    destination.mkdir(parents=True, exist_ok=True)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []

    def guarded_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        if self == destination:
            raise AssertionError("destination root mkdir should be skipped")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummySftpClient())
    monkeypatch.setattr("app.transports.sftp_transport.Path.mkdir", guarded_mkdir)

    result = transport.run(profile)

    assert result.success is True
    assert destination not in mkdir_targets


def test_sftp_transport_creates_destination_root_only_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = SftpTransport(LogService(tmp_path / "logs"))
    profile = build_sftp_profile(tmp_path)
    destination = Path(profile.destination)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []

    def tracking_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummySftpClient())
    monkeypatch.setattr("app.transports.sftp_transport.Path.mkdir", tracking_mkdir)

    result = transport.run(profile)

    assert result.success is True
    assert destination.exists()
    assert destination in mkdir_targets


def test_sftp_transport_creates_file_parent_only_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = SftpTransport(LogService(tmp_path / "logs"))
    profile = build_sftp_profile(tmp_path)
    destination = Path(profile.destination)
    destination.mkdir(parents=True, exist_ok=True)
    original_mkdir = Path.mkdir
    mkdir_targets: list[Path] = []
    entries = {
        "/exports": [
            SimpleNamespace(
                filename="nested",
                st_mode=stat.S_IFDIR,
                st_mtime=0,
                st_size=0,
            )
        ],
        "/exports/nested": [
            SimpleNamespace(
                filename="file.txt",
                st_mode=stat.S_IFREG,
                st_mtime=1,
                st_size=7,
            )
        ],
    }

    def tracking_mkdir(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        mkdir_targets.append(self)
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(transport, "_connect", lambda current: DummySftpClient(entries))
    monkeypatch.setattr("app.transports.sftp_transport.Path.mkdir", tracking_mkdir)

    result = transport.run(profile)

    expected_parent = destination / "nested"
    assert result.success is True
    assert expected_parent.exists()
    assert mkdir_targets.count(expected_parent) == 1


def test_sftp_transport_uses_local_staging_for_windows_unc_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    transport = SftpTransport(LogService(tmp_path / "logs"), platform_service=platform_service)
    profile = build_sftp_profile(
        tmp_path,
        source_type="sftp",
        destination=r"\\192.168.23.6\Backup\1.55\folder",
        destination_type="network",
    )
    staging_path = tmp_path / "temp" / "heisenberg_staging" / "folder-1" / "run"
    staged_roots: list[Path] = []
    cleanup_calls: list[Path] = []
    copy_calls: list[tuple[Path, Path]] = []
    progress_messages: list[str] = []

    monkeypatch.setattr(transport, "_connect", lambda current: DummySftpClient())
    monkeypatch.setattr(
        transport,
        "_download_tree",
        lambda client, remote, local, logger: (staged_roots.append(local) or 1),
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
            or RobocopyResult(["robocopy", str(staging), str(destination)], 3, "copied")
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
    assert "Robocopy Exit Code:\n3" in log_text
