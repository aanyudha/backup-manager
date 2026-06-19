"""Tests for restore result persistence and service behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.restore_result import RestoreResult
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.restore_service import MySQLRestoreValidation, RestoreService


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


def make_mysql_validation(
    *,
    tmp_path: Path,
    create_database_if_missing: bool = False,
    database_exists: bool = True,
) -> MySQLRestoreValidation:
    """Create a normalized MySQL restore validation payload for tests."""
    source_path = tmp_path / "backup.sql"
    source_path.write_text("SELECT 1;\n", encoding="utf-8")
    return MySQLRestoreValidation(
        sql_file=str(source_path),
        host="127.0.0.1",
        port=3306,
        username="root",
        password="secret",
        database="appdb",
        mysql_path=str(tmp_path / "mysql"),
        create_database_if_missing=create_database_if_missing,
        database_exists=database_exists,
        source_path=source_path,
    )


def test_restore_service_persists_success_results(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    """Successful restores should be returned and persisted to history."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    expected = make_result(success=True)
    validation = make_mysql_validation(tmp_path=tmp_path)
    monkeypatch.setattr(service, "_prepare_mysql_restore", lambda **kwargs: validation)
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
    monkeypatch.setattr(
        service,
        "validate_folder_restore",
        lambda source, destination: ({"source": source, "destination": destination}, "ok"),
    )
    monkeypatch.setattr(service.folder_engine, "run", lambda **kwargs: expected)

    result = service.restore_folder(source="backup", destination="live")

    assert result.success is False
    history = repository.list_restore_history()
    assert len(history) == 1
    assert history[0].success is False


def test_mysql_restore_fails_when_target_database_is_empty(tmp_path: Path) -> None:
    """MySQL restore validation should reject blank target databases."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    sql_file = tmp_path / "backup.sql"
    sql_file.write_text("SELECT 1;\n", encoding="utf-8")
    mysql_binary = tmp_path / "mysql"
    mysql_binary.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Target database is required\\."):
        service.validate_mysql_restore(
            sql_file=str(sql_file),
            host="127.0.0.1",
            port="3306",
            username="root",
            password="secret",
            database="   ",
            mysql_path=str(mysql_binary),
        )


def test_mysql_restore_fails_on_unsupported_file_extension(tmp_path: Path) -> None:
    """MySQL restore validation should reject unsupported file extensions."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    sql_file = tmp_path / "backup.txt"
    sql_file.write_text("SELECT 1;\n", encoding="utf-8")
    mysql_binary = tmp_path / "mysql"
    mysql_binary.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported restore file type\\. Use \\.sql or \\.sql\\.gz\\."):
        service.validate_mysql_restore(
            sql_file=str(sql_file),
            host="127.0.0.1",
            port="3306",
            username="root",
            password="secret",
            database="appdb",
            mysql_path=str(mysql_binary),
        )


def test_mysql_restore_fails_when_database_missing_and_create_flag_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MySQL restore should stop before execution when the target database is missing."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    sql_file = tmp_path / "backup.sql"
    sql_file.write_text("SELECT 1;\n", encoding="utf-8")
    mysql_binary = tmp_path / "mysql"
    mysql_binary.write_text("", encoding="utf-8")
    engine_calls: list[dict[str, object]] = []

    monkeypatch.setattr(service.mysql_service, "database_exists", lambda **kwargs: False)
    monkeypatch.setattr(service.mysql_engine, "run", lambda **kwargs: engine_calls.append(kwargs))

    with pytest.raises(
        ValueError,
        match='Target database does not exist\\. Enable "Create database if missing" or create it manually\\.',
    ):
        service.restore_mysql(
            sql_file=str(sql_file),
            host="127.0.0.1",
            port="3306",
            username="root",
            password="secret",
            database="appdb",
            mysql_path=str(mysql_binary),
            create_database_if_missing=False,
        )

    assert engine_calls == []


def test_mysql_restore_creates_database_when_create_flag_is_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MySQL restore should create the database before invoking the mysql client when requested."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    sql_file = tmp_path / "backup.sql"
    sql_file.write_text("SELECT 1;\n", encoding="utf-8")
    mysql_binary = tmp_path / "mysql"
    mysql_binary.write_text("", encoding="utf-8")
    expected = make_result(success=True)
    created: list[dict[str, object]] = []

    monkeypatch.setattr(service.mysql_service, "database_exists", lambda **kwargs: False)
    monkeypatch.setattr(service.mysql_service, "create_database_if_missing", lambda **kwargs: created.append(kwargs))
    monkeypatch.setattr(service.mysql_engine, "run", lambda **kwargs: expected)

    result = service.restore_mysql(
        sql_file=str(sql_file),
        host="127.0.0.1",
        port="3306",
        username="root",
        password="secret",
        database="appdb",
        mysql_path=str(mysql_binary),
        create_database_if_missing=True,
    )

    assert result.success is True
    assert created == [
        {
            "host": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "password": "secret",
            "database": "appdb",
        }
    ]


def test_mysql_restore_rejects_database_name_with_backtick(tmp_path: Path) -> None:
    """Backticks are rejected because they make identifier quoting unsafe."""
    repository = ProfileRepository(tmp_path / "config")
    service = RestoreService(repository, MySQLService(), LogService(tmp_path / "logs"))
    sql_file = tmp_path / "backup.sql"
    sql_file.write_text("SELECT 1;\n", encoding="utf-8")
    mysql_binary = tmp_path / "mysql"
    mysql_binary.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Database name cannot contain backticks\\."):
        service.validate_mysql_restore(
            sql_file=str(sql_file),
            host="127.0.0.1",
            port="3306",
            username="root",
            password="secret",
            database="bad`name",
            mysql_path=str(mysql_binary),
        )
