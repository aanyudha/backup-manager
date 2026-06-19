"""Application settings page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.default_backup_folder_edit = QLineEdit()
        self.default_log_folder_edit = QLineEdit()
        self.default_mysqldump_path_edit = QLineEdit()
        self.status_label = QLabel()
        self.save_button = QPushButton("Save Settings")

        form.addRow("Default Backup Folder", self.default_backup_folder_edit)
        form.addRow("Default Log Folder", self.default_log_folder_edit)
        form.addRow("Default mysqldump Path", self.default_mysqldump_path_edit)

        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.save_button.clicked.connect(self._emit_save)

    def load_settings(self, settings: AppSettings) -> None:
        """Populate fields from saved settings."""
        self.default_backup_folder_edit.setText(settings.default_backup_folder)
        self.default_log_folder_edit.setText(settings.default_log_folder)
        self.default_mysqldump_path_edit.setText(settings.default_mysqldump_path)

    def set_status(self, message: str) -> None:
        """Show a save result message."""
        self.status_label.setText(message)

    def _emit_save(self) -> None:
        settings = AppSettings(
            default_backup_folder=self.default_backup_folder_edit.text(),
            default_log_folder=self.default_log_folder_edit.text(),
            default_mysqldump_path=self.default_mysqldump_path_edit.text(),
        )
        self.save_requested.emit(settings)

