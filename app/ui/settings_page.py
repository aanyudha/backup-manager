"""Application settings page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.settings import AppSettings


class SettingsPage(QWidget):
    """Edit and save application-wide defaults."""

    save_requested = Signal(object)
    export_windows_service_requested = Signal()
    export_linux_service_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loaded_service_runner_mode = "internal_scheduler"

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.default_backup_folder_edit = QLineEdit()
        self.default_log_folder_edit = QLineEdit()
        self.default_mysqldump_path_edit = QLineEdit()
        self.auto_start_scheduler_checkbox = QCheckBox("Auto-start scheduler when app opens")
        self.run_as_service_checkbox = QCheckBox("Run as Service / Background Scheduler Mode")
        self.run_as_service_help = QLabel(
            "Service mode is intended for running scheduled backups without opening the desktop UI. "
            "Installation requires OS-specific setup.\n"
            "To use service mode, set each profile Schedule Runner to Background Service Scheduler."
        )
        self.run_as_service_help.setWordWrap(True)
        self.export_windows_service_button = QPushButton("Export Windows Service Task")
        self.export_linux_service_button = QPushButton("Export Linux systemd Service")
        self.export_help = QLabel("Exports generate helper files only. Nothing is installed automatically.")
        self.export_help.setWordWrap(True)
        self.status_label = QLabel()
        self.save_button = QPushButton("Save Settings")

        form.addRow("Default Backup Folder", self.default_backup_folder_edit)
        form.addRow("Default Log Folder", self.default_log_folder_edit)
        form.addRow("Default mysqldump Path", self.default_mysqldump_path_edit)
        form.addRow("", self.auto_start_scheduler_checkbox)
        form.addRow("", self.run_as_service_checkbox)
        form.addRow("", self.run_as_service_help)

        layout.addLayout(form)
        layout.addWidget(self.export_windows_service_button)
        layout.addWidget(self.export_linux_service_button)
        layout.addWidget(self.export_help)
        layout.addWidget(self.save_button)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.save_button.clicked.connect(self._emit_save)
        self.export_windows_service_button.clicked.connect(self.export_windows_service_requested.emit)
        self.export_linux_service_button.clicked.connect(self.export_linux_service_requested.emit)

    def load_settings(self, settings: AppSettings) -> None:
        """Populate fields from saved settings."""
        self.default_backup_folder_edit.setText(settings.default_backup_folder)
        self.default_log_folder_edit.setText(settings.default_log_folder)
        self.default_mysqldump_path_edit.setText(settings.default_mysqldump_path)
        self.auto_start_scheduler_checkbox.setChecked(settings.auto_start_scheduler)
        self.run_as_service_checkbox.setChecked(settings.run_as_service)
        self._loaded_service_runner_mode = settings.service_runner_mode

    def set_status(self, message: str) -> None:
        """Show a save result message."""
        self.status_label.setText(message)

    def _emit_save(self) -> None:
        settings = AppSettings(
            default_backup_folder=self.default_backup_folder_edit.text(),
            default_log_folder=self.default_log_folder_edit.text(),
            default_mysqldump_path=self.default_mysqldump_path_edit.text(),
            auto_start_scheduler=self.auto_start_scheduler_checkbox.isChecked(),
            run_as_service=self.run_as_service_checkbox.isChecked(),
            service_runner_mode=self._loaded_service_runner_mode,
        )
        self.save_requested.emit(settings)
