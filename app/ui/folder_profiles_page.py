"""Folder profile management page."""

from __future__ import annotations

import shlex
from datetime import timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.models.profile import FolderBackupProfile, utc_now
from app.services.platform_service import PlatformService
from app.ui.schedule_fields_widget import ScheduleFieldsSection


class FolderProfilesPage(QWidget):
    """Create and edit folder backup profiles."""

    save_requested = Signal(object)
    delete_requested = Signal(str)
    run_requested = Signal(str)

    def __init__(self, platform_service: PlatformService) -> None:
        super().__init__()
        self.platform_service = platform_service
        self._profiles: dict[str, FolderBackupProfile] = {}
        self._current_id: str | None = None

        layout = QVBoxLayout(self)
        splitter = QSplitter()

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._load_selected_profile)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.source_edit = QLineEdit()
        self.destination_edit = QLineEdit()
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["auto", "local_copy", "robocopy", "rsync", "sftp"])
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

        form.addRow("Profile Name", self.name_edit)
        form.addRow("Source", self.source_edit)
        form.addRow("Destination", self.destination_edit)
        form.addRow("Engine", self.engine_combo)
        form.addRow("Mode", self.mode_combo)
        form.addRow("Log Folder", self.log_folder_edit)
        form.addRow("SFTP Host", self.sftp_host_edit)
        form.addRow("SFTP Port", self.sftp_port_edit)
        form.addRow("SFTP Username", self.sftp_username_edit)
        form.addRow("SFTP Password", self.sftp_password_edit)
        form.addRow("SFTP Private Key", self.sftp_private_key_edit)
        form.addRow("SFTP Remote Path", self.sftp_remote_path_edit)
        form.addRow("Rsync Extra Args", self.rsync_args_edit)
        form.addRow("", self.enabled_checkbox)
        form.addRow("", self.retention_checkbox)
        form.addRow("Retention Days", self.retention_days_spin)
        self.schedule_fields.add_to_form(form)
        form.addRow("Compatibility", self.warning_label)

        button_grid = QGridLayout()
        self.validate_button = QPushButton("Validate")
        self.save_button = QPushButton("Save Profile")
        self.delete_button = QPushButton("Delete Profile")
        self.run_button = QPushButton("Run Backup")
        self.new_button = QPushButton("New Profile")
        button_grid.addWidget(self.validate_button, 0, 0)
        button_grid.addWidget(self.save_button, 0, 1)
        button_grid.addWidget(self.delete_button, 1, 0)
        button_grid.addWidget(self.run_button, 1, 1)
        button_grid.addWidget(self.new_button, 2, 0, 1, 2)

        self.status_output = QPlainTextEdit()
        self.status_output.setReadOnly(True)

        form_layout.addLayout(form)
        form_layout.addLayout(button_grid)
        form_layout.addWidget(QLabel("Status"))
        form_layout.addWidget(self.status_output)

        splitter.addWidget(self.profile_list)
        splitter.addWidget(form_container)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.validate_button.clicked.connect(self._validate_profile)
        self.save_button.clicked.connect(self._save_profile)
        self.delete_button.clicked.connect(self._delete_profile)
        self.run_button.clicked.connect(self._run_profile)
        self.new_button.clicked.connect(self.clear_form)
        self.engine_combo.currentTextChanged.connect(self._refresh_warning)
        self.retention_checkbox.toggled.connect(self.retention_days_spin.setEnabled)
        self._refresh_warning()

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
        self.rsync_args_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.retention_checkbox.setChecked(False)
        self.retention_days_spin.setValue(0)
        self.retention_days_spin.setEnabled(False)
        self.schedule_fields.clear()
        self.profile_list.clearSelection()
        self._refresh_warning()

    def _load_selected_profile(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        profile_id = current.data(Qt.ItemDataRole.UserRole)
        profile = self._profiles.get(profile_id)
        if not profile:
            return

        self._current_id = profile.id
        self.name_edit.setText(profile.name)
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
        self.rsync_args_edit.setText(" ".join(profile.rsync_extra_args))
        self.enabled_checkbox.setChecked(profile.enabled)
        self.retention_checkbox.setChecked(profile.retention_enabled)
        self.retention_days_spin.setValue(profile.retention_days or 0)
        self.retention_days_spin.setEnabled(profile.retention_enabled)
        self.schedule_fields.load_profile(profile)
        self._refresh_warning()

    def _collect_form_data(self) -> FolderBackupProfile:
        existing = self._profiles.get(self._current_id or "")
        created_at = existing.created_at if existing else utc_now()
        last_run_at = existing.last_run_at if existing else None
        last_status = existing.last_status if existing else None
        last_message = existing.last_message if existing else None
        payload = dict(
            name=self.name_edit.text(),
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

    def _refresh_warning(self) -> None:
        warnings = self.platform_service.compatibility_warnings()
        engine = self.engine_combo.currentText()
        if engine == "robocopy" and not self.platform_service.is_windows():
            warnings.append("Selected engine is not compatible with this OS.")
        if engine == "sftp" and self.mode_combo.currentText() == "mirror_with_delete":
            warnings.append("SFTP mirror_with_delete is unsupported in the MVP.")
        self.warning_label.setText(" | ".join(warnings) if warnings else "No compatibility warnings.")

    def _validate_profile(self) -> None:
        try:
            self._collect_form_data()
        except Exception as exc:
            self.append_status(str(exc))
            QMessageBox.warning(self, "Validate Profile", str(exc))
            return
        self.append_status("Profile validation passed.")

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
