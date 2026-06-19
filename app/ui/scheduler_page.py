"""Scheduler overview and controls page."""

from __future__ import annotations

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


class SchedulerPage(QWidget):
    """Display schedule status and basic scheduler controls."""

    refresh_requested = Signal()
    run_due_requested = Signal()
    start_requested = Signal()
    stop_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.summary_label = QLabel("Scheduled Profiles: 0")
        self.refresh_button = QPushButton("Refresh")
        self.run_due_button = QPushButton("Run Due Now")
        self.export_button = QPushButton("Export External Schedule")
        self.start_button = QPushButton("Start Scheduler")
        self.stop_button = QPushButton("Stop Scheduler")

        controls.addWidget(self.summary_label)
        controls.addStretch(1)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.run_due_button)
        controls.addWidget(self.export_button)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Profile Name",
                "Type",
                "Schedule Enabled",
                "Runner",
                "Schedule Summary",
                "Last Run",
                "Next Run",
                "Last Status",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setPlaceholderText("Scheduler activity will appear here.")

        layout.addLayout(controls)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Status"))
        layout.addWidget(self.status_output)

        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.run_due_button.clicked.connect(self.run_due_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.set_scheduler_running(False)

    def set_rows(self, rows: list[dict[str, str]]) -> None:
        """Replace the scheduler table contents."""
        self.table.setRowCount(len(rows))
        self.summary_label.setText(f"Scheduled Profiles: {len(rows)}")

        for row_index, row in enumerate(rows):
            values = [
                row["profile_name"],
                row["type"],
                row["schedule_enabled"],
                row["runner"],
                row["schedule_summary"],
                row["last_run"],
                row["next_run"],
                row["last_status"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["profile_id"])
                self.table.setItem(row_index, column, item)

    def append_status(self, message: str) -> None:
        """Append one scheduler status line."""
        self.status_output.appendPlainText(message)

    def current_profile_id(self) -> str | None:
        """Return the selected scheduler profile id."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def set_scheduler_running(self, running: bool) -> None:
        """Update the start and stop button state."""
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
