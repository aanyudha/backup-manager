"""Dialog for reviewing external scheduler export commands."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.services.external_scheduler_service import ExternalScheduleExport


class ExternalSchedulerExportDialog(QDialog):
    """Display Windows and Linux scheduler exports for manual installation."""

    def __init__(self, profile_name: str, export: ExternalScheduleExport) -> None:
        super().__init__()
        self.export = export
        self.setWindowTitle(f"External Schedule Export: {profile_name}")
        self.resize(900, 680)

        layout = QVBoxLayout(self)
        intro = QLabel("Export only. Review and install manually.")
        intro.setWordWrap(True)

        self.windows_output = QPlainTextEdit(export.windows_command)
        self.windows_output.setReadOnly(True)
        self.linux_output = QPlainTextEdit(export.linux_cron)
        self.linux_output.setReadOnly(True)
        notes_text = "\n".join(f"- {note}" for note in export.warnings)
        self.notes_output = QPlainTextEdit(notes_text)
        self.notes_output.setReadOnly(True)

        button_grid = QGridLayout()
        self.copy_windows_button = QPushButton("Copy Windows Command")
        self.copy_linux_button = QPushButton("Copy Linux Cron")
        self.save_windows_button = QPushButton("Save Windows .cmd")
        self.save_linux_button = QPushButton("Save Linux .cron.txt")
        button_grid.addWidget(self.copy_windows_button, 0, 0)
        button_grid.addWidget(self.copy_linux_button, 0, 1)
        button_grid.addWidget(self.save_windows_button, 1, 0)
        button_grid.addWidget(self.save_linux_button, 1, 1)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)

        layout.addWidget(intro)
        layout.addWidget(QLabel("Windows Task Scheduler Command"))
        layout.addWidget(self.windows_output)
        layout.addWidget(QLabel("Linux cron Line"))
        layout.addWidget(self.linux_output)
        layout.addWidget(QLabel("Notes"))
        layout.addWidget(self.notes_output)
        layout.addLayout(button_grid)
        layout.addWidget(close_buttons)

        self.copy_windows_button.clicked.connect(lambda: self._copy_text(self.windows_output.toPlainText()))
        self.copy_linux_button.clicked.connect(lambda: self._copy_text(self.linux_output.toPlainText()))

    @staticmethod
    def _copy_text(value: str) -> None:
        """Copy one export value to the clipboard."""
        QApplication.clipboard().setText(value)
