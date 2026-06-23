"""Tests for folder profile page layout safeguards."""

from __future__ import annotations

import os
import platform
from types import SimpleNamespace

if platform.system().lower() == "linux":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.services.platform_service import PlatformService
from app.services.remote_browser_service import RemoteBrowserService
from app.ui.folder_profiles_page import FolderProfilesPage


def test_folder_profiles_page_exposes_scrollable_form_and_status_panel(monkeypatch) -> None:
    """The folder page should remain usable after the source/destination redesign."""
    app = QApplication.instance() or QApplication([])
    platform_service = PlatformService()
    monkeypatch.setattr(platform_service, "is_windows", lambda: False)
    monkeypatch.setattr(platform_service, "command_exists", lambda command: False)

    page = FolderProfilesPage(platform_service, RemoteBrowserService())

    assert page.objectName() == "folderProfilesPage"
    assert page.status_output.minimumHeight() >= 100
    assert page.resolved_engine_value.text() == "local_copy"
    assert page.ftp_browse_button.text() == "Browse FTP Folder"
    assert "correct transport" in page.engine_helper_label.text()
    assert page.destination_type_combo.itemText(1) == "Network/Mounted Folder"

    page.close()
    app.quit()


def test_folder_profiles_page_switches_source_sections() -> None:
    """Source Type should show the matching section and helper text."""
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    page.source_type_combo.setCurrentIndex(1)
    assert not page.ftp_source_group.isHidden()
    assert page.source_path_group.isHidden()
    assert "FTP Source Folder" in page.source_helper_label.text()

    page.source_type_combo.setCurrentIndex(0)
    assert not page.source_path_group.isHidden()
    assert page.ftp_source_group.isHidden()
    assert "Local source uses the Source Folder path." == page.source_helper_label.text()

    page.close()
    app.quit()


def test_folder_profiles_page_updates_resolved_engine_for_remote_sources() -> None:
    """Remote-path fields should update the resolved engine label immediately."""
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    page.engine_combo.setCurrentText("auto")
    page.ftp_host_edit.setText("ftp.example.com")
    page.ftp_remote_path_edit.setText("/exports")
    assert page.resolved_engine_value.text() == "ftp"

    page.sftp_host_edit.setText("sftp.example.com")
    page.sftp_remote_path_edit.setText("/incoming")
    assert page.resolved_engine_value.text() == "sftp"
    assert "Auto selected SFTP" in page.warning_label.text()

    page.close()
    app.quit()


def test_selecting_ftp_folder_updates_remote_path_and_source_type(monkeypatch) -> None:
    """Applying a browsed FTP folder should write back to the FTP path field."""
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.QMessageBox.warning",
        lambda *args: warnings.append(str(args[-1])),
    )

    page.engine_combo.setCurrentText("auto")
    page._apply_ftp_remote_path("/exports")

    assert page.ftp_remote_path_edit.text() == "/exports"
    assert page.source_type_combo.currentData() == "ftp"
    assert page.resolved_engine_value.text() == "ftp"
    assert warnings == []

    page.close()
    app.quit()


def test_selecting_sftp_folder_sets_source_type_and_warns_when_engine_is_incompatible(monkeypatch) -> None:
    """Selecting an SFTP folder should warn when engine is not auto or sftp."""
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.QMessageBox.warning",
        lambda *args: warnings.append(str(args[-1])),
    )

    page.engine_combo.setCurrentText("ftp")
    page._apply_sftp_remote_path("/incoming")

    assert page.sftp_remote_path_edit.text() == "/incoming"
    assert page.source_type_combo.currentData() == "sftp"
    assert warnings == ["You selected an SFTP remote folder, but Engine is not auto or sftp."]

    page.close()
    app.quit()


def test_destination_helper_mentions_os_managed_credentials() -> None:
    """Destination guidance should explain UNC usage and scheduler guidance."""
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    assert "Windows UNC paths" in page.destination_helper_label.text()
    assert "Task Scheduler or service mode" in page.destination_network_warning_label.text()
    assert "destination upload is not supported yet" in page.destination_limitation_label.text()

    page.close()
    app.quit()


def test_folder_test_destination_calls_validation_only(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())
    page.destination_type_combo.setCurrentIndex(1)
    page.destination_edit.setText(r"\\server\share\backup")
    calls: list[tuple[str, str]] = []
    dialogs: list[tuple[str, str]] = []
    diagnostic = "Destination validation passed:\nPath: \\\\server\\share\\backup"

    monkeypatch.setattr(
        page.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (calls.append((path, destination_type)) or True, diagnostic),
    )
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.QMessageBox.information",
        lambda *args: dialogs.append(("info", str(args[-1]))),
    )
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.QMessageBox.warning",
        lambda *args: dialogs.append(("warn", str(args[-1]))),
    )
    monkeypatch.setattr(
        page,
        "_collect_form_data",
        lambda: (_ for _ in ()).throw(AssertionError("profile collection should not run")),
    )

    page._test_destination()

    assert calls == [(r"\\server\share\backup", "network")]
    assert dialogs and dialogs[0][0] == "info"
    assert dialogs[0][1] == diagnostic
    assert diagnostic in page.status_output.toPlainText()

    page.close()
    app.quit()


def test_network_destination_section_visibility_tracks_destination_type() -> None:
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())

    assert page.destination_network_group.isHidden()

    page.destination_type_combo.setCurrentIndex(1)
    assert not page.destination_network_group.isHidden()
    assert page.connect_network_share_button.text() == "Connect/Test Network Share"

    page.close()
    app.quit()


def test_folder_connect_test_share_runs_write_probe_after_connect(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = FolderProfilesPage(PlatformService(), RemoteBrowserService())
    page.destination_type_combo.setCurrentIndex(1)
    page.destination_edit.setText(r"\\server\share\backup")
    page.destination_network_username_edit.setText("backup-user")
    page.destination_network_password_edit.setText("secret")
    order: list[str] = []

    monkeypatch.setattr(page.platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.connect_share_diagnostic",
        lambda *args, **kwargs: (
            order.append("connect")
            or SimpleNamespace(
                success=True,
                message="connected",
                share_root=r"\\server\share",
                returncode=0,
            )
        ),
    )
    monkeypatch.setattr(
        page.path_validation_service,
        "validate_destination_path",
        lambda path, destination_type: (order.append("validate") or True, "probe ok"),
    )
    monkeypatch.setattr(
        "app.ui.folder_profiles_page.disconnect_share_diagnostic",
        lambda *args, **kwargs: (
            order.append("disconnect")
            or SimpleNamespace(
                success=True,
                message="disconnected",
                share_root=r"\\server\share",
                returncode=0,
            )
        ),
    )
    monkeypatch.setattr("app.ui.folder_profiles_page.get_current_windows_user", lambda: "WORKGROUP\\tester")
    monkeypatch.setattr("app.ui.folder_profiles_page.QMessageBox.information", lambda *args: None)
    monkeypatch.setattr("app.ui.folder_profiles_page.QMessageBox.warning", lambda *args: None)

    page._test_destination()

    assert order == ["connect", "validate", "disconnect"]
    status_text = page.status_output.toPlainText()
    assert "Share Root: \\\\server\\share" in status_text
    assert "Current Windows User: WORKGROUP\\tester" in status_text
    assert "Write Probe Result:\nprobe ok" in status_text

    page.close()
    app.quit()
