"""Application services."""

from __future__ import annotations

__all__ = ["BackupService", "LogService", "MySQLService", "PlatformService", "RestoreService"]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Lazily expose service classes without creating import cycles."""
    if name == "BackupService":
        from app.services.backup_service import BackupService

        return BackupService
    if name == "LogService":
        from app.services.log_service import LogService

        return LogService
    if name == "MySQLService":
        from app.services.mysql_service import MySQLService

        return MySQLService
    if name == "PlatformService":
        from app.services.platform_service import PlatformService

        return PlatformService
    if name == "RestoreService":
        from app.services.restore_service import RestoreService

        return RestoreService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
