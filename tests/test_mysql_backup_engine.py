"""Tests for the MySQL backup engine."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

from app.engines.mysql_backup_engine import (
    COLUMN_STATISTICS_OPTION,
    DEFAULT_MYSQLDUMP_OPTIONS,
    MySQLBackupEngine,
)
from app.models.profile import MySQLBackupProfile
from app.services.log_service import LogService


def build_mysql_profile(tmp_path: Path) -> MySQLBackupProfile:
    """Create a valid MySQL profile for tests."""
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    return MySQLBackupProfile(
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


class FakeStreamingPopen:
    """Minimal Popen stub for streamed gzip tests."""

    def __init__(self, args: list[str], stdout=None, stderr=None, env=None):  # type: ignore[no-untyped-def]
        self.args = args
        self.env = env
        self.returncode = 0
        self.stdout = io.BytesIO(b"-- compressed dump --")
        self.stderr = io.BytesIO(b"")
        self._killed = False

    def wait(self) -> int:
        return self.returncode

    def poll(self) -> int | None:
        return None if not self._killed else self.returncode

    def kill(self) -> None:
        self._killed = True
        self.returncode = 1


def stub_versions(monkeypatch: pytest.MonkeyPatch, engine: MySQLBackupEngine) -> None:
    """Prevent tests from making real version lookups."""
    monkeypatch.setattr(engine, "get_mysql_version", lambda profile: "8.0.36")
    monkeypatch.setattr(engine, "get_mysqldump_version", lambda executable: "mysqldump 8.0.36")


def test_mysqldump_log_command_masks_password(tmp_path: Path) -> None:
    """Masked command output must not expose passwords."""
    log_service = LogService(tmp_path)
    engine = MySQLBackupEngine(log_service)
    profile = build_mysql_profile(tmp_path)

    masked = engine.build_log_command(profile)

    assert "super-secret" not in masked
    assert "--password=********" in masked


def test_build_dump_command_includes_internal_defaults(tmp_path: Path) -> None:
    """mysqldump should always include the internal compatibility defaults."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)

    command = engine.build_dump_command(profile)

    for option in DEFAULT_MYSQLDUMP_OPTIONS:
        assert option in command.args
    assert COLUMN_STATISTICS_OPTION in command.args


def test_blank_mysqldump_path_uses_path_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank mysqldump paths should auto-detect mysqldump from PATH."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    profile.mysqldump_path = None
    monkeypatch.setattr("app.engines.mysql_backup_engine.shutil.which", lambda command: "/usr/bin/mysqldump")

    resolved = engine.resolve_mysqldump(profile)

    assert resolved == "/usr/bin/mysqldump"


def test_access_denied_stderr_marks_backup_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fatal stderr should fail the backup even if mysqldump returns zero."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    stub_versions(monkeypatch, engine)

    def fake_run(args: list[str], stdout=None, stderr=None, env=None, check=False):  # type: ignore[no-untyped-def]
        assert env["MYSQL_PWD"] == "super-secret"
        stdout.write(b"-- partial dump --")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stderr=(
                b"mysqldump: Got error: 1227: Access denied; you need PROCESS privilege(s) "
                b"for this operation when trying to dump tablespaces\n"
            ),
        )

    monkeypatch.setattr("app.engines.mysql_backup_engine.subprocess.run", fake_run)

    result = engine.run(profile)

    assert result.success is False
    assert result.message.startswith("MySQL backup failed:")
    assert "Access denied" in result.message


def test_mysqldump_error_stderr_marks_backup_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mysqldump: Error lines should be treated as fatal."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    stub_versions(monkeypatch, engine)

    def fake_run(args: list[str], stdout=None, stderr=None, env=None, check=False):  # type: ignore[no-untyped-def]
        stdout.write(b"")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stderr=b"mysqldump: Error: 'Unknown database' when selecting the database\n",
        )

    monkeypatch.setattr("app.engines.mysql_backup_engine.subprocess.run", fake_run)

    result = engine.run(profile)

    assert result.success is False
    assert result.message.startswith("MySQL backup failed:")
    assert "mysqldump: Error:" in result.message


def test_column_statistics_warning_with_zero_exit_code_is_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warning-only stderr should keep the backup successful."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    stub_versions(monkeypatch, engine)

    def fake_run(args: list[str], stdout=None, stderr=None, env=None, check=False):  # type: ignore[no-untyped-def]
        stdout.write(b"-- full dump --")
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stderr=b"Warning: column statistics not supported by the server\n",
        )

    monkeypatch.setattr("app.engines.mysql_backup_engine.subprocess.run", fake_run)

    result = engine.run(profile)

    assert result.success is True
    assert result.message == (
        "MySQL backup completed with warning: Warning: column statistics not supported by the server"
    )


def test_unknown_column_statistics_retries_without_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown column-statistics support should trigger a one-time compatibility retry."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    stub_versions(monkeypatch, engine)
    commands: list[list[str]] = []

    def fake_run(args: list[str], stdout=None, stderr=None, env=None, check=False):  # type: ignore[no-untyped-def]
        commands.append(list(args))
        stdout.write(b"-- dump --")
        if len(commands) == 1:
            return subprocess.CompletedProcess(
                args=args,
                returncode=2,
                stderr=b"mysqldump: unknown variable 'column-statistics=0'\n",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stderr=b"")

    monkeypatch.setattr("app.engines.mysql_backup_engine.subprocess.run", fake_run)

    result = engine.run(profile)

    assert result.success is True
    assert len(commands) == 2
    assert COLUMN_STATISTICS_OPTION in commands[0]
    assert COLUMN_STATISTICS_OPTION not in commands[1]
    assert result.message == "MySQL backup completed successfully."
    assert result.log_file is not None
    log_text = Path(result.log_file).read_text(encoding="utf-8")
    assert "Retrying mysqldump without --column-statistics=0 for compatibility." in log_text
    assert "super-secret" not in log_text


def test_compressed_mysql_backup_creates_sql_gz_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compressed backups should stream directly to a .sql.gz artifact."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    profile.compress = True
    profile.destination_type = "network"
    stub_versions(monkeypatch, engine)

    monkeypatch.setattr("app.services.compression_service.subprocess.Popen", FakeStreamingPopen)

    result = engine.run(profile)

    assert result.success is True
    assert result.output_file is not None
    assert result.output_file.endswith(".sql.gz")
    assert Path(result.output_file).exists()
    assert Path(result.output_file).parent == Path(profile.destination)


def test_uncompressed_mysql_backup_keeps_sql_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plain backups should still write .sql files."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    stub_versions(monkeypatch, engine)

    def fake_run(args: list[str], stdout=None, stderr=None, env=None, check=False):  # type: ignore[no-untyped-def]
        stdout.write(b"-- plain dump --")
        return subprocess.CompletedProcess(args=args, returncode=0, stderr=b"")

    monkeypatch.setattr("app.services.compression_service.subprocess.run", fake_run)

    result = engine.run(profile)

    assert result.success is True
    assert result.output_file is not None
    assert result.output_file.endswith(".sql")
    assert not result.output_file.endswith(".sql.gz")


def test_compression_failure_marks_backup_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compression errors should fail the backup run."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    profile.compress = True
    stub_versions(monkeypatch, engine)

    monkeypatch.setattr("app.services.compression_service.subprocess.Popen", FakeStreamingPopen)

    def raise_compression_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr("app.services.compression_service.gzip.open", raise_compression_error)

    result = engine.run(profile)

    assert result.success is False
    assert result.message.startswith("MySQL backup failed: Compression error:")


def test_mysql_backup_fails_early_if_destination_is_unwritable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Destination access errors should stop the backup before mysqldump starts."""
    engine = MySQLBackupEngine(LogService(tmp_path))
    profile = build_mysql_profile(tmp_path)
    monkeypatch.setattr(
        engine.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (
            False,
            (
                "Destination validation failed:\n"
                f"Path: {path}\n"
                "Exists: false\n"
                "Is Dir: false\n"
                "Create Folder: failed\n"
                "Write Test: skipped\n"
                "Delete Test: skipped\n"
                "Exception: OSError: blocked"
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="Destination validation failed:"):
        engine.run(profile)
