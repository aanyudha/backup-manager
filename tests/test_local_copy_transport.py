"""Tests for the local copy transport."""

from __future__ import annotations

import os
from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.transports.local_copy_transport import LocalCopyTransport


def test_local_copy_transport_copies_new_and_changed_files(tmp_path: Path) -> None:
    """New and changed files should be copied into the destination."""
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()

    source_file = source / "example.txt"
    source_file.write_text("new-content", encoding="utf-8")

    destination_file = destination / "example.txt"
    destination_file.write_text("old-content", encoding="utf-8")
    old_mtime = destination_file.stat().st_mtime - 60
    os.utime(destination_file, (old_mtime, old_mtime))

    profile = FolderBackupProfile(
        name="Folder Sync",
        source=str(source),
        destination=str(destination),
        engine="local_copy",
        mode="copy_new_changed",
    )

    result = LocalCopyTransport(LogService(tmp_path)).run(profile)

    assert result.success is True
    assert destination_file.read_text(encoding="utf-8") == "new-content"
