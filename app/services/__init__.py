"""Application services."""

from __future__ import annotations

__all__ = [
    "BackupService",
    "CompressionService",
    "LogService",
    "MySQLService",
    "PlatformService",
    "RestoreService",
    "SchedulerService",
    "RetentionService",
    "VerificationService",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Lazily expose service classes without creating import cycles."""
    if name == "BackupService":
        from app.services.backup_service import BackupService

        return BackupService
    if name == "LogService":
        from app.services.log_service import LogService

        return LogService
    if name == "CompressionService":
        from app.services.compression_service import CompressionService

        return CompressionService
    if name == "MySQLService":
        from app.services.mysql_service import MySQLService

        return MySQLService
    if name == "PlatformService":
        from app.services.platform_service import PlatformService

        return PlatformService
    if name == "RetentionService":
        from app.services.retention_service import RetentionService

        return RetentionService
    if name == "SchedulerService":
        from app.services.scheduler_service import SchedulerService

        return SchedulerService
    if name == "RestoreService":
        from app.services.restore_service import RestoreService

        return RestoreService
    if name == "VerificationService":
        from app.services.verification_service import VerificationService

        return VerificationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
