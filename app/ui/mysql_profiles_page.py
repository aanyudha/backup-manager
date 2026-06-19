"""MySQL profile management page."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.models.profile import MySQLBackupProfile, utc_now
from app.services.mysql_service import MySQLService


class MySQLProfilesPage(QWidget):
    """Create and edit MySQL backup profiles."""

    save_requested = Signal(object)
    delete_requested = Signal(str)
    run_requested = Signal(str)

    def __init__(self, mysql_service: MySQLService) -> None:
        super().__init__()
        self.mysql_service = mysql_service
        self._profiles: dict[str, MySQLBackupProfile] = {}
        self._current_id: str | None = None

        main_layout = QVBoxLayout(self)
        splitter = QSplitter()

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._load_selected_profile)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit("3306")
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.mysqldump_path_edit = QLineEdit()
        self.destination_edit = QLineEdit()
        self.database_mode_combo = QComboBox()
        self.database_mode_combo.addItems(["all", "single", "multiple"])
        self.database_list = QListWidget()
        self.database_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(True)
        self.compress_checkbox = QCheckBox("Keep compress flag enabled for future gzip support")

        form.addRow("Profile Name", self.name_edit)
        form.addRow("Host", self.host_edit)
        form.addRow("Port", self.port_edit)
        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        form.addRow("mysqldump Path", self.mysqldump_path_edit)
        form.addRow("Destination Folder", self.destination_edit)
        form.addRow("Database Mode", self.database_mode_combo)
        form.addRow("Database List", self.database_list)
        form.addRow("", self.enabled_checkbox)
        form.addRow("", self.compress_checkbox)

        button_grid = QGridLayout()
        self.test_button = QPushButton("Test Connection")
        self.load_databases_button = QPushButton("Load Database List")
        self.save_button = QPushButton("Save Profile")
        self.delete_button = QPushButton("Delete Profile")
        self.run_button = QPushButton("Run Backup")
        self.new_button = QPushButton("New Profile")

        button_grid.addWidget(self.test_button, 0, 0)
        button_grid.addWidget(self.load_databases_button, 0, 1)
        button_grid.addWidget(self.save_button, 1, 0)
        button_grid.addWidget(self.delete_button, 1, 1)
        button_grid.addWidget(self.run_button, 2, 0)
        button_grid.addWidget(self.new_button, 2, 1)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setPlaceholderText("Connection tests and backup messages appear here.")

        form_layout.addLayout(form)
        form_layout.addLayout(button_grid)
        form_layout.addWidget(QLabel("Status"))
        form_layout.addWidget(self.status_output)

        splitter.addWidget(self.profile_list)
        splitter.addWidget(form_container)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        self.test_button.clicked.connect(self._test_connection)
        self.load_databases_button.clicked.connect(self._load_databases)
        self.save_button.clicked.connect(self._save_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        self.run_button.clicked.connect(self._run_profile)
        self.new_button.clicked.connect(self.clear_form)

    def set_profiles(self, profiles: list[MySQLBackupProfile]) -> None:
        """Load profiles into the page list."""
        current_id = self._current_id
        self._profiles = {profile.id: profile for profile in profiles}
        self.profile_list.clear()
        for profile in sorted(profiles, key=lambda item: item.name.lower()):
            item = QListWidgetItem(profile.name)
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            self.profile_list.addItem(item)

        if current_id:
            for index in range(self.profile_list.count()):
                item = self.profile_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) == current_id:
                    self.profile_list.setCurrentItem(item)
                    return
        if self.profile_list.count():
            self.profile_list.setCurrentRow(0)
        else:
            self.clear_form()

    def append_status(self, message: str) -> None:
        """Append a line to the status panel."""
        self.status_output.appendPlainText(message)

    def set_running(self, running: bool) -> None:
        """Disable run actions while a backup is active."""
        self.run_button.setEnabled(not running)

    def clear_form(self) -> None:
        """Reset form to a new profile draft."""
        self._current_id = None
        self.name_edit.clear()
        self.host_edit.clear()
        self.port_edit.setText("3306")
        self.username_edit.clear()
        self.password_edit.clear()
        self.mysqldump_path_edit.clear()
        self.destination_edit.clear()
        self.database_mode_combo.setCurrentText("all")
        self.database_list.clearSelection()
        self.enabled_checkbox.setChecked(True)
        self.compress_checkbox.setChecked(False)
        self.profile_list.clearSelection()

    def _load_selected_profile(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = self._profiles.get(profile_id)
        if not profile:
            return

        self._current_id = profile.id
        self.name_edit.setText(profile.name)
        self.host_edit.setText(profile.host)
        self.port_edit.setText(str(profile.port))
        self.username_edit.setText(profile.username)
        self.password_edit.setText(profile.password)
        self.mysqldump_path_edit.setText(profile.mysqldump_path or "")
        self.destination_edit.setText(profile.destination)
        self.database_mode_combo.setCurrentText(profile.database_mode)
        self.enabled_checkbox.setChecked(profile.enabled)
        self.compress_checkbox.setChecked(profile.compress)
        self._set_database_items(profile.databases, selected=profile.databases)

    def _set_database_items(self, items: list[str], selected: list[str] | None = None) -> None:
        self.database_list.clear()
        selected_values = set(selected or [])
        for database in items:
            item = QListWidgetItem(database)
            item.setSelected(database in selected_values)
            self.database_list.addItem(item)

    def _collect_form_data(self) -> MySQLBackupProfile:
        selected_databases = [item.text() for item in self.database_list.selectedItems()]
        existing = self._profiles.get(self._current_id or "")
        created_at = existing.created_at if existing else utc_now()
        last_run_at = existing.last_run_at if existing else None
        last_status = existing.last_status if existing else None
        last_message = existing.last_message if existing else None
        payload = dict(
            name=self.name_edit.text(),
            host=self.host_edit.text(),
            port=int(self.port_edit.text() or "3306"),
            username=self.username_edit.text(),
            password=self.password_edit.text(),
            database_mode=self.database_mode_combo.currentText(),
            databases=selected_databases,
            mysqldump_path=self.mysqldump_path_edit.text() or None,
            destination=self.destination_edit.text(),
            compress=self.compress_checkbox.isChecked(),
            enabled=self.enabled_checkbox.isChecked(),
            created_at=created_at,
            updated_at=utc_now().astimezone(timezone.utc),
            last_run_at=last_run_at,
            last_status=last_status,
            last_message=last_message,
        )
        if existing:
            payload["id"] = existing.id
        return MySQLBackupProfile(**payload)

    def _test_connection(self) -> None:
        success, message = self.mysql_service.test_connection(
            host=self.host_edit.text(),
            port=int(self.port_edit.text() or "3306"),
            username=self.username_edit.text(),
            password=self.password_edit.text(),
        )
        self.append_status(message)
        if not success:
            QMessageBox.warning(self, "MySQL Connection", message)

    def _load_databases(self) -> None:
        try:
            databases = list(
                self.mysql_service.list_databases(
                    host=self.host_edit.text(),
                    port=int(self.port_edit.text() or "3306"),
                    username=self.username_edit.text(),
                    password=self.password_edit.text(),
                )
            )
        except Exception as exc:
            self.append_status(str(exc))
            QMessageBox.warning(self, "Load Database List", str(exc))
            return

        self._set_database_items(databases, selected=databases[:1] if self.database_mode_combo.currentText() == "single" else [])
        self.append_status(f"Loaded {len(databases)} database(s).")

    def _save_profile(self) -> None:
        try:
            profile = self._collect_form_data()
        except Exception as exc:
            QMessageBox.warning(self, "Save Profile", str(exc))
            return
        self.save_requested.emit(profile)
        self._current_id = profile.id

    def _delete_profile(self) -> None:
        if self._current_id:
            self.delete_requested.emit(self._current_id)

    def _run_profile(self) -> None:
        if self._current_id:
            self.run_requested.emit(self._current_id)
        else:
            QMessageBox.information(self, "Run Backup", "Save the profile before running it.")
