"""Application entry point for Heisenberg Backup Manager."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.platform_service import PlatformService
from app.ui.main_window import MainWindow


def main() -> int:
    """Start the desktop application."""
    app = QApplication(sys.argv)

    root_dir = Path(__file__).resolve().parent
    repository = ProfileRepository(root_dir / "config")
    platform_service = PlatformService()
    log_service = LogService(root_dir)
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)

    window = MainWindow(
        repository=repository,
        backup_service=backup_service,
        mysql_service=mysql_service,
        platform_service=platform_service,
        log_service=log_service,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

