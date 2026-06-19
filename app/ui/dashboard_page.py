"""Dashboard page showing profile status and run controls."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.profile import Profile


class DashboardPage(QWidget):
    """Display all profiles and live backup status output."""

    run_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._profiles_by_row: dict[int, str] = {}

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.summary_label = QLabel("Profiles: 0")
        self.run_button = QPushButton("Run Selected")
        self.refresh_button = QPushButton("Refresh")
        controls.addWidget(self.summary_label)
        controls.addStretch(1)
        controls.addWidget(self.run_button)
        controls.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Enabled", "Last Run", "Last Status", "Last Message"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setPlaceholderText("Backup status output will appear here.")

        layout.addLayout(controls)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Live Output"))
        layout.addWidget(self.status_output)

        self.run_button.clicked.connect(self._emit_run_selected)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)

    def set_profiles(self, profiles: list[Profile]) -> None:
        """Populate the dashboard table."""
        self.table.setRowCount(len(profiles))
        self._profiles_by_row.clear()
        self.summary_label.setText(f"Profiles: {len(profiles)}")

        for row, profile in enumerate(sorted(profiles, key=lambda item: item.name.lower())):
            self._profiles_by_row[row] = profile.id
            values = [
                profile.name,
                profile.type,
                "Yes" if profile.enabled else "No",
                self._format_datetime(profile.last_run_at),
                profile.last_status or "",
                profile.last_message or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {2}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        if profiles:
            self.table.selectRow(0)

    def append_status(self, message: str) -> None:
        """Append a timestamped line to the live output box."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.status_output.appendPlainText(f"[{stamp}] {message}")

    def clear_status(self) -> None:
        """Clear the status panel."""
        self.status_output.clear()

    def set_running(self, running: bool) -> None:
        """Disable the run button while a backup is active."""
        self.run_button.setEnabled(not running)

    def _emit_run_selected(self) -> None:
        row = self.table.currentRow()
        profile_id = self._profiles_by_row.get(row)
        if profile_id:
            self.run_requested.emit(profile_id)

    @staticmethod
    def _format_datetime(value) -> str:
        if not value:
            return ""
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

