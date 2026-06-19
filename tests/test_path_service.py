"""Tests for runtime path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.services.path_service import PathService


def test_path_service_uses_source_root_when_not_frozen(tmp_path: Path) -> None:
    """Source mode should keep config and logs inside the repository root."""
    service = PathService(source_root=tmp_path)

    assert service.is_frozen() is False
    assert service.app_root() == tmp_path
    assert service.config_dir() == tmp_path / "config"
    assert service.logs_dir() == tmp_path / "logs"


def test_path_service_uses_working_directory_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen mode should write config and logs relative to the working directory."""
    executable_dir = tmp_path / "dist" / "HeisenbergBackupManager"
    executable_dir.mkdir(parents=True)
    working_dir = tmp_path / "portable-run"
    working_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    service = PathService(
        source_root=tmp_path / "source",
        working_dir=working_dir,
        executable_path=executable_dir / "HeisenbergBackupManager.exe",
    )

    assert service.is_frozen() is True
    assert service.app_root() == executable_dir
    assert service.config_dir() == working_dir / "config"
    assert service.logs_dir() == working_dir / "logs"
