"""Tests for the folder restore engine."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.engines.folder_restore_engine import FolderRestoreEngine
from app.services.log_service import LogService


def test_folder_restore_copies_files_and_preserves_timestamps(tmp_path: Path) -> None:
    """Folder restore should recursively copy files with metadata."""
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    source_file = nested / "notes.txt"
    source_file.write_text("hello restore", encoding="utf-8")
    os.utime(source_file, (1_700_000_000, 1_700_000_000))
    destination = tmp_path / "destination"

    engine = FolderRestoreEngine(LogService(tmp_path / "logs"))
    result = engine.run(source=str(source), destination=str(destination))

    copied_file = destination / "nested" / "notes.txt"
    assert result.success is True
    assert copied_file.read_text(encoding="utf-8") == "hello restore"
    assert int(copied_file.stat().st_mtime) == 1_700_000_000


def test_folder_restore_overwrites_existing_files(tmp_path: Path) -> None:
    """Folder restore should overwrite existing destination files in MVP mode."""
    source = tmp_path / "backup"
    source.mkdir()
    (source / "config.ini").write_text("fresh-value=true\n", encoding="utf-8")

    destination = tmp_path / "live"
    destination.mkdir()
    existing = destination / "config.ini"
    existing.write_text("fresh-value=false\n", encoding="utf-8")

    engine = FolderRestoreEngine(LogService(tmp_path / "logs"))
    result = engine.run(source=str(source), destination=str(destination))

    assert result.success is True
    assert existing.read_text(encoding="utf-8") == "fresh-value=true\n"


def test_folder_restore_validation_fails_when_source_is_missing(tmp_path: Path) -> None:
    """Folder restore validation should fail when the backup source does not exist."""
    engine = FolderRestoreEngine(LogService(tmp_path / "logs"))

    with pytest.raises(FileNotFoundError, match="Backup source folder not found:"):
        engine.validate_paths(str(tmp_path / "missing"), str(tmp_path / "destination"))


def test_folder_restore_validation_creates_destination_when_missing(tmp_path: Path) -> None:
    """Folder restore validation should create the destination directory when needed."""
    source = tmp_path / "backup"
    source.mkdir()
    destination = tmp_path / "new-destination"
    engine = FolderRestoreEngine(LogService(tmp_path / "logs"))

    source_path, destination_path = engine.validate_paths(str(source), str(destination))

    assert source_path == source
    assert destination_path == destination
    assert destination.exists()
    assert destination.is_dir()


def test_folder_restore_validation_reports_writable_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Folder restore validation should surface destination write failures clearly."""
    source = tmp_path / "backup"
    source.mkdir()
    destination = tmp_path / "locked"
    engine = FolderRestoreEngine(LogService(tmp_path / "logs"))
    original_open = Path.open

    def fake_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.name == ".restore_write_test":
            raise OSError("permission denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    with pytest.raises(PermissionError, match="Restore destination is not writable:"):
        engine.validate_paths(str(source), str(destination))
