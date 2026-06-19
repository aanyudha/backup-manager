"""Service layer for restore execution and restore history persistence."""

from __future__ import annotations

from collections.abc import Callable

from app.engines.folder_restore_engine import FolderRestoreEngine
from app.engines.mysql_restore_engine import MySQLRestoreEngine
from app.models.restore_result import RestoreResult
from app.repositories.profile_repository import ProfileRepository
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService

ProgressCallback = Callable[[str], None]


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

    def validate_mysql_file(self, sql_file: str) -> tuple[bool, str]:
        """Validate a MySQL restore source file."""
        path = self.mysql_engine.validate_sql_file(sql_file)
        return True, f"SQL file validation passed: {path}"

    def test_mysql_connection(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        """Test MySQL connectivity for restore inputs."""
        return self.mysql_service.test_connection(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def validate_folder_restore(self, source: str, destination: str) -> tuple[bool, str]:
        """Validate folder restore paths."""
        source_path, destination_path = self.folder_engine.validate_paths(source, destination)
        return True, f"Folder restore validation passed: {source_path} -> {destination_path}"

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
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        """Run a MySQL restore and persist its result."""
        result = self.mysql_engine.run(
            sql_file=sql_file,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            mysql_path=mysql_path,
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
        result = self.folder_engine.run(
            source=source,
            destination=destination,
            progress=progress,
        )
        self.repository.append_restore_result(result)
        self.log_service.log_app(
            f"Folder restore finished with status={'success' if result.success else 'failed'}: {result.message}"
        )
        return result
