"""Tests for folder auto-engine resolution and transport routing."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

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


def test_auto_resolves_ftp_when_source_type_is_ftp(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        source_type="ftp",
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/exports",
    )

    assert engine.resolve_engine(profile) == "ftp"


def test_auto_resolves_sftp_when_source_type_is_sftp(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        source_type="sftp",
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


def test_auto_resolves_rsync_when_source_type_is_rsync(tmp_path: Path) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source_type="rsync",
        source="backup@example.com:/srv/data",
    )

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

    assert engine.resolve_engine(
        build_profile(
            tmp_path,
            engine="ftp",
            source="",
            ftp_host="ftp.example.com",
            ftp_username="backup",
            ftp_password="secret",
            ftp_remote_path="/exports",
        )
    ) == "ftp"
    assert engine.resolve_engine(
        build_profile(
            tmp_path,
            engine="sftp",
            source="",
            sftp_host="sftp.example.com",
            sftp_username="backup",
            sftp_password="secret",
            sftp_remote_path="/exports",
        )
    ) == "sftp"


def test_ftp_source_requires_auto_or_ftp_engine(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FTP source requires Engine auto or ftp."):
        build_profile(
            tmp_path,
            source="",
            source_type="ftp",
            engine="local_copy",
            ftp_host="ftp.example.com",
            ftp_username="backup",
            ftp_remote_path="/exports",
        )


def test_local_source_rejects_ftp_engine(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FTP/SFTP engine requires remote source type."):
        build_profile(tmp_path, engine="ftp")


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


def test_ftp_run_uses_ftp_remote_path_not_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, _ = build_engine(tmp_path)
    destination = tmp_path / "network-destination"
    profile = build_profile(
        tmp_path,
        source="C:/should-not-be-used",
        source_type="ftp",
        destination_type="network",
        destination=str(destination),
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/exports",
    )
    captured: dict[str, object] = {}

    class DummyFtp:
        def quit(self) -> None:
            return None

    monkeypatch.setattr("app.transports.ftp_transport.FtpTransport._connect", lambda self, current: DummyFtp())

    def fake_download(  # type: ignore[no-untyped-def]
        self,
        ftp,
        remote_root,
        local_root,
        logger,
    ):
        captured["remote_root"] = remote_root
        captured["local_root"] = local_root
        return 0

    monkeypatch.setattr("app.transports.ftp_transport.FtpTransport._download_tree", fake_download)

    result = engine.run(profile)

    assert result.success is True
    assert captured["remote_root"] == PurePosixPath("/exports")
    assert captured["local_root"] == destination


def test_ftp_destination_validation_happens_before_transport_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(
        tmp_path,
        source="",
        source_type="ftp",
        destination_type="network",
        destination=r"\\server\share\backup",
        ftp_host="ftp.example.com",
        ftp_username="backup",
        ftp_password="secret",
        ftp_remote_path="/exports",
    )
    call_order: list[str] = []

    monkeypatch.setattr(
        engine.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (call_order.append("validate") or False, "destination blocked"),
    )
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.FtpTransport.run",
        lambda self, current_profile, progress=None: (call_order.append("transport") or build_result(current_profile)),
    )

    with pytest.raises(RuntimeError, match="destination blocked"):
        engine.run(profile)

    assert call_order == ["validate"]


def test_auto_logs_requested_and_resolved_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, _ = build_engine(tmp_path)
    profile = build_profile(tmp_path)
    source_dir = Path(profile.source)
    source_dir.mkdir(parents=True, exist_ok=True)
    app_log_messages: list[str] = []

    monkeypatch.setattr(engine.log_service, "log_app", lambda message: app_log_messages.append(message))
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.LocalCopyTransport.run",
        lambda self, current_profile, progress=None: build_result(current_profile, "Copied 0 file(s)"),
    )

    engine.run(profile)

    assert "Requested engine: auto" in app_log_messages
    assert any(message.startswith("Resolved engine: ") for message in app_log_messages)


def test_folder_backup_logs_destination_validation_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, platform_service = build_engine(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    profile = build_profile(
        tmp_path,
        source=str(source_dir),
        destination=r"\\server\share\backup",
        destination_type="network",
        destination_network_username="backup-user",
        destination_network_password="secret",
        destination_network_domain="WORKGROUP",
    )
    app_log_messages: list[str] = []

    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: False)
    monkeypatch.setattr(engine.log_service, "log_app", lambda message: app_log_messages.append(message))
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.connect_share_diagnostic",
        lambda *args, **kwargs: SimpleNamespace(
            success=True,
            message="connected",
            share_root=r"\\server\share",
            returncode=0,
        ),
    )
    monkeypatch.setattr(
        engine.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (False, "Destination validation failed: blocked"),
    )

    with pytest.raises(RuntimeError, match="Destination validation failed: blocked"):
        engine.run(profile)

    assert any(r"destination=\\server\share\backup" in message for message in app_log_messages)
    assert any(r"share_root=\\server\share" in message for message in app_log_messages)
    assert any("network_credentials_provided=true" in message for message in app_log_messages)
    assert any("net_use_attempted=true" in message for message in app_log_messages)
    assert any("net_use_exit_code=0" in message for message in app_log_messages)
    assert not any("secret" in message for message in app_log_messages)


def test_unc_destination_connects_before_validation_and_disconnects_after_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, platform_service = build_engine(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    profile = build_profile(
        tmp_path,
        source=str(source_dir),
        destination=r"\\server\share\backup",
        destination_type="network",
        destination_network_username="backup-user",
        destination_network_password="secret",
        destination_network_domain="WORKGROUP",
        destination_network_remember_session=False,
    )
    call_order: list[str] = []

    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: False)
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.connect_share_diagnostic",
        lambda *args, **kwargs: (
            call_order.append("connect")
            or SimpleNamespace(
                success=True,
                message="connected",
                share_root=r"\\server\share",
                returncode=0,
            )
        ),
    )
    monkeypatch.setattr(
        engine.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (call_order.append("validate") or True, "ok"),
    )
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.disconnect_share_diagnostic",
        lambda *args, **kwargs: (
            call_order.append("disconnect")
            or SimpleNamespace(
                success=True,
                message="disconnected",
                share_root=r"\\server\share",
                returncode=0,
            )
        ),
    )
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.LocalCopyTransport.run",
        lambda self, current_profile, progress=None: (call_order.append("transport") or build_result(current_profile, "Copied 1 file(s)")),
    )

    result = engine.run(profile)

    assert result.success is True
    assert call_order == ["connect", "validate", "transport", "disconnect"]


def test_local_destination_does_not_call_net_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, platform_service = build_engine(tmp_path)
    source_dir = tmp_path / "source"
    destination_dir = tmp_path / "destination"
    source_dir.mkdir(parents=True, exist_ok=True)
    destination_dir.mkdir(parents=True, exist_ok=True)
    profile = build_profile(
        tmp_path,
        source=str(source_dir),
        destination=str(destination_dir),
        destination_network_username="backup-user",
        destination_network_password="secret",
    )

    monkeypatch.setattr(platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.connect_share_diagnostic",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("net use should not run for local paths")),
    )
    monkeypatch.setattr(
        "app.engines.folder_backup_engine.LocalCopyTransport.run",
        lambda self, current_profile, progress=None: build_result(current_profile, "Copied 0 file(s)"),
    )

    result = engine.run(profile)

    assert result.success is True
