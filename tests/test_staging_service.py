"""Tests for local staging and robocopy fallback helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.staging_service as staging_module
from app.services.log_service import LogService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.staging_service import StagingService


def build_platform(monkeypatch: pytest.MonkeyPatch, *, is_windows: bool, has_robocopy: bool) -> PlatformService:
    """Create a patchable platform service for staging tests."""
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: is_windows)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: has_robocopy and command == "robocopy")
    return platform_service


def test_staging_service_creates_folder_under_runtime_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path_service = PathService(source_root=tmp_path)
    platform_service = build_platform(monkeypatch, is_windows=True, has_robocopy=True)
    service = StagingService(
        path_service=path_service,
        platform_service=platform_service,
        log_service=LogService(tmp_path / "logs"),
    )

    staging_path = service.create_staging_folder("FTP Profile 1")

    assert staging_path.exists()
    assert staging_path.is_dir()
    assert staging_path.parent.parent == path_service.temp_dir() / "heisenberg_staging"
    assert staging_path.parent.name == "FTP_Profile_1"


def test_staging_service_cleanup_removes_folder(tmp_path: Path) -> None:
    staging_path = tmp_path / "temp" / "heisenberg_staging" / "profile" / "20260624_120000"
    staging_path.mkdir(parents=True)
    (staging_path / "file.txt").write_text("payload", encoding="utf-8")

    StagingService.cleanup_staging_folder(staging_path)

    assert not staging_path.exists()


def test_staging_service_robocopy_exit_code_below_8_is_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_service = PathService(source_root=tmp_path)
    platform_service = build_platform(monkeypatch, is_windows=True, has_robocopy=True)
    service = StagingService(path_service=path_service, platform_service=platform_service)
    staging_path = tmp_path / "temp" / "heisenberg_staging" / "profile" / "run"
    destination = Path(r"\\server\share\backup")
    calls: list[list[str]] = []

    def fake_run(command, capture_output, text, check):  # type: ignore[no-untyped-def]
        calls.append(command)
        return SimpleNamespace(returncode=3, stdout="copied", stderr="")

    monkeypatch.setattr(staging_module.subprocess, "run", fake_run)

    result = service.copy_staging_to_destination_with_robocopy(staging_path, destination)

    assert result.success is True
    assert result.returncode == 3
    assert result.output == "copied"
    assert calls == [[
        "robocopy",
        str(staging_path),
        str(destination),
        "*.*",
        "/E",
        "/DCOPY:DA",
        "/COPY:DAT",
        "/R:3",
        "/W:3",
        "/MT:8",
        "/FFT",
        "/TEE",
    ]]


def test_staging_service_robocopy_exit_code_8_or_higher_is_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_service = PathService(source_root=tmp_path)
    platform_service = build_platform(monkeypatch, is_windows=True, has_robocopy=True)
    service = StagingService(path_service=path_service, platform_service=platform_service)

    monkeypatch.setattr(
        staging_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=8, stdout="", stderr="failed"),
    )

    result = service.copy_staging_to_destination_with_robocopy(tmp_path / "staging", Path(r"\\server\share\backup"))

    assert result.success is False
    assert result.returncode == 8
    assert result.output == "failed"
