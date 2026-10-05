"""Regression tests for connections to modern and legacy MySQL servers."""

from unittest.mock import MagicMock

import pymysql
import pytest

from app.services.mysql_service import MySQLService


@pytest.mark.parametrize("legacy", [False, True])
def test_empty_database_list_without_selecting_database(monkeypatch, legacy):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    connect = MagicMock(side_effect=(
        [pymysql.err.OperationalError(1115, "Unknown character set: 'utf8mb4'"), connection]
        if legacy else [connection]
    ))
    monkeypatch.setattr(pymysql, "connect", connect)

    assert MySQLService().list_databases(
        host="localhost", port=3306, username="root", password=""
    ) == []

    assert [call.kwargs["charset"] for call in connect.call_args_list] == (
        ["utf8mb4", "utf8"] if legacy else ["utf8mb4"]
    )
    assert all("database" not in call.kwargs for call in connect.call_args_list)
    assert all(call.kwargs["password"] == "" for call in connect.call_args_list)
    cursor.execute.assert_called_once_with("SHOW DATABASES")
    connection.close.assert_called_once()


@pytest.mark.parametrize("code", [1045, 2003])
def test_other_connection_errors_are_not_retried(monkeypatch, code):
    connect = MagicMock(side_effect=pymysql.err.OperationalError(code, "Connection failed"))
    monkeypatch.setattr(pymysql, "connect", connect)

    success, message = MySQLService().test_connection(
        host="localhost", port=3306, username="root", password=""
    )

    assert not success
    assert "Connection failed" in message
    connect.assert_called_once()
