"""Main window for the desktop application."""

from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from app.models.profile import FolderBackupProfile, MySQLBackupProfile, Profile
from app.models.result import BackupResult
from app.models.settings import AppSettings
from app.repositories.profile_repository import ProfileRepository
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.mysql_service import MySQLService
from app.services.platform_service import PlatformService
from app.ui.dashboard_page import DashboardPage
from app.ui.folder_profiles_page import FolderProfilesPage
from app.ui.logs_page import LogsPage
from app.ui.mysql_profiles_page import MySQLProfilesPage
from app.ui.settings_page import SettingsPage
from app.workers.backup_worker import BackupWorker


class MainWindow(QMainWindow):
    """Coordinate UI pages, repository writes, and backup workers."""

    def __init__(
        self,
        *,
        repository: ProfileRepository,
        backup_service: BackupService,
        mysql_service: MySQLService,
        platform_service: PlatformService,
        log_service: LogService,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.backup_service = backup_service
        self.mysql_service = mysql_service
        self.platform_service = platform_service
        self.log_service = log_service
        self.worker_thread: QThread | None = None
        self.worker: BackupWorker | None = None

        self.setWindowTitle("Heisenberg Backup Manager")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        self.dashboard_page = DashboardPage()
        self.mysql_profiles_page = MySQLProfilesPage(mysql_service)
        self.folder_profiles_page = FolderProfilesPage(platform_service)
        self.logs_page = LogsPage(log_service.logs_dir)
        self.settings_page = SettingsPage()

        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.mysql_profiles_page, "MySQL Profiles")
        self.tabs.addTab(self.folder_profiles_page, "Folder Profiles")
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
        self.settings_page.load_settings(self.repository.load_settings())
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

    def run_profile(self, profile_id: str) -> None:
        """Start a background backup for the selected profile."""
        if self.worker_thread is not None:
            QMessageBox.information(self, "Backup Running", "Wait for the current backup to finish.")
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

    def _handle_progress(self, message: str) -> None:
        self.dashboard_page.append_status(message)
        self.mysql_profiles_page.append_status(message)
        self.folder_profiles_page.append_status(message)

    def _handle_finished(self, result: BackupResult) -> None:
        self.dashboard_page.append_status(result.message)
        self.logs_page.refresh()
        self.refresh_all()
        self._set_running(False)

    def _handle_failed(self, message: str) -> None:
        self.dashboard_page.append_status(f"Backup failed: {message}")
        QMessageBox.warning(self, "Backup Failed", message)
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
