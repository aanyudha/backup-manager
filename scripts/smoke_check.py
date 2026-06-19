"""Basic command-line smoke check for Heisenberg Backup Manager."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.ui.main_window import MainWindow


def main() -> int:
    """Run a lightweight import and environment smoke check."""
    path_service = PathService()
    config_dir = path_service.config_dir()
    logs_dir = path_service.logs_dir()

    platform_service = PlatformService()
    log_service = LogService(logs_dir)
    repository = ProfileRepository(config_dir)
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)
    restore_service = RestoreService(repository, mysql_service, log_service)

    print(f"Detected OS: {platform_service.system_name()}")
    print(f"Available engines: {', '.join(platform_service.get_available_engines())}")
    print(f"Config directory ready: {config_dir.exists()} -> {config_dir}")
    print(f"Logs directory ready: {logs_dir.exists()} -> {logs_dir}")

    # Import-side verification for major desktop modules without starting the UI.
    _ = backup_service, restore_service, mysql_service, MainWindow
    print("Core modules imported successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
