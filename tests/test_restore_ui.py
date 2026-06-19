"""Tests for restore UI safety messaging."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.restore_result import RestoreResult
from app.ui.main_window import MainWindow
from app.ui.restore_page import RestorePage


def test_mysql_confirmation_text_includes_target_database_and_source_file() -> None:
    """MySQL restore confirmations should name the destructive target and source file."""
    text = MainWindow.build_mysql_restore_confirmation(
        database="appdb",
        sql_file="C:/backups/restore.sql.gz",
    )

    assert "appdb" in text
    assert "C:/backups/restore.sql.gz" in text
    assert "overwrite existing database objects" in text


def test_folder_confirmation_text_includes_destination_path() -> None:
    """Folder restore confirmations should name the destination path and overwrite behavior."""
    text = MainWindow.build_folder_restore_confirmation(destination="C:/restore/live")

    assert "C:/restore/live" in text
    assert "No files will be deleted." in text
    assert "may be overwritten" in text


def test_restore_result_details_include_status_duration_log_and_message() -> None:
    """Restore result formatting should show the key completion details in one place."""
    started_at = datetime.now(timezone.utc)
    finished_at = started_at + timedelta(seconds=2)
    result = RestoreResult(
        success=False,
        restore_type="mysql",
        source="source.sql",
        destination="appdb@127.0.0.1:3306",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=2.0,
        message="MySQL restore failed: Access denied",
        log_file="logs/restore_20260619_120000.log",
    )

    text = RestorePage.format_restore_result(result)

    assert "Status: Failed" in text
    assert "Duration: 2.00s" in text
    assert "Log file: logs/restore_20260619_120000.log" in text
    assert "Message: MySQL restore failed: Access denied" in text
