"""Tests for FTP and SFTP remote folder browsing helpers."""

from __future__ import annotations

import logging
import stat

import pytest

from app.services.remote_browser_service import RemoteBrowserService


class FakeFtpClient:
    """Small FTP stub for directory-listing tests."""

    def __init__(self) -> None:
        self.connected = False
        self.logged_in = False
        self.passive_mode = True

    def connect(self, host: str, port: int, timeout: int) -> None:
        self.connected = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = True

    def set_pasv(self, passive_mode: bool) -> None:
        self.passive_mode = passive_mode

    def mlsd(self, remote_path: str):
        assert remote_path == "/exports"
        return iter(
            [
                ("daily", {"type": "dir"}),
                ("notes.txt", {"type": "file"}),
                (".", {"type": "cdir"}),
            ]
        )

    def quit(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakeSftpEntry:
    """Small SFTP entry stub."""

    def __init__(self, filename: str, *, is_dir: bool) -> None:
        self.filename = filename
        self.st_mode = stat.S_IFDIR if is_dir else stat.S_IFREG


class FakeSftpClient:
    """Small SFTP client stub."""

    def listdir_attr(self, remote_path: str):
        assert remote_path == "/exports"
        return [
            FakeSftpEntry("incoming", is_dir=True),
            FakeSftpEntry("dump.sql", is_dir=False),
        ]

    def close(self) -> None:
        return None


class FakeTransport:
    """Small Paramiko transport stub."""

    def __init__(self, target) -> None:
        self.target = target
        self.connected_with: dict[str, object] | None = None

    def connect(self, **kwargs) -> None:
        self.connected_with = kwargs

    def close(self) -> None:
        return None


def test_ftp_directory_listing_returns_only_directories(monkeypatch) -> None:
    service = RemoteBrowserService()
    monkeypatch.setattr("app.services.remote_browser_service.ftplib.FTP", FakeFtpClient)

    entries = service.list_ftp_directories(
        host="ftp.example.com",
        port=21,
        username="backup",
        password="secret",
        remote_path="/exports",
        passive_mode=True,
    )

    assert [(entry.name, entry.path) for entry in entries] == [("daily", "/exports/daily")]


def test_sftp_directory_listing_returns_only_directories(monkeypatch) -> None:
    service = RemoteBrowserService()
    fake_transport = FakeTransport(("sftp.example.com", 22))
    monkeypatch.setattr("app.services.remote_browser_service.paramiko.Transport", lambda target: fake_transport)
    monkeypatch.setattr(
        "app.services.remote_browser_service.paramiko.SFTPClient.from_transport",
        lambda transport: FakeSftpClient(),
    )

    entries = service.list_sftp_directories(
        host="sftp.example.com",
        port=22,
        username="backup",
        password="secret",
        remote_path="/exports",
    )

    assert [(entry.name, entry.path) for entry in entries] == [("incoming", "/exports/incoming")]


def test_remote_browser_rejects_missing_ftp_credentials() -> None:
    service = RemoteBrowserService()

    with pytest.raises(RuntimeError, match="Fill FTP connection fields before browsing."):
        service.list_ftp_directories(
            host="",
            port=21,
            username="backup",
            password="secret",
        )


def test_remote_browser_rejects_missing_sftp_credentials() -> None:
    service = RemoteBrowserService()

    with pytest.raises(RuntimeError, match="Fill SFTP connection fields before browsing."):
        service.list_sftp_directories(
            host="sftp.example.com",
            port=22,
            username="backup",
            password="",
            private_key_path=None,
        )


def test_remote_browser_does_not_log_passwords(monkeypatch, caplog) -> None:
    service = RemoteBrowserService()
    monkeypatch.setattr("app.services.remote_browser_service.ftplib.FTP", FakeFtpClient)

    with caplog.at_level(logging.INFO):
        service.list_ftp_directories(
            host="ftp.example.com",
            port=21,
            username="backup",
            password="super-secret",
            remote_path="/exports",
        )

    assert "super-secret" not in caplog.text
