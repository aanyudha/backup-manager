"""Main window for the desktop application."""

from __future__ import annotations

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
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.platform_service import PlatformService
from app.services.restore_service import RestoreService
from app.ui.dashboard_page import DashboardPage
from app.ui.folder_profiles_page import FolderProfilesPage
from app.ui.logs_page import LogsPage
from app.ui.mysql_profiles_page import MySQLProfilesPage
from app.ui.restore_page import RestorePage
from app.ui.settings_page import SettingsPage
from app.workers.backup_worker import BackupWorker
from app.workers.restore_worker import RestoreWorker


class MainWindow(QMainWindow):
    """Coordinate UI pages, repository writes, and backup workers."""

    def __init__(
        self,
        *,
        repository: ProfileRepository,
        backup_service: BackupService,
        restore_service: RestoreService,
        mysql_service: MySQLService,
        platform_service: PlatformService,
        log_service: LogService,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.backup_service = backup_service
        self.restore_service = restore_service
        self.mysql_service = mysql_service
        self.platform_service = platform_service
        self.log_service = log_service
        self.worker_thread: QThread | None = None
        self.worker: object | None = None

        self.setWindowTitle("Heisenberg Backup Manager")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        self.dashboard_page = DashboardPage()
        self.mysql_profiles_page = MySQLProfilesPage(mysql_service)
        self.folder_profiles_page = FolderProfilesPage(platform_service)
        self.restore_page = RestorePage()
        self.logs_page = LogsPage(log_service.logs_dir)
        self.settings_page = SettingsPage()

        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.mysql_profiles_page, "MySQL Profiles")
        self.tabs.addTab(self.folder_profiles_page, "Folder Profiles")
        self.tabs.addTab(self.restore_page, "Restore")
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
        self.settings_page.save_requested.connect(self.save_settings)

        self.refresh_all()

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
