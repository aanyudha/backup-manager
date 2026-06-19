"""Tests for the MySQL restore engine."""

from __future__ import annotations

import gzip
import subprocess
from pathlib import Path

import pytest

from app.engines.mysql_restore_engine import MySQLRestoreEngine
from app.services.log_service import LogService


def make_mysql_binary(tmp_path: Path) -> Path:
    """Create a fake mysql client path for tests."""
    binary = tmp_path / "mysql"
    binary.write_text("", encoding="utf-8")
    return binary


def test_build_restore_command_masks_password(tmp_path: Path) -> None:
    """Restore command logs must not expose passwords."""
    engine = MySQLRestoreEngine(LogService(tmp_path))
    binary = make_mysql_binary(tmp_path)

    command = engine.build_restore_command(
        host="127.0.0.1",
        port=3306,
        username="root",
        password="top-secret",
        database="appdb",
        mysql_path=str(binary),
    )

    assert command.args == [
        str(binary),
        "--host=127.0.0.1",
        "--port=3306",
        "--user=root",
        "appdb",
    ]
    assert command.env["MYSQL_PWD"] == "top-secret"
    masked = engine.build_log_command(command, has_password=True)
    assert "top-secret" not in masked
    assert "--password=********" in masked


def test_sql_gz_restore_uses_decompressed_sql(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.sql.gz` input should be inflated before invoking mysql."""
    logs_dir = tmp_path / "logs"
    engine = MySQLRestoreEngine(LogService(logs_dir))
    binary = make_mysql_binary(tmp_path)
    sql_bytes = b"CREATE TABLE demo (id INT);\nINSERT INTO demo VALUES (1);\n"
    compressed_path = tmp_path / "restore.sql.gz"
    with gzip.open(compressed_path, "wb") as handle:
        handle.write(sql_bytes)

    captured: dict[str, object] = {}

    def fake_run(  # type: ignore[no-untyped-def]
        args,
        stdin=None,
        stdout=None,
        stderr=None,
        env=None,
        check=False,
    ):
        captured["args"] = list(args)
        captured["stdin_bytes"] = stdin.read()
        captured["env"] = dict(env or {})
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("app.engines.mysql_restore_engine.subprocess.run", fake_run)

    result = engine.run(
        sql_file=str(compressed_path),
        host="localhost",
        port=3306,
        username="root",
        password="secret",
        database="appdb",
        mysql_path=str(binary),
    )

    assert result.success is True
    assert captured["stdin_bytes"] == sql_bytes
    assert captured["args"] == [
        str(binary),
        "--host=localhost",
        "--port=3306",
        "--user=root",
        "appdb",
    ]
    assert captured["env"]["MYSQL_PWD"] == "secret"
    assert result.log_file is not None
    assert Path(result.log_file).exists()
