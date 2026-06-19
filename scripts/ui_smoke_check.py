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

from PySide6.QtWidgets import QApplication, QListWidget

from app.repositories.profile_repository import ProfileRepository
from app.repositories.scheduler_state_repository import SchedulerStateRepository
from app.services.backup_service import BackupService
from app.services.external_scheduler_service import ExternalSchedulerService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.services.scheduler_service import SchedulerService
from app.ui.folder_profiles_page import FolderProfilesPage
from app.ui.main_window import MainWindow
from app.ui.mysql_profiles_page import MySQLProfilesPage


def main() -> int:
    """Instantiate the Qt application and main window without entering the event loop."""
    path_service = PathService()
    repository = ProfileRepository(path_service.config_dir())
    platform_service = PlatformService()
    log_service = LogService(path_service.logs_dir())
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)
    restore_service = RestoreService(repository, mysql_service, log_service)
    scheduler_service = SchedulerService(SchedulerStateRepository(path_service.config_dir()))
    external_scheduler_service = ExternalSchedulerService(
        app_script_path=path_service.app_entry_path(),
        logs_dir=path_service.logs_dir(),
        exports_dir=path_service.exports_scheduler_dir(),
    )

    app = QApplication([])
    window = MainWindow(
        repository=repository,
        backup_service=backup_service,
        restore_service=restore_service,
        scheduler_service=scheduler_service,
        mysql_service=mysql_service,
        platform_service=platform_service,
        log_service=log_service,
        path_service=path_service,
        external_scheduler_service=external_scheduler_service,
    )
    title = window.windowTitle()
    assert title == "Heisenberg Backup Manager", title
    print(f"UI title verified: {title}")
    assert window.tabs.tabText(3) == "Restore", window.tabs.tabText(3)
    assert window.tabs.tabText(4) == "Scheduler", window.tabs.tabText(4)
    mysql_page = MySQLProfilesPage(mysql_service)
    assert mysql_page.objectName() == "mysqlProfilesPage", mysql_page.objectName()
    database_list = mysql_page.findChild(QListWidget, "databaseListWidget")
    assert database_list is not None, "databaseListWidget not found"
    assert database_list.minimumHeight() >= 160, database_list.minimumHeight()
    print(f"MySQL database list minimum height verified: {database_list.minimumHeight()}")
    folder_page = FolderProfilesPage(platform_service)
    assert folder_page.objectName() == "folderProfilesPage", folder_page.objectName()
    assert folder_page.status_output.minimumHeight() >= 100, folder_page.status_output.minimumHeight()
    print(f"Folder status panel minimum height verified: {folder_page.status_output.minimumHeight()}")
    folder_page.close()
    mysql_page.close()
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
