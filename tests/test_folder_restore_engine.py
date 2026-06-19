"""Tests for the folder restore engine."""

from __future__ import annotations

import os
from pathlib import Path

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
