"""Service layer for restore execution and restore history persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.engines.folder_restore_engine import FolderRestoreEngine
from app.engines.mysql_restore_engine import MySQLRestoreEngine
from app.models.restore_result import RestoreResult
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class MySQLRestoreValidation:
    """Normalized MySQL restore inputs plus preflight findings."""

    sql_file: str
    host: str
    port: int
    username: str
    password: str
    database: str
    mysql_path: str | None
    create_database_if_missing: bool
    database_exists: bool
    source_path: Path


class RestoreService:
    """Coordinate restore validation, execution, and history persistence."""

    def __init__(
        self,
        repository: ProfileRepository,
        mysql_service: MySQLService,
        log_service: LogService,
    ) -> None:
        self.repository = repository
        self.mysql_service = mysql_service
        self.log_service = log_service
        self.mysql_engine = MySQLRestoreEngine(log_service)
        self.folder_engine = FolderRestoreEngine(log_service)

    def list_history(self) -> list[RestoreResult]:
        """Return restore history ordered from newest to oldest."""
        history = self.repository.list_restore_history()
        return sorted(history, key=lambda item: item.finished_at, reverse=True)

    def validate_mysql_restore(
        self,
        *,
        sql_file: str,
        host: str,
        port: int | str | object,
        username: str,
        password: str,
        database: str,
        mysql_path: str | None = None,
        create_database_if_missing: bool = False,
    ) -> tuple[dict[str, object], str]:
        """Validate a full MySQL restore request without executing the restore."""
        validation = self._prepare_mysql_restore(
            sql_file=sql_file,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            mysql_path=mysql_path,
            create_database_if_missing=create_database_if_missing,
        )
        payload: dict[str, object] = {
            "sql_file": validation.sql_file,
            "host": validation.host,
            "port": validation.port,
            "username": validation.username,
            "password": validation.password,
            "database": validation.database,
            "mysql_path": validation.mysql_path,
            "create_database_if_missing": validation.create_database_if_missing,
        }
        if validation.database_exists:
            detail = "Target database exists."
        elif validation.create_database_if_missing:
            detail = 'Target database does not exist yet and will be created because "Create database if missing" is enabled.'
        else:
            detail = "Target database exists."
        return payload, f"MySQL restore validation passed. {detail}"

    def test_mysql_connection(
        self,
        *,
        host: str,
        port: int | str | object,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        """Test MySQL connectivity for restore inputs."""
        normalized_port = self._normalize_port(port)
        return self.mysql_service.test_connection(
            host=host,
            port=normalized_port,
            username=username,
            password=password,
        )

    def validate_folder_restore(self, source: str, destination: str) -> tuple[dict[str, str], str]:
        """Validate folder restore paths."""
        source_path, destination_path = self.folder_engine.validate_paths(source, destination)
        payload = {
            "source": str(source_path),
            "destination": str(destination_path),
        }
        return payload, f"Folder restore validation passed: {source_path} -> {destination_path}"

    def restore_mysql(
        self,
        *,
        sql_file: str,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        mysql_path: str | None = None,
        create_database_if_missing: bool = False,
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        """Run a MySQL restore and persist its result."""
        validation = self._prepare_mysql_restore(
            sql_file=sql_file,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            mysql_path=mysql_path,
            create_database_if_missing=create_database_if_missing,
        )
        if validation.create_database_if_missing:
            if progress:
                progress(f"Ensuring target database exists for {validation.database}...")
            self.mysql_service.create_database_if_missing(
                host=validation.host,
                port=validation.port,
                username=validation.username,
                password=validation.password,
                database=validation.database,
            )
        result = self.mysql_engine.run(
            sql_file=validation.sql_file,
            host=validation.host,
            port=validation.port,
            username=validation.username,
            password=validation.password,
            database=validation.database,
            mysql_path=validation.mysql_path,
            progress=progress,
        )
        self.repository.append_restore_result(result)
        self.log_service.log_app(
            f"MySQL restore finished with status={'success' if result.success else 'failed'}: {result.message}"
        )
        return result

    def restore_folder(
        self,
        *,
        source: str,
        destination: str,
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        """Run a folder restore and persist its result."""
        validated_payload, _ = self.validate_folder_restore(source, destination)
        result = self.folder_engine.run(
            source=validated_payload["source"],
            destination=validated_payload["destination"],
            progress=progress,
        )
        self.repository.append_restore_result(result)
        self.log_service.log_app(
            f"Folder restore finished with status={'success' if result.success else 'failed'}: {result.message}"
        )
        return result

    def _prepare_mysql_restore(
        self,
        *,
        sql_file: str,
        host: str,
        port: int | str | object,
        username: str,
        password: str,
        database: str,
        mysql_path: str | None,
        create_database_if_missing: bool,
    ) -> MySQLRestoreValidation:
        """Normalize and preflight-check a MySQL restore request."""
        normalized_host = host.strip()
        normalized_username = username.strip()
        normalized_database = self.mysql_service.normalize_database_name(database)
        normalized_port = self._normalize_port(port)
        normalized_mysql_path = self._normalize_optional_text(mysql_path)
        source_path = self.mysql_engine.validate_request(
            sql_file=sql_file,
            host=normalized_host,
            port=normalized_port,
            username=normalized_username,
            database=normalized_database,
            mysql_path=normalized_mysql_path,
        )
        database_exists = self.mysql_service.database_exists(
            host=normalized_host,
            port=normalized_port,
            username=normalized_username,
            password=password,
            database=normalized_database,
        )
        if not database_exists and not create_database_if_missing:
            raise ValueError(
                'Target database does not exist. Enable "Create database if missing" or create it manually.'
            )
        return MySQLRestoreValidation(
            sql_file=str(source_path),
            host=normalized_host,
            port=normalized_port,
            username=normalized_username,
            password=password,
            database=normalized_database,
            mysql_path=normalized_mysql_path,
            create_database_if_missing=create_database_if_missing,
            database_exists=database_exists,
            source_path=source_path,
        )

    def _normalize_port(self, port: int | str | object) -> int:
        """Parse the incoming port into a positive integer."""
        try:
            value = int(str(port).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Port must be a valid integer.") from exc
        if value <= 0:
            raise ValueError("Port must be a valid integer.")
        return value

    def _normalize_optional_text(self, value: str | None) -> str | None:
        """Convert blank optional text inputs to None."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
