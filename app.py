"""Application entry point for Heisenberg Backup Manager."""

from __future__ import annotations

import io
import sys

from app.cli.backup_profile import parse_cli_args
from app.repositories.profile_repository import ProfileRepository
from app.repositories.scheduler_state_repository import SchedulerStateRepository
from app.services.backup_service import BackupService
from app.services.cli_backup_service import CliBackupService
from app.services.external_scheduler_service import ExternalSchedulerService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.services.scheduler_service import SchedulerService


def build_runtime_services(path_service: PathService) -> dict[str, object]:
    """Construct the shared runtime services for UI and CLI modes."""
    repository = ProfileRepository(path_service.config_dir())
    platform_service = PlatformService()
    log_service = LogService(path_service.logs_dir())
    mysql_service = MySQLService()
    backup_service = BackupService(repository, platform_service, log_service)
    restore_service = RestoreService(repository, mysql_service, log_service)
    scheduler_service = SchedulerService(SchedulerStateRepository(path_service.config_dir()))
    external_scheduler_service = ExternalSchedulerService(
        app_script_path=None if path_service.is_frozen() else path_service.app_entry_path(),
        logs_dir=path_service.logs_dir(),
        exports_dir=path_service.exports_scheduler_dir(),
    )

    return {
        "path_service": path_service,
        "repository": repository,
        "platform_service": platform_service,
        "log_service": log_service,
        "mysql_service": mysql_service,
        "backup_service": backup_service,
        "restore_service": restore_service,
        "scheduler_service": scheduler_service,
        "external_scheduler_service": external_scheduler_service,
    }


def run_cli_mode(*, run_profile_id: str | None, run_profile_name: str | None) -> int:
    """Run one backup profile in CLI mode without starting Qt."""
    services = build_runtime_services(PathService())
    output = io.StringIO()
    exit_code = CliBackupService(services["backup_service"]).execute(
        profile_id=run_profile_id,
        profile_name=run_profile_name,
        stdout=output,
    )
    print(output.getvalue(), end="")
    return exit_code


def start_desktop_app() -> int:
    """Start the desktop application."""
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    services = build_runtime_services(PathService())

    window = MainWindow(
        repository=services["repository"],
        backup_service=services["backup_service"],
        restore_service=services["restore_service"],
        scheduler_service=services["scheduler_service"],
        mysql_service=services["mysql_service"],
        platform_service=services["platform_service"],
        log_service=services["log_service"],
        path_service=services["path_service"],
        external_scheduler_service=services["external_scheduler_service"],
    )
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Dispatch CLI mode or start the desktop UI."""
    args = parse_cli_args(argv)
    if args.run_profile_id or args.run_profile_name:
        return run_cli_mode(
            run_profile_id=args.run_profile_id,
            run_profile_name=args.run_profile_name,
        )
    return start_desktop_app()


if __name__ == "__main__":
    raise SystemExit(main())
