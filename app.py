"""Application entry point for Heisenberg Backup Manager."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.repositories.profile_repository import ProfileRepository
from app.repositories.scheduler_state_repository import SchedulerStateRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.services.scheduler_service import SchedulerService
from app.ui.main_window import MainWindow


def main() -> int:
    """Start the desktop application."""
    app = QApplication(sys.argv)

    path_service = PathService()
    repository = ProfileRepository(path_service.config_dir())
    platform_service = PlatformService()
    log_service = LogService(path_service.logs_dir())
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)
    restore_service = RestoreService(repository, mysql_service, log_service)
    scheduler_service = SchedulerService(SchedulerStateRepository(path_service.config_dir()))

    window = MainWindow(
        repository=repository,
        backup_service=backup_service,
        restore_service=restore_service,
        scheduler_service=scheduler_service,
        mysql_service=mysql_service,
        platform_service=platform_service,
        log_service=log_service,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
