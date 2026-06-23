"""MySQL profile management page."""

from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.models.profile import MySQLBackupProfile, utc_now
from app.services.mysql_service import MySQLService
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.windows_network_share_service import (
    connect_share_diagnostic,
    disconnect_share_diagnostic,
    extract_unc_share_root,
    get_current_windows_user,
    should_connect_to_share,
)
from app.ui.schedule_fields_widget import ScheduleFieldsSection


class MySQLProfilesPage(QWidget):
    """Create and edit MySQL backup profiles."""

    save_requested = Signal(object)
    delete_requested = Signal(str)
    run_requested = Signal(str)

    def __init__(self, mysql_service: MySQLService) -> None:
        super().__init__()
        self.setObjectName("mysqlProfilesPage")
        self.mysql_service = mysql_service
        self.path_validation_service = PathValidationService()
        self.platform_service = PlatformService()
        self._profiles: dict[str, MySQLBackupProfile] = {}
        self._current_id: str | None = None

        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._load_selected_profile)

        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit("3306")
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.mysqldump_path_edit = QLineEdit()
        self.mysqldump_path_edit.setPlaceholderText("Leave blank to auto-detect mysqldump from PATH")
        self.mysqldump_help_label = QLabel("Leave blank to auto-detect mysqldump from PATH.")
        self.mysqldump_help_label.setWordWrap(True)
        self.destination_type_combo = QComboBox()
        self.destination_type_combo.addItem("Local Folder", "local")
        self.destination_type_combo.addItem("Network/Mounted Folder", "network")
        self.destination_edit = QLineEdit()
        self.destination_browse_button = QPushButton("Browse Destination")
        self.destination_helper_label = QLabel(
            "Network/Mounted Folder supports Windows UNC paths, mapped drives, or Linux mounted shares."
        )
        self.destination_helper_label.setWordWrap(True)
        self.destination_network_group = QGroupBox("Windows Network Login")
        destination_network_form = QFormLayout(self.destination_network_group)
        self.destination_network_username_edit = QLineEdit()
        self.destination_network_password_edit = QLineEdit()
        self.destination_network_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.destination_network_domain_edit = QLineEdit()
        self.destination_network_remember_session_checkbox = QCheckBox("Keep SMB session after backup/test")
        self.connect_network_share_button = QPushButton("Connect/Test Network Share")
        self.destination_network_warning_label = QLabel(
            "Windows-only: use a UNC path like \\\\server\\share\\folder. For Task Scheduler or service mode, prefer UNC paths and credentials because mapped drives may not exist in that session."
        )
        self.destination_network_warning_label.setWordWrap(True)
        destination_network_form.addRow("Username", self.destination_network_username_edit)
        destination_network_form.addRow("Password", self.destination_network_password_edit)
        destination_network_form.addRow("Domain", self.destination_network_domain_edit)
        destination_network_form.addRow("", self.destination_network_remember_session_checkbox)
        destination_network_form.addRow("", self.destination_network_warning_label)
        destination_network_form.addRow("", self.connect_network_share_button)
        self.database_mode_combo = QComboBox()
        self.database_mode_combo.addItems(["all", "single", "multiple"])
        self.database_list = QListWidget()
        self.database_list.setObjectName("databaseListWidget")
        self.database_list.setMinimumHeight(180)
        self.database_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(True)
        self.compress_checkbox = QCheckBox("Compress SQL backup as .sql.gz")
        self.retention_checkbox = QCheckBox("Enable Retention")
        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(0, 36500)
        self.retention_days_spin.setValue(0)
        self.retention_days_spin.setEnabled(False)
        self.schedule_fields = ScheduleFieldsSection()

        button_grid = QGridLayout()
        self.test_button = QPushButton("Test Connection")
        self.test_destination_button = QPushButton("Test Destination")
        self.load_databases_button = QPushButton("Load Database List")
        self.save_button = QPushButton("Save Profile")
        self.delete_button = QPushButton("Delete Profile")
        self.run_button = QPushButton("Run Backup")
        self.new_button = QPushButton("New Profile")

        button_grid.addWidget(self.test_button, 0, 0)
        button_grid.addWidget(self.test_destination_button, 0, 1)
        button_grid.addWidget(self.save_button, 0, 2)
        button_grid.addWidget(self.delete_button, 1, 0)
        button_grid.addWidget(self.run_button, 1, 1)
        button_grid.addWidget(self.new_button, 1, 2)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setPlaceholderText("Connection tests and backup messages appear here.")
        self.status_output.setMinimumHeight(100)

        form_panel = QWidget()
        form_panel_layout = QVBoxLayout(form_panel)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        connection_group = QGroupBox("Connection")
        connection_form = QFormLayout(connection_group)
        connection_form.addRow("Profile Name", self.name_edit)
        connection_form.addRow("Host", self.host_edit)
        connection_form.addRow("Port", self.port_edit)
        connection_form.addRow("Username", self.username_edit)
        connection_form.addRow("Password", self.password_edit)

        database_group = QGroupBox("Database Selection")
        database_layout = QVBoxLayout(database_group)
        database_form = QFormLayout()
        database_form.addRow("Database Mode", self.database_mode_combo)
        database_layout.addLayout(database_form)
        database_layout.addWidget(self.load_databases_button)
        database_layout.addWidget(self.database_list)

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_form = QFormLayout()
        output_form.addRow("mysqldump Path", self.mysqldump_path_edit)
        output_form.addRow("", self.mysqldump_help_label)
        output_form.addRow("Destination Type", self.destination_type_combo)
        output_form.addRow(
            "Destination Folder",
            self._build_line_with_button(self.destination_edit, self.destination_browse_button),
        )
        output_form.addRow("", self.destination_helper_label)
        output_form.addRow("", self.destination_network_group)
        output_form.addRow("", self.enabled_checkbox)
        output_form.addRow("", self.compress_checkbox)
        output_form.addRow("", self.retention_checkbox)
        output_form.addRow("Retention Days", self.retention_days_spin)
        output_layout.addLayout(output_form)
        output_layout.addWidget(QLabel("Status"))
        output_layout.addWidget(self.status_output)

        schedule_group = QGroupBox("Schedule")
        schedule_form = QFormLayout(schedule_group)
        self.schedule_fields.add_to_form(schedule_form)

        actions_group = QGroupBox("Actions")
        actions_group.setLayout(button_grid)

        scroll_layout.addWidget(connection_group)
        scroll_layout.addWidget(database_group)
        scroll_layout.addWidget(output_group)
        scroll_layout.addWidget(schedule_group)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        form_panel_layout.addWidget(scroll_area)
        form_panel_layout.addWidget(actions_group)

        splitter.addWidget(self.profile_list)
        splitter.addWidget(form_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 680])
        main_layout.addWidget(splitter)

        self.test_button.clicked.connect(self._test_connection)
        self.test_destination_button.clicked.connect(self._test_destination)
        self.load_databases_button.clicked.connect(self._load_databases)
        self.save_button.clicked.connect(self._save_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        self.run_button.clicked.connect(self._run_profile)
        self.new_button.clicked.connect(self.clear_form)
        self.retention_checkbox.toggled.connect(self.retention_days_spin.setEnabled)
        self.destination_browse_button.clicked.connect(self._browse_destination_folder)
        self.destination_type_combo.currentIndexChanged.connect(self._refresh_destination_network_ui)
        self.connect_network_share_button.clicked.connect(self._test_destination)
        self._refresh_destination_network_ui()

    @staticmethod
    def _build_line_with_button(line_edit: QLineEdit, button: QPushButton) -> QWidget:
        """Render a path field and browse button on one row."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return container

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        """Select a combo-box entry by its stored data value."""
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _current_combo_value(combo: QComboBox) -> str:
        """Return the stored data value for a combo box."""
        value = combo.currentData()
        return value if isinstance(value, str) else combo.currentText()

    def _refresh_destination_network_ui(self, *_args) -> None:
        """Show Windows share login fields only for network destinations."""
        self.destination_network_group.setVisible(self._current_combo_value(self.destination_type_combo) == "network")

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
        self._set_combo_value(self.destination_type_combo, "local")
        self.destination_edit.clear()
        self.destination_network_username_edit.clear()
        self.destination_network_password_edit.clear()
        self.destination_network_domain_edit.clear()
        self.destination_network_remember_session_checkbox.setChecked(False)
        self.database_mode_combo.setCurrentText("all")
        self.database_list.clear()
        self.enabled_checkbox.setChecked(True)
        self.compress_checkbox.setChecked(False)
        self.retention_checkbox.setChecked(False)
        self.retention_days_spin.setValue(0)
        self.retention_days_spin.setEnabled(False)
        self.schedule_fields.clear()
        self.profile_list.clearSelection()
        self._refresh_destination_network_ui()

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
        self._set_combo_value(self.destination_type_combo, profile.destination_type)
        self.destination_edit.setText(profile.destination)
        self.destination_network_username_edit.setText(profile.destination_network_username or "")
        self.destination_network_password_edit.setText(profile.destination_network_password or "")
        self.destination_network_domain_edit.setText(profile.destination_network_domain or "")
        self.destination_network_remember_session_checkbox.setChecked(profile.destination_network_remember_session)
        self.database_mode_combo.setCurrentText(profile.database_mode)
        self.enabled_checkbox.setChecked(profile.enabled)
        self.compress_checkbox.setChecked(profile.compress)
        self.retention_checkbox.setChecked(profile.retention_enabled)
        self.retention_days_spin.setValue(profile.retention_days or 0)
        self.retention_days_spin.setEnabled(profile.retention_enabled)
        self.schedule_fields.load_profile(profile)
        self.restore_saved_database_selection(profile)
        self._refresh_destination_network_ui()

    def populate_database_list(self, databases: list[str], selected_databases: list[str]) -> None:
        """Merge the loaded list with saved selections so edits do not discard choices."""
        self.database_list.clear()
        ordered_selected = [database for database in dict.fromkeys(selected_databases) if database.strip()]
        mode = self.database_mode_combo.currentText()
        if mode == "all":
            ordered_selected = []
        elif mode == "single":
            ordered_selected = ordered_selected[:1]
            if not ordered_selected and databases:
                ordered_selected = [databases[0]]

        seen: set[str] = set()
        for database in databases:
            clean_name = database.strip()
            if not clean_name or clean_name in seen:
                continue
            seen.add(clean_name)
            item = QListWidgetItem(clean_name)
            item.setData(Qt.ItemDataRole.UserRole, clean_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if clean_name in ordered_selected else Qt.CheckState.Unchecked
            )
            self.database_list.addItem(item)

        for database in ordered_selected:
            if database in seen:
                continue
            item = QListWidgetItem(f"{database} (saved, not found)")
            item.setData(Qt.ItemDataRole.UserRole, database)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.database_list.addItem(item)

    def get_selected_databases(self) -> list[str]:
        """Return raw database names from the current selection."""
        selected: list[str] = []
        for index in range(self.database_list.count()):
            item = self.database_list.item(index)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            value = item.data(Qt.ItemDataRole.UserRole) or item.text()
            if isinstance(value, str) and value.strip():
                selected.append(value.strip())
        return selected

    def restore_saved_database_selection(self, profile: MySQLBackupProfile) -> None:
        """Restore database mode and saved selections when a profile is loaded."""
        self.database_mode_combo.setCurrentText(profile.database_mode)
        self.populate_database_list(profile.databases, profile.databases)

    def _collect_form_data(self) -> MySQLBackupProfile:
        selected_databases = self.get_selected_databases()
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
            destination_type=self._current_combo_value(self.destination_type_combo),
            destination=self.destination_edit.text(),
            destination_network_username=self.destination_network_username_edit.text() or None,
            destination_network_password=self.destination_network_password_edit.text() or None,
            destination_network_domain=self.destination_network_domain_edit.text() or None,
            destination_network_remember_session=self.destination_network_remember_session_checkbox.isChecked(),
            compress=self.compress_checkbox.isChecked(),
            enabled=self.enabled_checkbox.isChecked(),
            retention_enabled=self.retention_checkbox.isChecked(),
            retention_days=self.retention_days_spin.value() or None,
            created_at=created_at,
            updated_at=utc_now().astimezone(timezone.utc),
            last_run_at=last_run_at,
            last_status=last_status,
            last_message=last_message,
        )
        self.schedule_fields.apply_to_payload(payload)
        if existing:
            payload["id"] = existing.id
        return MySQLBackupProfile(**payload)

    def _browse_destination_folder(self) -> None:
        """Open a local folder picker for the destination path."""
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder",
            self.destination_edit.text() or "",
        )
        if selected:
            self.destination_edit.setText(selected)

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

    def _test_destination(self) -> None:
        destination = self.destination_edit.text()
        destination_type = self._current_combo_value(self.destination_type_combo)
        should_disconnect_share = should_connect_to_share(
            destination,
            destination_type,
            self.destination_network_username_edit.text(),
            self.destination_network_password_edit.text(),
            platform_service=self.platform_service,
        )
        share_root = ""
        if destination.strip().startswith("\\\\"):
            try:
                share_root = extract_unc_share_root(destination)
            except ValueError:
                share_root = ""
        disconnect_warning: str | None = None
        connect_diagnostic = None
        if should_disconnect_share:
            connect_diagnostic = connect_share_diagnostic(
                destination,
                self.destination_network_username_edit.text(),
                self.destination_network_password_edit.text(),
                self.destination_network_domain_edit.text() or None,
            )
            self.append_status(connect_diagnostic.message)
            if not connect_diagnostic.success:
                QMessageBox.warning(self, "Test Destination", connect_diagnostic.message)
                return
        try:
            valid, message = self.path_validation_service.validate_destination_path(destination, destination_type)
        finally:
            if should_disconnect_share and not self.destination_network_remember_session_checkbox.isChecked():
                disconnect_diagnostic = disconnect_share_diagnostic(destination)
                self.append_status(disconnect_diagnostic.message)
                if not disconnect_diagnostic.success:
                    disconnect_warning = disconnect_diagnostic.message
        if connect_diagnostic and connect_diagnostic.success:
            windows_user = get_current_windows_user()
            share_root_text = connect_diagnostic.share_root or share_root or "(unavailable)"
            message = (
                f"Share Root: {share_root_text}\n"
                f"Current Windows User: {windows_user}\n"
                f"Net Use Result:\n{connect_diagnostic.message}\n\n"
                f"Write Probe Result:\n{message}"
            )
        self.append_status(message)
        if disconnect_warning:
            message = f"{message}\n{disconnect_warning}"
        if valid:
            QMessageBox.information(self, "Test Destination", message)
            return
        QMessageBox.warning(self, "Test Destination", message)

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

        existing = self._profiles.get(self._current_id or "")
        saved_selected = self.get_selected_databases() or (existing.databases if existing else [])
        self.populate_database_list(databases, saved_selected)
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
