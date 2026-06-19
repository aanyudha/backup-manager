"""Tests for restore result persistence and service behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.restore_result import RestoreResult
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.restore_service import RestoreService


def make_result(*, success: bool, restore_type: str = "mysql") -> RestoreResult:
    """Create a stable restore result for tests."""
    started_at = datetime.now(timezone.utc)
    finished_at = started_at + timedelta(seconds=3)
    return RestoreResult(
        success=success,
        restore_type=restore_type,
        source="C:/backups/source.sql",
        destination="appdb@127.0.0.1:3306",
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=3.0,
        message="ok" if success else "failed",
        log_file="logs/restore_20260619_100000.log",
    )


def test_restore_service_persists_success_results(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    """Successful restores should be returned and persisted to history."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    expected = make_result(success=True)
    monkeypatch.setattr(service.mysql_engine, "run", lambda **kwargs: expected)

    result = service.restore_mysql(
        sql_file="backup.sql",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="secret",
        database="appdb",
    )

    assert result.success is True
    history = repository.list_restore_history()
    assert len(history) == 1
    assert history[0].success is True


def test_restore_service_persists_failed_results(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    """Failed restore results should also be recorded in history."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    expected = make_result(success=False, restore_type="folder")
    monkeypatch.setattr(service.folder_engine, "run", lambda **kwargs: expected)

    result = service.restore_folder(source="backup", destination="live")

    assert result.success is False
    history = repository.list_restore_history()
    assert len(history) == 1
    assert history[0].success is False
