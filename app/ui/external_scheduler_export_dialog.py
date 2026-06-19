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
        self.resize(980, 860)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "This export registers an operating system schedule.\n"
            "It does not run the backup immediately.\n\n"
            "The schedule time is copied from the selected profile.\n"
            "If you change the profile schedule later, export again."
        )
        intro.setWordWrap(True)

        register_label = QLabel("A. Register Schedule Command")
        run_now_label = QLabel("B. Run Backup Now Command")

        self.windows_register_output = QPlainTextEdit(export.windows_register_command)
        self.windows_register_output.setReadOnly(True)
        self.windows_run_now_output = QPlainTextEdit(export.windows_run_now_command)
        self.windows_run_now_output.setReadOnly(True)
        self.linux_register_output = QPlainTextEdit(export.linux_register_text)
        self.linux_register_output.setReadOnly(True)
        self.linux_run_now_output = QPlainTextEdit(export.linux_run_now_command)
        self.linux_run_now_output.setReadOnly(True)
        notes_text = "\n".join(f"- {note}" for note in export.warnings)
        self.notes_output = QPlainTextEdit(notes_text)
        self.notes_output.setReadOnly(True)

        button_grid = QGridLayout()
        self.copy_windows_register_button = QPushButton("Copy Windows Register")
        self.copy_windows_run_now_button = QPushButton("Copy Windows Run Now")
        self.copy_linux_register_button = QPushButton("Copy Linux Register")
        self.copy_linux_run_now_button = QPushButton("Copy Linux Run Now")
        self.save_windows_button = QPushButton("Save Windows Files")
        self.save_linux_button = QPushButton("Save Linux Files")
        button_grid.addWidget(self.copy_windows_register_button, 0, 0)
        button_grid.addWidget(self.copy_windows_run_now_button, 0, 1)
        button_grid.addWidget(self.copy_linux_register_button, 1, 0)
        button_grid.addWidget(self.copy_linux_run_now_button, 1, 1)
        button_grid.addWidget(self.save_windows_button, 2, 0)
        button_grid.addWidget(self.save_linux_button, 2, 1)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)

        layout.addWidget(intro)
        layout.addWidget(register_label)
        layout.addWidget(QLabel("Windows Task Scheduler"))
        layout.addWidget(self.windows_register_output)
        layout.addWidget(QLabel("Linux cron"))
        layout.addWidget(self.linux_register_output)
        layout.addWidget(run_now_label)
        layout.addWidget(QLabel("Windows Run Now"))
        layout.addWidget(self.windows_run_now_output)
        layout.addWidget(QLabel("Linux Run Now"))
        layout.addWidget(self.linux_run_now_output)
        layout.addWidget(QLabel("Notes"))
        layout.addWidget(self.notes_output)
        layout.addLayout(button_grid)
        layout.addWidget(close_buttons)

        self.copy_windows_register_button.clicked.connect(
            lambda: self._copy_text(self.windows_register_output.toPlainText())
        )
        self.copy_windows_run_now_button.clicked.connect(
            lambda: self._copy_text(self.windows_run_now_output.toPlainText())
        )
        self.copy_linux_register_button.clicked.connect(
            lambda: self._copy_text(self.linux_register_output.toPlainText())
        )
        self.copy_linux_run_now_button.clicked.connect(
            lambda: self._copy_text(self.linux_run_now_output.toPlainText())
        )

    @staticmethod
    def _copy_text(value: str) -> None:
        """Copy one export value to the clipboard."""
        QApplication.clipboard().setText(value)
