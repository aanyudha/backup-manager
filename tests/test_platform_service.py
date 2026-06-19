"""Tests for platform helpers and transport guardrails."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.robocopy_transport import RobocopyTransport


def test_platform_service_command_exists() -> None:
    """command_exists should detect a known executable."""
    service = PlatformService()

    assert service.command_exists(Path(sys.executable).name)


def test_robocopy_unavailable_on_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """robocopy should not be allowed on Linux."""
    service = PlatformService()
    monkeypatch.setattr(service, "is_windows", lambda: False)
    transport = RobocopyTransport(LogService(tmp_path), service)
    profile = FolderBackupProfile(
        name="Linux Folder",
        source=str(tmp_path / "source"),
        destination=str(tmp_path / "destination"),
        engine="robocopy",
        mode="copy_new_changed",
    )

    with pytest.raises(RuntimeError, match="Windows"):
        transport.build_command(profile)

