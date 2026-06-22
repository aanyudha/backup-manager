"""Main window for the desktop application."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from app.models.profile import FolderBackupProfile, MySQLBackupProfile, Profile
from app.models.restore_result import RestoreResult
from app.models.result import BackupResult
from app.models.settings import AppSettings
from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.external_scheduler_service import ExternalSchedulerService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.path_service import PathService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.services.scheduler_service import SchedulerService
from app.services.service_mode_export_service import ServiceModeExportService
from app.ui.dashboard_page import DashboardPage
from app.ui.external_scheduler_export_dialog import ExternalSchedulerExportDialog
from app.ui.folder_profiles_page import FolderProfilesPage
from app.ui.logs_page import LogsPage
from app.ui.mysql_profiles_page import MySQLProfilesPage
from app.ui.restore_page import RestorePage
from app.ui.scheduler_page import SchedulerPage
from app.ui.settings_page import SettingsPage
from app.workers.backup_worker import BackupWorker
from app.workers.restore_worker import RestoreWorker
from app.workers.scheduler_worker import SchedulerWorker


class MainWindow(QMainWindow):
    """Coordinate UI pages, repository writes, and backup workers."""

    def __init__(
        self,
        *,
        repository: ProfileRepository,
        backup_service: BackupService,
        restore_service: RestoreService,
        scheduler_service: SchedulerService,
        mysql_service: MySQLService,
        platform_service: PlatformService,
        log_service: LogService,
        path_service: PathService,
        external_scheduler_service: ExternalSchedulerService,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.backup_service = backup_service
        self.restore_service = restore_service
        self.scheduler_service = scheduler_service
        self.mysql_service = mysql_service
        self.platform_service = platform_service
        self.log_service = log_service
        self.path_service = path_service
        self.external_scheduler_service = external_scheduler_service
        self.service_mode_export_service = ServiceModeExportService(
            app_script_path=None if path_service.is_frozen() else path_service.app_entry_path(),
            working_directory=path_service.app_root(),
            exports_dir=path_service.exports_service_dir(),
        )
        self.worker_thread: QThread | None = None
        self.worker: object | None = None
        self.scheduler_thread: QThread | None = None
        self.scheduler_worker: SchedulerWorker | None = None
        self._scheduler_continuous = False

        self.setWindowTitle("Heisenberg Backup Manager")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        self.dashboard_page = DashboardPage()
        self.mysql_profiles_page = MySQLProfilesPage(mysql_service)
        self.folder_profiles_page = FolderProfilesPage(platform_service)
        self.restore_page = RestorePage()
        self.scheduler_page = SchedulerPage()
        self.logs_page = LogsPage(log_service.logs_dir)
        self.settings_page = SettingsPage()

        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.mysql_profiles_page, "MySQL Profiles")
        self.tabs.addTab(self.folder_profiles_page, "Folder Profiles")
        self.tabs.addTab(self.restore_page, "Restore")
        self.tabs.addTab(self.scheduler_page, "Scheduler")
        self.tabs.addTab(self.logs_page, "Logs")
        self.tabs.addTab(self.settings_page, "Settings")
        self.setCentralWidget(self.tabs)

        self.dashboard_page.run_requested.connect(self.run_profile)
        self.dashboard_page.refresh_requested.connect(self.refresh_all)
        self.mysql_profiles_page.save_requested.connect(self.save_profile)
        self.mysql_profiles_page.delete_requested.connect(self.delete_profile)
        self.mysql_profiles_page.run_requested.connect(self.run_profile)
        self.folder_profiles_page.save_requested.connect(self.save_profile)
        self.folder_profiles_page.delete_requested.connect(self.delete_profile)
        self.folder_profiles_page.run_requested.connect(self.run_profile)
        self.restore_page.mysql_validate_requested.connect(self.validate_mysql_restore_file)
        self.restore_page.mysql_test_requested.connect(self.test_mysql_restore_connection)
        self.restore_page.mysql_restore_requested.connect(self.run_mysql_restore)
        self.restore_page.folder_validate_requested.connect(self.validate_folder_restore)
        self.restore_page.folder_restore_requested.connect(self.run_folder_restore)
        self.scheduler_page.refresh_requested.connect(self.refresh_all)
        self.scheduler_page.run_due_requested.connect(self.run_due_now)
        self.scheduler_page.export_requested.connect(self.export_external_schedule)
        self.scheduler_page.start_requested.connect(self.start_scheduler)
        self.scheduler_page.stop_requested.connect(self.stop_scheduler)
        self.settings_page.save_requested.connect(self.save_settings)
        self.settings_page.export_windows_service_requested.connect(self.export_windows_service)
        self.settings_page.export_linux_service_requested.connect(self.export_linux_service)

        self.refresh_all()
        if self.settings_page.auto_start_scheduler_checkbox.isChecked():
            self.start_scheduler()

    def refresh_all(self) -> None:
        """Reload profiles, settings, and log list from disk."""
        profiles = self.repository.list_profiles()
        self.dashboard_page.set_profiles(profiles)
        self.mysql_profiles_page.set_profiles(
            [profile for profile in profiles if isinstance(profile, MySQLBackupProfile)]
        )
        self.folder_profiles_page.set_profiles(
            [profile for profile in profiles if isinstance(profile, FolderBackupProfile)]
        )
        settings = self.repository.load_settings()
        self.settings_page.load_settings(settings)
        self.restore_page.load_settings(settings)
        self.restore_page.set_history(self.restore_service.list_history())
        self.scheduler_page.set_rows(self._build_scheduler_rows(profiles))
        self.scheduler_page.set_scheduler_running(self.scheduler_thread is not None and self._scheduler_continuous)
        self.logs_page.refresh()

    def save_profile(self, profile: Profile) -> None:
        """Persist a new or updated profile."""
        try:
            if self.repository.get_by_id(profile.id):
                self.repository.update(profile)
                message = f"Updated profile '{profile.name}'."
            else:
                self.repository.create(profile)
                message = f"Created profile '{profile.name}'."
        except Exception as exc:
            QMessageBox.warning(self, "Save Profile", str(exc))
            return

        self.dashboard_page.append_status(message)
        self.mysql_profiles_page.append_status(message)
        self.folder_profiles_page.append_status(message)
        self.refresh_all()

    def delete_profile(self, profile_id: str) -> None:
        """Delete the requested profile."""
        profile = self.repository.get_by_id(profile_id)
        if not profile:
            return
        self.repository.delete(profile_id)
        message = f"Deleted profile '{profile.name}'."
        self.dashboard_page.append_status(message)
        self.refresh_all()

    def save_settings(self, settings: AppSettings) -> None:
        """Persist application settings."""
        self.repository.save_settings(settings)
        self.settings_page.set_status("Settings saved.")
        self.dashboard_page.append_status("Settings updated.")
        if settings.auto_start_scheduler:
            self.scheduler_page.append_status("Auto-start scheduler is enabled for the next app launch.")
        self.restore_page.load_settings(settings)

    def run_profile(self, profile_id: str) -> None:
        """Start a background backup for the selected profile."""
        if self.worker_thread is not None:
            QMessageBox.information(self, "Operation Running", "Wait for the current operation to finish.")
            return

        profile = self.repository.get_by_id(profile_id)
        if not profile:
            QMessageBox.warning(self, "Run Backup", "Profile not found.")
            return
        if not profile.enabled:
            QMessageBox.information(self, "Run Backup", "Selected profile is disabled.")
            return

        self.dashboard_page.clear_status()
        self.dashboard_page.append_status(f"Starting backup for '{profile.name}'.")
        self._set_running(True)

        self.worker_thread = QThread(self)
        self.worker = BackupWorker(self.backup_service, profile_id)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.started.connect(lambda _: self.dashboard_page.append_status("Backup worker started."))
        self.worker.progress.connect(self._handle_progress)
        self.worker.finished.connect(self._handle_finished)
        self.worker.failed.connect(self._handle_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def validate_mysql_restore_file(self, payload: dict[str, object]) -> None:
        """Validate the selected MySQL restore request."""
        try:
            _, message = self.restore_service.validate_mysql_restore(
                sql_file=str(payload.get("sql_file", "")),
                host=str(payload.get("host", "")),
                port=payload.get("port", "3306"),
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                database=str(payload.get("database", "")),
                mysql_path=self._normalize_optional_payload_text(payload.get("mysql_path")),
                create_database_if_missing=bool(payload.get("create_database_if_missing", False)),
            )
        except Exception as exc:
            self.restore_page.append_status(str(exc))
            QMessageBox.warning(self, "Validate Restore", str(exc))
            return
        self.restore_page.append_status(message)

    def test_mysql_restore_connection(self, payload: dict[str, object]) -> None:
        """Test the MySQL restore connection details."""
        try:
            success, message = self.restore_service.test_mysql_connection(
                host=str(payload.get("host", "")),
                port=payload.get("port", "3306"),
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
            )
        except Exception as exc:
            self.restore_page.append_status(str(exc))
            QMessageBox.warning(self, "Test Connection", str(exc))
            return

        self.restore_page.append_status(message)
        if not success:
            QMessageBox.warning(self, "Test Connection", message)

    def validate_folder_restore(self, payload: dict[str, object]) -> None:
        """Validate folder restore paths."""
        try:
            _, message = self.restore_service.validate_folder_restore(
                str(payload.get("source", "")),
                str(payload.get("destination", "")),
            )
        except Exception as exc:
            self.restore_page.append_status(str(exc))
            QMessageBox.warning(self, "Validate Folder Restore", str(exc))
            return
        self.restore_page.append_status(message)

    def run_mysql_restore(self, payload: dict[str, object]) -> None:
        """Start a background MySQL restore."""
        if self.worker_thread is not None:
            QMessageBox.information(self, "Restore Running", "Wait for the current operation to finish.")
            return
        try:
            validated_payload, validation_message = self.restore_service.validate_mysql_restore(
                sql_file=str(payload.get("sql_file", "")),
                host=str(payload.get("host", "")),
                port=payload.get("port", "3306"),
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                database=str(payload.get("database", "")),
                mysql_path=self._normalize_optional_payload_text(payload.get("mysql_path")),
                create_database_if_missing=bool(payload.get("create_database_if_missing", False)),
            )
        except Exception as exc:
            self.restore_page.append_status(str(exc))
            QMessageBox.warning(self, "Run Restore", str(exc))
            return
        if not self._confirm_mysql_restore(validated_payload):
            return

        self.restore_page.clear_status()
        database = str(validated_payload.get("database", "")).strip() or "database"
        self.restore_page.append_status(validation_message)
        self.restore_page.append_status(f"Starting MySQL restore for '{database}'.")
        self._set_running(True)

        self.worker_thread = QThread(self)
        self.worker = RestoreWorker(self.restore_service, "mysql", validated_payload)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.started.connect(lambda restore_type: self.restore_page.append_status(f"Restore worker started ({restore_type})."))
        self.worker.progress.connect(self._handle_progress)
        self.worker.finished.connect(self._handle_finished)
        self.worker.failed.connect(self._handle_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def run_folder_restore(self, payload: dict[str, object]) -> None:
        """Start a background folder restore."""
        if self.worker_thread is not None:
            QMessageBox.information(self, "Restore Running", "Wait for the current operation to finish.")
            return
        if not self._confirm_folder_restore(payload):
            return
        try:
            validated_payload, validation_message = self.restore_service.validate_folder_restore(
                str(payload.get("source", "")),
                str(payload.get("destination", "")),
            )
        except Exception as exc:
            self.restore_page.append_status(str(exc))
            QMessageBox.warning(self, "Run Restore", str(exc))
            return

        self.restore_page.clear_status()
        self.restore_page.append_status(validation_message)
        self.restore_page.append_status("Starting folder restore.")
        self._set_running(True)

        self.worker_thread = QThread(self)
        self.worker = RestoreWorker(self.restore_service, "folder", validated_payload)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.started.connect(lambda restore_type: self.restore_page.append_status(f"Restore worker started ({restore_type})."))
        self.worker.progress.connect(self._handle_progress)
        self.worker.finished.connect(self._handle_finished)
        self.worker.failed.connect(self._handle_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _handle_progress(self, message: str) -> None:
        self.dashboard_page.append_status(message)
        self.mysql_profiles_page.append_status(message)
        self.folder_profiles_page.append_status(message)
        self.restore_page.append_status(message)

    def _handle_finished(self, result: object) -> None:
        if isinstance(result, BackupResult):
            self.dashboard_page.append_status(result.message)
        elif isinstance(result, RestoreResult):
            self.dashboard_page.append_status(result.message)
            self.restore_page.show_restore_result(result)
        self.logs_page.refresh()
        self.refresh_all()
        self._set_running(False)

    def _handle_failed(self, message: str) -> None:
        self.dashboard_page.append_status(f"Operation failed: {message}")
        self.restore_page.append_status(f"Restore failed: {message}")
        QMessageBox.warning(self, "Operation Failed", message)
        self._set_running(False)

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None

    def _set_running(self, running: bool) -> None:
        self.dashboard_page.set_running(running)
        self.mysql_profiles_page.set_running(running)
        self.folder_profiles_page.set_running(running)
        self.restore_page.set_running(running)

    def start_scheduler(self) -> None:
        """Start the continuous internal scheduler."""
        if self.scheduler_thread is not None:
            QMessageBox.information(self, "Scheduler Running", "Wait for the current scheduler operation to finish.")
            return
        self._start_scheduler_worker(run_once=False)

    def stop_scheduler(self) -> None:
        """Request that the continuous scheduler stop."""
        if self.scheduler_worker is None or not self._scheduler_continuous:
            QMessageBox.information(self, "Scheduler", "Scheduler is not currently running.")
            return
        self.scheduler_page.append_status("Stopping scheduler...")
        self.scheduler_worker.stop()

    def run_due_now(self) -> None:
        """Trigger an immediate due-profile check."""
        if self.scheduler_worker is not None and self._scheduler_continuous:
            self.scheduler_page.append_status("Immediate due check requested.")
            self.dashboard_page.append_status("Immediate due check requested.")
            self.scheduler_worker.request_run_due_now()
            return
        if self.scheduler_thread is not None:
            QMessageBox.information(self, "Scheduler Busy", "Wait for the current due check to finish.")
            return
        self._start_scheduler_worker(run_once=True)

    def export_external_schedule(self) -> None:
        """Show export commands for the selected scheduler profile."""
        profile_id = self.scheduler_page.current_profile_id()
        if not profile_id:
            QMessageBox.information(
                self,
                "Export External Schedule",
                "Select a profile in the Scheduler table first.",
            )
            return

        profile = self.repository.get_by_id(profile_id)
        if not profile:
            QMessageBox.warning(self, "Export External Schedule", "Selected profile was not found.")
            return

        try:
            export = self.external_scheduler_service.build_export(
                profile,
                self.path_service.executable_path(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export External Schedule", str(exc))
            return

        dialog = ExternalSchedulerExportDialog(profile.name, export)
        dialog.save_windows_button.clicked.connect(
            lambda: self._save_windows_export(profile)
        )
        dialog.save_linux_button.clicked.connect(
            lambda: self._save_linux_export(profile)
        )
        dialog.exec()

    def _start_scheduler_worker(self, *, run_once: bool) -> None:
        """Create and start the scheduler worker thread."""
        self.scheduler_thread = QThread(self)
        self.scheduler_worker = SchedulerWorker(
            self.backup_service,
            self.scheduler_service,
            self.log_service,
            run_once=run_once,
        )
        self._scheduler_continuous = not run_once
        self.scheduler_worker.moveToThread(self.scheduler_thread)
        self.scheduler_thread.started.connect(self.scheduler_worker.run)
        self.scheduler_worker.progress.connect(self._handle_scheduler_progress)
        self.scheduler_worker.profile_completed.connect(lambda _: self.refresh_all())
        self.scheduler_worker.finished.connect(self.refresh_all)
        self.scheduler_worker.finished.connect(self.scheduler_thread.quit)
        self.scheduler_worker.failed.connect(self._handle_scheduler_failed)
        self.scheduler_worker.failed.connect(self.scheduler_thread.quit)
        self.scheduler_thread.finished.connect(self._cleanup_scheduler_worker)
        self.scheduler_thread.start()
        self.scheduler_page.set_scheduler_running(self._scheduler_continuous)

    def _handle_scheduler_progress(self, message: str) -> None:
        self.scheduler_page.append_status(message)
        self.dashboard_page.append_status(message)
        if "Scheduled backup finished" in message or "Skipped profile" in message:
            self.logs_page.refresh()

    def _handle_scheduler_failed(self, message: str) -> None:
        self.scheduler_page.append_status(f"Scheduler failed: {message}")
        self.dashboard_page.append_status(f"Scheduler failed: {message}")
        QMessageBox.warning(self, "Scheduler Failed", message)

    def _cleanup_scheduler_worker(self) -> None:
        if self.scheduler_worker is not None:
            self.scheduler_worker.deleteLater()
        if self.scheduler_thread is not None:
            self.scheduler_thread.deleteLater()
        self.scheduler_worker = None
        self.scheduler_thread = None
        self._scheduler_continuous = False
        self.scheduler_page.set_scheduler_running(False)

    def _build_scheduler_rows(self, profiles: list[Profile]) -> list[dict[str, str]]:
        now = datetime.now().astimezone()
        rows: list[dict[str, str]] = []
        for profile in sorted(profiles, key=lambda item: item.name.lower()):
            next_run = self.scheduler_service.get_next_run(profile, now)
            next_run_text = self._format_datetime(next_run)
            if (
                profile.schedule_enabled
                and profile.schedule_runner == "external"
                and profile.schedule_type != "manual"
            ):
                next_run_text = "Managed by OS scheduler"
            rows.append(
                {
                    "profile_id": profile.id,
                    "profile_name": profile.name,
                    "type": profile.type,
                    "schedule_enabled": "Yes" if profile.schedule_enabled else "No",
                    "runner": self._format_schedule_runner(profile.schedule_runner),
                    "schedule_summary": self.scheduler_service.get_schedule_summary(profile),
                    "last_run": self._format_datetime(profile.last_run_at),
                    "next_run": next_run_text,
                    "last_status": profile.last_status or "",
                }
            )
        return rows

    def _confirm_mysql_restore(self, payload: dict[str, object]) -> bool:
        """Confirm the destructive MySQL restore action with the user."""
        answer = QMessageBox.question(
            self,
            "Confirm Restore",
            self.build_mysql_restore_confirmation(
                database=str(payload.get("database", "")).strip(),
                sql_file=str(payload.get("sql_file", "")).strip(),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_folder_restore(self, payload: dict[str, object]) -> bool:
        """Confirm the destructive folder restore action with the user."""
        answer = QMessageBox.question(
            self,
            "Confirm Restore",
            self.build_folder_restore_confirmation(destination=str(payload.get("destination", "")).strip()),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    @staticmethod
    def build_mysql_restore_confirmation(*, database: str, sql_file: str) -> str:
        """Return the MySQL restore confirmation dialog text."""
        return (
            "This restore may overwrite existing database objects in:\n"
            f"{database}\n\n"
            "Source file:\n"
            f"{sql_file}\n\n"
            "Continue?"
        )

    @staticmethod
    def build_folder_restore_confirmation(*, destination: str) -> str:
        """Return the folder restore confirmation dialog text."""
        return (
            "This restore will copy files into:\n"
            f"{destination}\n\n"
            "Existing files with the same name may be overwritten.\n"
            "No files will be deleted.\n\n"
            "Continue?"
        )

    @staticmethod
    def _normalize_optional_payload_text(value: object) -> str | None:
        """Collapse blank optional payload values to None."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _format_datetime(value) -> str:
        if not value:
            return ""
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_schedule_runner(schedule_runner: str) -> str:
        if schedule_runner == "external":
            return "External OS Scheduler"
        return "Internal Scheduler"

    def _save_windows_export(self, profile: Profile) -> None:
        """Persist the Windows scheduler export files."""
        paths = self.external_scheduler_service.save_windows_exports(profile, self.path_service.executable_path())
        joined_paths = "\n".join(str(path) for path in paths)
        self.scheduler_page.append_status(f"Saved Windows exports:\n{joined_paths}")
        self.dashboard_page.append_status(f"Saved Windows export for '{profile.name}'.")
        QMessageBox.information(self, "Export External Schedule", f"Saved Windows exports:\n{joined_paths}")

    def _save_linux_export(self, profile: Profile) -> None:
        """Persist the Linux scheduler export files."""
        paths = self.external_scheduler_service.save_linux_exports(profile, self.path_service.executable_path())
        joined_paths = "\n".join(str(path) for path in paths)
        self.scheduler_page.append_status(f"Saved Linux exports:\n{joined_paths}")
        self.dashboard_page.append_status(f"Saved Linux export for '{profile.name}'.")
        QMessageBox.information(self, "Export External Schedule", f"Saved Linux exports:\n{joined_paths}")

    def export_windows_service(self) -> None:
        """Persist Windows service helper files."""
        paths = self.service_mode_export_service.save_windows_exports(self.path_service.executable_path())
        joined_paths = "\n".join(str(path) for path in paths)
        self.settings_page.set_status("Windows service helper files exported.")
        self.dashboard_page.append_status("Saved Windows service helper exports.")
        QMessageBox.information(self, "Export Windows Service Task", f"Saved files:\n{joined_paths}")

    def export_linux_service(self) -> None:
        """Persist Linux service helper files."""
        paths = self.service_mode_export_service.save_linux_exports(self.path_service.executable_path())
        joined_paths = "\n".join(str(path) for path in paths)
        self.settings_page.set_status("Linux service helper files exported.")
        self.dashboard_page.append_status("Saved Linux service helper exports.")
        QMessageBox.information(self, "Export Linux systemd Service", f"Saved files:\n{joined_paths}")
