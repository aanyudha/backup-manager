"""Dialog for browsing remote FTP or SFTP source folders."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.services.remote_browser_service import RemoteBrowserService


class RemoteFolderBrowserDialog(QDialog):
    """Browse remote folders and return the selected path."""

    def __init__(
        self,
        *,
        protocol: Literal["ftp", "sftp"],
        browser_service: RemoteBrowserService,
        connection: dict[str, object],
        initial_path: str,
    ) -> None:
        super().__init__()
        self.protocol = protocol
        self.browser_service = browser_service
        self.connection = connection
        self.selected_path: str | None = None

        self.setWindowTitle(f"Browse {protocol.upper()} Folder")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.current_path_edit = QLineEdit(initial_path or "/")
        form.addRow("Current Remote Path", self.current_path_edit)
        layout.addLayout(form)

        self.folder_list = QListWidget()
        self.folder_list.itemDoubleClicked.connect(self._open_selected_folder)
        layout.addWidget(QLabel("Folders"))
        layout.addWidget(self.folder_list)

        button_row = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.up_button = QPushButton("Up")
        self.open_button = QPushButton("Open")
        self.select_button = QPushButton("Select This Folder")
        self.cancel_button = QPushButton("Cancel")
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.up_button)
        button_row.addWidget(self.open_button)
        button_row.addStretch(1)
        button_row.addWidget(self.select_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.connect_button.clicked.connect(self._connect_and_list)
        self.up_button.clicked.connect(self._go_up)
        self.open_button.clicked.connect(self._open_selected_folder)
        self.select_button.clicked.connect(self._select_current_folder)
        self.cancel_button.clicked.connect(self.reject)

        self._connect_and_list()

    def _connect_and_list(self, *_args) -> None:
        current_path = self._normalized_current_path()
        try:
            if self.protocol == "ftp":
                entries = self.browser_service.list_ftp_directories(
                    host=str(self.connection["host"]),
                    port=int(self.connection["port"]),
                    username=str(self.connection["username"]),
                    password=str(self.connection["password"]),
                    remote_path=current_path,
                    passive_mode=bool(self.connection.get("passive_mode", True)),
                )
            else:
                entries = self.browser_service.list_sftp_directories(
                    host=str(self.connection["host"]),
                    port=int(self.connection["port"]),
                    username=str(self.connection["username"]),
                    password=self._optional_text(self.connection.get("password")),
                    private_key_path=self._optional_text(self.connection.get("private_key_path")),
                    remote_path=current_path,
                )
        except Exception as exc:
            QMessageBox.warning(self, "Browse Remote Folder", str(exc))
            return

        self.current_path_edit.setText(current_path)
        self.folder_list.clear()
        for entry in entries:
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            self.folder_list.addItem(item)

    def _go_up(self, *_args) -> None:
        current_path = PurePosixPath(self._normalized_current_path())
        parent = current_path.parent if str(current_path) != "/" else current_path
        self.current_path_edit.setText(str(parent) or "/")
        self._connect_and_list()

    def _open_selected_folder(self, *_args) -> None:
        item = self.folder_list.currentItem()
        if item is None:
            return
        selected_path = str(item.data(Qt.ItemDataRole.UserRole))
        self.current_path_edit.setText(selected_path)
        self._connect_and_list()

    def _select_current_folder(self, *_args) -> None:
        item = self.folder_list.currentItem()
        self.selected_path = (
            str(item.data(Qt.ItemDataRole.UserRole))
            if item is not None
            else self._normalized_current_path()
        )
        self.accept()

    def _normalized_current_path(self) -> str:
        cleaned = self.current_path_edit.text().strip() or "/"
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        return str(PurePosixPath(cleaned))

    @staticmethod
    def _optional_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
