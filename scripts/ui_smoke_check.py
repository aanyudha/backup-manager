"""Headless UI smoke check for Heisenberg Backup Manager."""

from __future__ import annotations

import os
import platform
from pathlib import Path
import sys

if platform.system().lower() == "linux":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication

from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.ui.main_window import MainWindow


def main() -> int:
    """Instantiate the Qt application and main window without entering the event loop."""
    path_service = PathService()
    repository = ProfileRepository(path_service.config_dir())
    platform_service = PlatformService()
    log_service = LogService(path_service.logs_dir())
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)

    app = QApplication([])
    window = MainWindow(
        repository=repository,
        backup_service=backup_service,
        mysql_service=mysql_service,
        platform_service=platform_service,
        log_service=log_service,
    )
    title = window.windowTitle()
    assert title == "Heisenberg Backup Manager", title
    print(f"UI title verified: {title}")
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
