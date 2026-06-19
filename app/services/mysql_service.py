"""Helpers for testing MySQL connectivity and managing databases."""

from __future__ import annotations

from collections.abc import Sequence

import pymysql

SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


class MySQLService:
    """Wrap PyMySQL calls for the UI layer."""

    def _connect(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ):
        """Open a short-lived MySQL connection with shared defaults."""
        return pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            cursorclass=pymysql.cursors.Cursor,
        )

    def normalize_database_name(self, database: str) -> str:
        """Return a stripped database name after validating it for restore use."""
        name = database.strip()
        if not name:
            raise ValueError("Target database is required.")
        if "`" in name:
            raise ValueError("Database name cannot contain backticks.")
        return name

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
            connection = self._connect(
                host=host,
                port=port,
                username=username,
                password=password,
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
            connection = self._connect(
                host=host,
                port=port,
                username=username,
                password=password,
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

    def database_exists(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
    ) -> bool:
        """Return whether the target database exists on the server."""
        database_name = self.normalize_database_name(database)
        connection = None
        try:
            connection = self._connect(
                host=host,
                port=port,
                username=username,
                password=password,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                    (database_name,),
                )
                return cursor.fetchone() is not None
        except pymysql.MySQLError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def create_database_if_missing(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
    ) -> None:
        """Create the target database if it does not already exist."""
        database_name = self.normalize_database_name(database)
        connection = None
        try:
            connection = self._connect(
                host=host,
                port=port,
                username=username,
                password=password,
            )
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
            connection.commit()
        except pymysql.MySQLError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            try:
                connection.close()
            except Exception:
                pass
