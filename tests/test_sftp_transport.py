"""Tests for the SFTP folder transport."""

from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
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
