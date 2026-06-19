"""Helpers for testing MySQL connectivity and listing databases."""

from __future__ import annotations

from collections.abc import Sequence

import pymysql

SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


class MySQLService:
    """Wrap PyMySQL calls for the UI layer."""

    def test_connection(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        """Test whether MySQL credentials are valid."""
        connection = None
        try:
            connection = pymysql.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
            )
        except pymysql.MySQLError as exc:
            return False, str(exc)
        connection.close()
        return True, "Connection successful."

    def list_databases(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        exclude_system: bool = True,
    ) -> Sequence[str]:
        """Return available databases for the provided connection."""
        connection = None
        try:
            connection = pymysql.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
                cursorclass=pymysql.cursors.Cursor,
            )
            with connection.cursor() as cursor:
                cursor.execute("SHOW DATABASES")
                rows = cursor.fetchall()
        except pymysql.MySQLError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            try:
                connection.close()
            except Exception:
                pass

        databases = [row[0] for row in rows]
        if exclude_system:
            databases = [name for name in databases if name not in SYSTEM_DATABASES]
        return databases
