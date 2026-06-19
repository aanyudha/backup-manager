"""Tests for the MySQL backup engine."""

from __future__ import annotations

from pathlib import Path

from app.engines.mysql_backup_engine import MySQLBackupEngine
from app.models.profile import MySQLBackupProfile
from app.services.log_service import LogService


def test_mysqldump_log_command_masks_password(tmp_path: Path) -> None:
    """Masked command output must not expose passwords."""
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    log_service = LogService(tmp_path)
    engine = MySQLBackupEngine(log_service)
    profile = MySQLBackupProfile(
        name="Database Backup",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="super-secret",
        database_mode="single",
        databases=["appdb"],
        mysqldump_path=str(fake_dump),
        destination=str(tmp_path / "output"),
    )

    masked = engine.build_log_command(profile)

    assert "super-secret" not in masked
    assert "--password=********" in masked

