"""Folder profile management page."""

from __future__ import annotations

import shlex
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
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.engines.folder_backup_engine import FolderBackupEngine
from app.models.profile import FolderBackupProfile, utc_now
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.remote_browser_service import RemoteBrowserService
from app.ui.remote_folder_browser_dialog import RemoteFolderBrowserDialog
from app.ui.schedule_fields_widget import ScheduleFieldsSection


class FolderProfilesPage(QWidget):
    """Create and edit folder backup profiles."""

    save_requested = Signal(object)
    delete_requested = Signal(str)
    run_requested = Signal(str)

    def __init__(
        self,
        platform_service: PlatformService,
        remote_browser_service: RemoteBrowserService,
    ) -> None:
        super().__init__()
        self.setObjectName("folderProfilesPage")
        self.platform_service = platform_service
        self.remote_browser_service = remote_browser_service
        self.path_validation_service = PathValidationService()
        self._profiles: dict[str, FolderBackupProfile] = {}
        self._current_id: str | None = None

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._load_selected_profile)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        self.name_edit = QLineEdit()
        self.source_type_combo = QComboBox()
        self._add_choice(self.source_type_combo, "Local Folder", "local")
        self._add_choice(self.source_type_combo, "FTP Remote Folder", "ftp")
        self._add_choice(self.source_type_combo, "SFTP Remote Folder", "sftp")
        self._add_choice(self.source_type_combo, "Rsync Remote/Path", "rsync")
        self.destination_type_combo = QComboBox()
        self._add_choice(self.destination_type_combo, "Local Folder", "local")
        self._add_choice(self.destination_type_combo, "Network/Mounted Folder", "network")
        self.source_edit = QLineEdit()
        self.source_browse_button = QPushButton("Browse Source")
        self.source_path_label = QLabel("Source Folder")
        self.source_path_row = self._build_line_with_button(self.source_edit, self.source_browse_button)
        self.source_helper_label = QLabel()
        self.source_helper_label.setWordWrap(True)
        self.destination_edit = QLineEdit()
        self.destination_browse_button = QPushButton("Browse Destination")
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["auto", "local_copy", "robocopy", "rsync", "sftp", "ftp"])
        self.resolved_engine_value = QLabel("local_copy")
        self.engine_helper_label = QLabel(
            "Engine auto chooses the correct transport based on Source Type and path settings."
        )
        self.engine_helper_label.setWordWrap(True)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["copy_new_changed", "sync_without_delete", "mirror_with_delete"])
        self.log_folder_edit = QLineEdit()

        self.sftp_host_edit = QLineEdit()
        self.sftp_port_edit = QLineEdit("22")
        self.sftp_username_edit = QLineEdit()
        self.sftp_password_edit = QLineEdit()
        self.sftp_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.sftp_private_key_edit = QLineEdit()
        self.sftp_remote_path_edit = QLineEdit()
        self.sftp_browse_button = QPushButton("Browse SFTP Folder")

        self.ftp_host_edit = QLineEdit()
        self.ftp_port_edit = QLineEdit("21")
        self.ftp_username_edit = QLineEdit()
        self.ftp_password_edit = QLineEdit()
        self.ftp_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ftp_remote_path_edit = QLineEdit()
        self.ftp_browse_button = QPushButton("Browse FTP Folder")
        self.ftp_passive_checkbox = QCheckBox("Use Passive Mode")
        self.ftp_passive_checkbox.setChecked(True)

        self.destination_helper_label = QLabel(
            "Network/Mounted Folder does not store credentials. Mount or login must be handled by the OS."
        )
        self.destination_helper_label.setWordWrap(True)
        self.destination_limitation_label = QLabel(
            "FTP/SFTP destination upload is not supported yet. Remote sources are copied to Local or Network/Mounted destinations."
        )
        self.destination_limitation_label.setWordWrap(True)
        self.rsync_args_edit = QLineEdit()
        self.enabled_checkbox = QCheckBox("Enabled")
        self.enabled_checkbox.setChecked(True)
        self.retention_checkbox = QCheckBox("Enable Retention")
        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(0, 36500)
        self.retention_days_spin.setValue(0)
        self.retention_days_spin.setEnabled(False)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.schedule_fields = ScheduleFieldsSection()

        transfer_group = QGroupBox("Transfer Direction")
        transfer_form = QFormLayout(transfer_group)
        transfer_form.addRow("Profile Name", self.name_edit)
        transfer_form.addRow("Source Type", self.source_type_combo)
        transfer_form.addRow("Engine", self.engine_combo)
        transfer_form.addRow("Resolved Engine", self.resolved_engine_value)
        transfer_form.addRow("", self.engine_helper_label)
        transfer_form.addRow("Mode", self.mode_combo)
        transfer_form.addRow("Log Folder", self.log_folder_edit)

        self.source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(self.source_group)
        source_layout.addWidget(self.source_helper_label)
        self.source_path_group = QGroupBox("Local Source")
        source_path_form = QFormLayout(self.source_path_group)
        source_path_form.addRow(self.source_path_label, self.source_path_row)
        self.sftp_source_group = QGroupBox("SFTP Source")
        sftp_form = QFormLayout(self.sftp_source_group)
        sftp_form.addRow("SFTP Host", self.sftp_host_edit)
        sftp_form.addRow("SFTP Port", self.sftp_port_edit)
        sftp_form.addRow("SFTP Username", self.sftp_username_edit)
        sftp_form.addRow("SFTP Password", self.sftp_password_edit)
        sftp_form.addRow("SFTP Private Key", self.sftp_private_key_edit)
        sftp_form.addRow(
            "SFTP Source Folder",
            self._build_line_with_button(self.sftp_remote_path_edit, self.sftp_browse_button),
        )
        self.ftp_source_group = QGroupBox("FTP Source")
        ftp_form = QFormLayout(self.ftp_source_group)
        ftp_form.addRow("FTP Host", self.ftp_host_edit)
        ftp_form.addRow("FTP Port", self.ftp_port_edit)
        ftp_form.addRow("FTP Username", self.ftp_username_edit)
        ftp_form.addRow("FTP Password", self.ftp_password_edit)
        ftp_form.addRow(
            "FTP Source Folder",
            self._build_line_with_button(self.ftp_remote_path_edit, self.ftp_browse_button),
        )
        ftp_form.addRow("", self.ftp_passive_checkbox)
        source_layout.addWidget(self.source_path_group)
        source_layout.addWidget(self.ftp_source_group)
        source_layout.addWidget(self.sftp_source_group)

        destination_group = QGroupBox("Destination")
        destination_form = QFormLayout(destination_group)
        destination_form.addRow("Destination Type", self.destination_type_combo)
        destination_form.addRow(
            "Destination Folder",
            self._build_line_with_button(self.destination_edit, self.destination_browse_button),
        )
        destination_form.addRow("", self.destination_helper_label)
        destination_form.addRow("", self.destination_limitation_label)

        options_group = QGroupBox("Options")
        options_form = QFormLayout(options_group)
        options_form.addRow("Rsync Extra Args", self.rsync_args_edit)
        options_form.addRow("", self.enabled_checkbox)
        options_form.addRow("", self.retention_checkbox)
        options_form.addRow("Retention Days", self.retention_days_spin)
        self.schedule_fields.add_to_form(options_form)
        options_form.addRow("Compatibility", self.warning_label)

        button_grid = QGridLayout()
        self.validate_button = QPushButton("Validate")
        self.test_destination_button = QPushButton("Test Destination")
        self.save_button = QPushButton("Save Profile")
        self.delete_button = QPushButton("Delete Profile")
        self.run_button = QPushButton("Run Backup")
        self.new_button = QPushButton("New Profile")
        button_grid.addWidget(self.validate_button, 0, 0)
        button_grid.addWidget(self.test_destination_button, 0, 1)
        button_grid.addWidget(self.save_button, 0, 2)
        button_grid.addWidget(self.delete_button, 1, 0)
        button_grid.addWidget(self.run_button, 1, 1)
        button_grid.addWidget(self.new_button, 1, 2)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setMinimumHeight(100)

        scroll_layout.addWidget(transfer_group)
        scroll_layout.addWidget(self.source_group)
        scroll_layout.addWidget(destination_group)
        scroll_layout.addWidget(options_group)
        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        form_layout.addWidget(scroll_area)
        form_layout.addLayout(button_grid)
        form_layout.addWidget(QLabel("Status"))
        form_layout.addWidget(self.status_output)

        splitter.addWidget(self.profile_list)
        splitter.addWidget(form_container)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 680])
        layout.addWidget(splitter)

        self.validate_button.clicked.connect(self._validate_profile)
        self.test_destination_button.clicked.connect(self._test_destination)
        self.save_button.clicked.connect(self._save_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        self.run_button.clicked.connect(self._run_profile)
        self.new_button.clicked.connect(self.clear_form)
        self.engine_combo.currentTextChanged.connect(self._refresh_warning)
        self.engine_combo.currentTextChanged.connect(self._refresh_resolved_engine)
        self.mode_combo.currentTextChanged.connect(self._refresh_warning)
        self.source_type_combo.currentIndexChanged.connect(self._refresh_source_ui)
        self.source_type_combo.currentIndexChanged.connect(self._refresh_warning)
        self.source_type_combo.currentIndexChanged.connect(self._refresh_resolved_engine)
        self.destination_type_combo.currentIndexChanged.connect(self._refresh_warning)
        self.destination_type_combo.currentIndexChanged.connect(self._refresh_resolved_engine)
        self.retention_checkbox.toggled.connect(self.retention_days_spin.setEnabled)
        self.source_browse_button.clicked.connect(self._browse_source_folder)
        self.destination_browse_button.clicked.connect(self._browse_destination_folder)
        self.ftp_browse_button.clicked.connect(self._browse_ftp_folder)
        self.sftp_browse_button.clicked.connect(self._browse_sftp_folder)
        for widget in (
            self.source_edit,
            self.destination_edit,
            self.sftp_host_edit,
            self.sftp_remote_path_edit,
            self.ftp_host_edit,
            self.ftp_remote_path_edit,
        ):
            widget.textChanged.connect(self._refresh_resolved_engine)
            widget.textChanged.connect(self._refresh_warning)
        self._refresh_source_ui()
        self._refresh_warning()
        self._refresh_resolved_engine()

    @staticmethod
    def _add_choice(combo: QComboBox, label: str, value: str) -> None:
        """Insert a combo-box option with a stable data value."""
        combo.addItem(label, value)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        """Select a combo-box entry by its user data."""
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _current_combo_value(combo: QComboBox) -> str:
        """Return the stable data value for a combo-box."""
        value = combo.currentData()
        return value if isinstance(value, str) else combo.currentText()

    @staticmethod
    def _build_line_with_button(line_edit: QLineEdit, button: QPushButton) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return container

    def _current_source_type(self) -> str:
        return self._current_combo_value(self.source_type_combo)

    def _current_destination_type(self) -> str:
        return self._current_combo_value(self.destination_type_combo)

    def set_profiles(self, profiles: list[FolderBackupProfile]) -> None:
        """Load folder profiles into the list."""
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
        self.status_output.appendPlainText(message)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)

    def clear_form(self) -> None:
        self._current_id = None
        self.name_edit.clear()
        self._set_combo_value(self.source_type_combo, "local")
        self._set_combo_value(self.destination_type_combo, "local")
        self.source_edit.clear()
        self.destination_edit.clear()
        self.engine_combo.setCurrentText("auto")
        self.mode_combo.setCurrentText("copy_new_changed")
        self.log_folder_edit.clear()
        self.sftp_host_edit.clear()
        self.sftp_port_edit.setText("22")
        self.sftp_username_edit.clear()
        self.sftp_password_edit.clear()
        self.sftp_private_key_edit.clear()
        self.sftp_remote_path_edit.clear()
        self.ftp_host_edit.clear()
        self.ftp_port_edit.setText("21")
        self.ftp_username_edit.clear()
        self.ftp_password_edit.clear()
        self.ftp_remote_path_edit.clear()
        self.ftp_passive_checkbox.setChecked(True)
        self.rsync_args_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.retention_checkbox.setChecked(False)
        self.retention_days_spin.setValue(0)
        self.retention_days_spin.setEnabled(False)
        self.schedule_fields.clear()
        self.profile_list.clearSelection()
        self._refresh_source_ui()
        self._refresh_warning()
        self._refresh_resolved_engine()

    def _load_selected_profile(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = self._profiles.get(profile_id)
        if not profile:
            return

        self._current_id = profile.id
        self.name_edit.setText(profile.name)
        self._set_combo_value(self.source_type_combo, profile.source_type)
        self._set_combo_value(self.destination_type_combo, profile.destination_type)
        self.source_edit.setText(profile.source)
        self.destination_edit.setText(profile.destination)
        self.engine_combo.setCurrentText(profile.engine)
        self.mode_combo.setCurrentText(profile.mode)
        self.log_folder_edit.setText(profile.log_folder or "")
        self.sftp_host_edit.setText(profile.sftp_host or "")
        self.sftp_port_edit.setText(str(profile.sftp_port or 22))
        self.sftp_username_edit.setText(profile.sftp_username or "")
        self.sftp_password_edit.setText(profile.sftp_password or "")
        self.sftp_private_key_edit.setText(profile.sftp_private_key or "")
        self.sftp_remote_path_edit.setText(profile.sftp_remote_path or "")
        self.ftp_host_edit.setText(profile.ftp_host or "")
        self.ftp_port_edit.setText(str(profile.ftp_port or 21))
        self.ftp_username_edit.setText(profile.ftp_username or "")
        self.ftp_password_edit.setText(profile.ftp_password or "")
        self.ftp_remote_path_edit.setText(profile.ftp_remote_path or "")
        self.ftp_passive_checkbox.setChecked(profile.ftp_passive)
        self.rsync_args_edit.setText(" ".join(profile.rsync_extra_args))
        self.enabled_checkbox.setChecked(profile.enabled)
        self.retention_checkbox.setChecked(profile.retention_enabled)
        self.retention_days_spin.setValue(profile.retention_days or 0)
        self.retention_days_spin.setEnabled(profile.retention_enabled)
        self.schedule_fields.load_profile(profile)
        self._refresh_source_ui()
        self._refresh_warning()
        self._refresh_resolved_engine()

    def _collect_form_data(self) -> FolderBackupProfile:
        existing = self._profiles.get(self._current_id or "")
        created_at = existing.created_at if existing else utc_now()
        last_run_at = existing.last_run_at if existing else None
        last_status = existing.last_status if existing else None
        last_message = existing.last_message if existing else None
        payload = dict(
            name=self.name_edit.text(),
            source_type=self._current_source_type(),
            destination_type=self._current_destination_type(),
            source=self.source_edit.text(),
            destination=self.destination_edit.text(),
            engine=self.engine_combo.currentText(),
            mode=self.mode_combo.currentText(),
            log_folder=self.log_folder_edit.text() or None,
            sftp_host=self.sftp_host_edit.text() or None,
            sftp_port=int(self.sftp_port_edit.text() or "22"),
            sftp_username=self.sftp_username_edit.text() or None,
            sftp_password=self.sftp_password_edit.text() or None,
            sftp_private_key=self.sftp_private_key_edit.text() or None,
            sftp_remote_path=self.sftp_remote_path_edit.text() or None,
            ftp_host=self.ftp_host_edit.text() or None,
            ftp_port=int(self.ftp_port_edit.text() or "21"),
            ftp_username=self.ftp_username_edit.text() or None,
            ftp_password=self.ftp_password_edit.text() or None,
            ftp_remote_path=self.ftp_remote_path_edit.text() or None,
            ftp_passive=self.ftp_passive_checkbox.isChecked(),
            rsync_extra_args=shlex.split(self.rsync_args_edit.text()) if self.rsync_args_edit.text().strip() else [],
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
        return FolderBackupProfile(**payload)

    def _refresh_source_ui(self, *_args) -> None:
        source_type = self._current_source_type()
        self.source_path_group.setVisible(source_type in {"local", "rsync"})
        self.ftp_source_group.setVisible(source_type == "ftp")
        self.sftp_source_group.setVisible(source_type == "sftp")
        self.source_browse_button.setVisible(source_type == "local")
        if source_type == "local":
            self.source_path_group.setTitle("Local Source")
            self.source_path_label.setText("Source Folder")
            self.source_helper_label.setText("Local source uses the Source Folder path.")
        elif source_type == "ftp":
            self.source_helper_label.setText(
                "FTP Source Folder is copied from the FTP server to the destination."
            )
        elif source_type == "sftp":
            self.source_helper_label.setText(
                "SFTP Source Folder is copied from the SFTP server to the destination."
            )
        else:
            self.source_path_group.setTitle("Rsync Source")
            self.source_path_label.setText("Source Path")
            self.source_helper_label.setText(
                "Use local path or remote syntax, for example user@host:/path"
            )

    def _refresh_warning(self, *_args) -> None:
        warnings = self.platform_service.compatibility_warnings()
        engine = self.engine_combo.currentText()
        source_type = self._current_source_type()
        effective_engine = FolderBackupEngine.resolve_engine_inputs(
            platform_service=self.platform_service,
            requested_engine=engine,
            source_type=source_type,
            destination_type=self._current_destination_type(),
            source=self.source_edit.text(),
            destination=self.destination_edit.text(),
            sftp_host=self.sftp_host_edit.text() or None,
            sftp_remote_path=self.sftp_remote_path_edit.text() or None,
            ftp_host=self.ftp_host_edit.text() or None,
            ftp_remote_path=self.ftp_remote_path_edit.text() or None,
        )
        if self.engine_combo.currentText() == "auto" and self._has_sftp_configuration() and self._has_ftp_configuration():
            warnings.append(
                "Both SFTP and FTP settings are filled. Auto selected SFTP. Clear unused settings to avoid confusion."
            )
        if source_type == "ftp" and engine not in {"auto", "ftp"}:
            warnings.append("FTP source requires Engine auto or ftp.")
        if source_type == "sftp" and engine not in {"auto", "sftp"}:
            warnings.append("SFTP source requires Engine auto or sftp.")
        if source_type == "rsync" and engine not in {"auto", "rsync"}:
            warnings.append("Rsync source requires Engine auto or rsync.")
        if source_type == "local" and engine in {"ftp", "sftp"}:
            warnings.append("FTP/SFTP engine requires remote source type.")
        if engine == "robocopy" and not self.platform_service.is_windows():
            warnings.append("Selected engine is not compatible with this OS.")
        if effective_engine == "sftp" and self.mode_combo.currentText() == "mirror_with_delete":
            warnings.append("SFTP mirror_with_delete is unsupported in the MVP.")
        if effective_engine == "ftp" and self.mode_combo.currentText() == "mirror_with_delete":
            warnings.append("FTP mirror_with_delete is unsupported in the MVP.")
        self.warning_label.setText(" | ".join(warnings) if warnings else "No compatibility warnings.")

    def _refresh_resolved_engine(self, *_args) -> None:
        resolved = FolderBackupEngine.resolve_engine_inputs(
            platform_service=self.platform_service,
            requested_engine=self.engine_combo.currentText(),
            source_type=self._current_source_type(),
            destination_type=self._current_destination_type(),
            source=self.source_edit.text(),
            destination=self.destination_edit.text(),
            sftp_host=self.sftp_host_edit.text() or None,
            sftp_remote_path=self.sftp_remote_path_edit.text() or None,
            ftp_host=self.ftp_host_edit.text() or None,
            ftp_remote_path=self.ftp_remote_path_edit.text() or None,
        )
        self.resolved_engine_value.setText(resolved)

    def _has_sftp_configuration(self) -> bool:
        return bool(self.sftp_host_edit.text().strip() or self.sftp_remote_path_edit.text().strip())

    def _has_ftp_configuration(self) -> bool:
        return bool(self.ftp_host_edit.text().strip() or self.ftp_remote_path_edit.text().strip())

    def _validate_profile(self) -> None:
        try:
            profile = self._collect_form_data()
        except Exception as exc:
            self.append_status(str(exc))
            QMessageBox.warning(self, "Validate Profile", str(exc))
            return
        self._refresh_resolved_engine()
        if profile.engine == "auto":
            message = (
                f"Profile validation passed. Auto detected transport: "
                f"{self.resolved_engine_value.text()}"
            )
        else:
            message = "Profile validation passed."
        self.append_status(message)
        QMessageBox.information(self, "Validate Profile", message)

    def _test_destination(self) -> None:
        valid, message = self.path_validation_service.validate_destination_path(
            self.destination_edit.text(),
            self._current_destination_type(),
        )
        if valid:
            success_message = f"Destination validation passed: {self.destination_edit.text().strip()}"
            self.append_status(success_message)
            QMessageBox.information(self, "Test Destination", success_message)
            return
        self.append_status(message)
        QMessageBox.warning(self, "Test Destination", message)

    def _browse_source_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select Source Folder", self.source_edit.text() or "")
        if selected:
            self._set_combo_value(self.source_type_combo, "local")
            self.source_edit.setText(selected)

    def _browse_destination_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder",
            self.destination_edit.text() or "",
        )
        if selected:
            self.destination_edit.setText(selected)

    def _browse_ftp_folder(self, *_args) -> None:
        if (
            not self.ftp_host_edit.text().strip()
            or not self.ftp_username_edit.text().strip()
            or not self.ftp_password_edit.text()
        ):
            message = "Fill FTP connection fields before browsing."
            self.append_status(message)
            QMessageBox.warning(self, "Browse FTP Folder", message)
            return
        dialog = RemoteFolderBrowserDialog(
            protocol="ftp",
            browser_service=self.remote_browser_service,
            connection={
                "host": self.ftp_host_edit.text(),
                "port": int(self.ftp_port_edit.text() or "21"),
                "username": self.ftp_username_edit.text(),
                "password": self.ftp_password_edit.text(),
                "passive_mode": self.ftp_passive_checkbox.isChecked(),
            },
            initial_path=self.ftp_remote_path_edit.text() or "/",
        )
        if dialog.exec() and dialog.selected_path:
            self._apply_ftp_remote_path(dialog.selected_path)

    def _browse_sftp_folder(self, *_args) -> None:
        if (
            not self.sftp_host_edit.text().strip()
            or not self.sftp_username_edit.text().strip()
            or (not self.sftp_password_edit.text() and not self.sftp_private_key_edit.text().strip())
        ):
            message = "Fill SFTP connection fields before browsing."
            self.append_status(message)
            QMessageBox.warning(self, "Browse SFTP Folder", message)
            return
        dialog = RemoteFolderBrowserDialog(
            protocol="sftp",
            browser_service=self.remote_browser_service,
            connection={
                "host": self.sftp_host_edit.text(),
                "port": int(self.sftp_port_edit.text() or "22"),
                "username": self.sftp_username_edit.text(),
                "password": self.sftp_password_edit.text() or None,
                "private_key_path": self.sftp_private_key_edit.text() or None,
            },
            initial_path=self.sftp_remote_path_edit.text() or "/",
        )
        if dialog.exec() and dialog.selected_path:
            self._apply_sftp_remote_path(dialog.selected_path)

    def _apply_ftp_remote_path(self, remote_path: str) -> None:
        self._set_combo_value(self.source_type_combo, "ftp")
        self.ftp_remote_path_edit.setText(remote_path)
        if self.engine_combo.currentText() not in {"auto", "ftp"}:
            message = "You selected an FTP remote folder, but Engine is not auto or ftp."
            self.append_status(message)
            QMessageBox.warning(self, "Browse FTP Folder", message)

    def _apply_sftp_remote_path(self, remote_path: str) -> None:
        self._set_combo_value(self.source_type_combo, "sftp")
        self.sftp_remote_path_edit.setText(remote_path)
        if self.engine_combo.currentText() not in {"auto", "sftp"}:
            message = "You selected an SFTP remote folder, but Engine is not auto or sftp."
            self.append_status(message)
            QMessageBox.warning(self, "Browse SFTP Folder", message)

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
