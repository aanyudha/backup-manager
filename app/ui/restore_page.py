"""Restore page for MySQL and folder restores."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.restore_result import RestoreResult
from app.models.settings import AppSettings


class RestorePage(QWidget):
    """Collect restore inputs and show restore history."""

    mysql_validate_requested = Signal(object)
    mysql_test_requested = Signal(object)
    mysql_restore_requested = Signal(object)
    folder_validate_requested = Signal(object)
    folder_restore_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        sections = QHBoxLayout()
        sections.addWidget(self._build_mysql_group(), 1)
        sections.addWidget(self._build_folder_group(), 1)
        layout.addLayout(sections)

        layout.addWidget(QLabel("Restore History"))
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Source", "Destination", "Status", "Duration"]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)

        layout.addWidget(QLabel("Status"))
        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setPlaceholderText("Restore validation, progress, and results appear here.")
        layout.addWidget(self.status_output)

    def _build_mysql_group(self) -> QGroupBox:
        group = QGroupBox("MySQL Restore")
        layout = QVBoxLayout(group)
        form = QFormLayout()

        self.mysql_sql_file_edit = QLineEdit()
        self.mysql_database_edit = QLineEdit()
        self.mysql_host_edit = QLineEdit("127.0.0.1")
        self.mysql_port_edit = QLineEdit("3306")
        self.mysql_username_edit = QLineEdit()
        self.mysql_password_edit = QLineEdit()
        self.mysql_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.mysql_path_edit = QLineEdit()
        self.mysql_create_database_checkbox = QCheckBox("Create database if missing")

        form.addRow("SQL File", self.mysql_sql_file_edit)
        form.addRow("Database", self.mysql_database_edit)
        form.addRow("Host", self.mysql_host_edit)
        form.addRow("Port", self.mysql_port_edit)
        form.addRow("Username", self.mysql_username_edit)
        form.addRow("Password", self.mysql_password_edit)
        form.addRow("mysql Path", self.mysql_path_edit)
        form.addRow("", self.mysql_create_database_checkbox)
        layout.addLayout(form)

        buttons = QGridLayout()
        self.mysql_validate_button = QPushButton("Validate")
        self.mysql_test_button = QPushButton("Test Connection")
        self.mysql_restore_button = QPushButton("Run Restore")
        buttons.addWidget(self.mysql_validate_button, 0, 0)
        buttons.addWidget(self.mysql_test_button, 0, 1)
        buttons.addWidget(self.mysql_restore_button, 1, 0, 1, 2)
        layout.addLayout(buttons)

        self.mysql_validate_button.clicked.connect(lambda: self.mysql_validate_requested.emit(self.mysql_restore_payload()))
        self.mysql_test_button.clicked.connect(lambda: self.mysql_test_requested.emit(self.mysql_connection_payload()))
        self.mysql_restore_button.clicked.connect(lambda: self.mysql_restore_requested.emit(self.mysql_restore_payload()))
        return group

    def _build_folder_group(self) -> QGroupBox:
        group = QGroupBox("Folder Restore")
        layout = QVBoxLayout(group)
        form = QFormLayout()

        self.folder_source_edit = QLineEdit()
        self.folder_destination_edit = QLineEdit()
        form.addRow("Backup Source Folder", self.folder_source_edit)
        form.addRow("Restore Destination Folder", self.folder_destination_edit)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.folder_validate_button = QPushButton("Validate")
        self.folder_restore_button = QPushButton("Run Restore")
        buttons.addWidget(self.folder_validate_button)
        buttons.addWidget(self.folder_restore_button)
        layout.addLayout(buttons)

        self.folder_validate_button.clicked.connect(
            lambda: self.folder_validate_requested.emit(self.folder_restore_payload())
        )
        self.folder_restore_button.clicked.connect(
            lambda: self.folder_restore_requested.emit(self.folder_restore_payload())
        )
        return group

    def mysql_connection_payload(self) -> dict[str, object]:
        """Collect MySQL connection inputs."""
        return {
            "host": self.mysql_host_edit.text(),
            "port": self.mysql_port_edit.text() or "3306",
            "username": self.mysql_username_edit.text(),
            "password": self.mysql_password_edit.text(),
        }

    def mysql_restore_payload(self) -> dict[str, object]:
        """Collect MySQL restore inputs."""
        payload = self.mysql_connection_payload()
        payload.update(
            {
                "sql_file": self.mysql_sql_file_edit.text(),
                "database": self.mysql_database_edit.text(),
                "mysql_path": self.mysql_path_edit.text() or None,
                "create_database_if_missing": self.mysql_create_database_checkbox.isChecked(),
            }
        )
        return payload

    def folder_restore_payload(self) -> dict[str, object]:
        """Collect folder restore inputs."""
        return {
            "source": self.folder_source_edit.text(),
            "destination": self.folder_destination_edit.text(),
        }

    def load_settings(self, settings: AppSettings) -> None:
        """Apply settings defaults to restore inputs."""
        if self.mysql_path_edit.text().strip() or not settings.default_mysqldump_path.strip():
            return

        dump_path = Path(settings.default_mysqldump_path.strip())
        candidate_name = "mysql.exe" if dump_path.suffix.lower() == ".exe" else "mysql"
        candidate_path = dump_path.with_name(candidate_name)
        if candidate_path.exists():
            self.mysql_path_edit.setText(str(candidate_path))

    def set_history(self, history: list[RestoreResult]) -> None:
        """Populate the restore history table."""
        self.history_table.setRowCount(len(history))
        for row, result in enumerate(history):
            values = [
                self._format_datetime(result.finished_at),
                result.restore_type,
                result.source,
                result.destination,
                "Success" if result.success else "Failed",
                f"{result.duration_seconds:.2f}s",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(row, column, item)

    def append_status(self, message: str) -> None:
        """Append a timestamped line to the restore status panel."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.status_output.appendPlainText(f"[{stamp}] {message}")

    def clear_status(self) -> None:
        """Clear the restore status panel."""
        self.status_output.clear()

    def show_restore_result(self, result: RestoreResult) -> None:
        """Display a consistent restore result summary in the status panel."""
        self.append_status(self.format_restore_result(result))

    def set_running(self, running: bool) -> None:
        """Disable restore actions while background work is active."""
        for button in [
            self.mysql_validate_button,
            self.mysql_test_button,
            self.mysql_restore_button,
            self.folder_validate_button,
            self.folder_restore_button,
        ]:
            button.setEnabled(not running)

    @staticmethod
    def _format_datetime(value) -> str:
        if not value:
            return ""
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def format_restore_result(result: RestoreResult) -> str:
        """Render restore results with the details operators need after a run."""
        status = "Success" if result.success else "Failed"
        log_file = result.log_file or "N/A"
        return (
            f"Restore finished.\n"
            f"Status: {status}\n"
            f"Duration: {result.duration_seconds:.2f}s\n"
            f"Log file: {log_file}\n"
            f"Message: {result.message}"
        )
