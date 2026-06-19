"""Log viewer page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogsPage(QWidget):
    """Browse and open log files from the logs directory."""

    def __init__(self, logs_dir: Path) -> None:
        super().__init__()
        self.logs_dir = logs_dir
        self._paths: dict[int, Path] = {}

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.open_button = QPushButton("Open Selected Log")
        self.open_folder_button = QPushButton("Open Log Folder")
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.open_button)
        controls.addWidget(self.open_folder_button)

        self.log_list = QListWidget()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.log_list.currentItemChanged.connect(self._preview_selected)

        layout.addLayout(controls)
        layout.addWidget(self.log_list)
        layout.addWidget(self.preview)

        self.refresh_button.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_selected_log)
        self.open_folder_button.clicked.connect(self.open_log_folder)

    def refresh(self) -> None:
        """Reload log file list."""
        self.log_list.clear()
        self._paths.clear()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(self.logs_dir.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        for index, path in enumerate(files):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._paths[index] = path
            self.log_list.addItem(item)
        if self.log_list.count():
            self.log_list.setCurrentRow(0)
        else:
            self.preview.clear()

    def open_selected_log(self) -> None:
        """Open the currently selected log file using the OS."""
        item = self.log_list.currentItem()
        if item is None:
            return
        path = self._paths.get(item.data(Qt.ItemDataRole.UserRole))
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_log_folder(self) -> None:
        """Open the logs directory in the OS file browser."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logs_dir)))

    def _preview_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        path = self._paths.get(current.data(Qt.ItemDataRole.UserRole))
        if not path:
            return
        self.preview.setPlainText(path.read_text(encoding="utf-8", errors="replace"))

