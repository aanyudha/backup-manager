"""Tests for MySQL profile page behavior and layout safeguards."""

from __future__ import annotations

import os
import platform
from types import SimpleNamespace

if platform.system().lower() == "linux":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget

from app.models.profile import MySQLBackupProfile
from app.services.mysql_service import MySQLService
from app.ui.mysql_profiles_page import MySQLProfilesPage


def test_mysql_profiles_page_exposes_expanding_database_list() -> None:
    """The database list should remain visible after schedule fields are added."""
    app = QApplication.instance() or QApplication([])

    page = MySQLProfilesPage(MySQLService())

    assert page.objectName() == "mysqlProfilesPage"
    database_list = page.findChild(QListWidget, "databaseListWidget")
    assert database_list is not None
    assert database_list.minimumHeight() >= 160
    assert "auto-detect mysqldump from PATH" in page.mysqldump_help_label.text()
    assert "engine auto" not in page.mysqldump_help_label.text().lower()
    assert page.destination_type_combo.itemText(1) == "Network/Mounted Folder"
    assert "Windows UNC paths" in page.destination_helper_label.text()

    page.close()
    app.quit()


class StubMySQLService(MySQLService):
    """Simple MySQL service stub for UI selection tests."""

    def __init__(self, databases: list[str] | None = None) -> None:
        super().__init__()
        self.databases = databases or []

    def list_databases(self, **kwargs):  # type: ignore[no-untyped-def]
        return list(self.databases)


def build_profile(*, database_mode: str, databases: list[str]) -> MySQLBackupProfile:
    """Create a MySQL profile with saved database selections."""
    return MySQLBackupProfile(
        id="profile-1",
        name="Primary DB",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="secret",
        database_mode=database_mode,  # type: ignore[arg-type]
        databases=databases,
        destination="C:/backups",
    )


def test_loading_profile_restores_multiple_database_selection() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    profile = build_profile(database_mode="multiple", databases=["appdb", "analytics"])

    page.set_profiles([profile])

    assert page.get_selected_databases() == ["appdb", "analytics"]
    assert page.database_list.count() == 2

    page.close()
    app.quit()


def test_loading_database_list_preserves_saved_selection_and_marks_missing() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService(["appdb", "reporting"]))
    profile = build_profile(database_mode="multiple", databases=["appdb", "legacydb"])

    page.set_profiles([profile])
    page._load_databases()

    labels = [page.database_list.item(index).text() for index in range(page.database_list.count())]
    assert "legacydb (saved, not found)" in labels
    assert page.get_selected_databases() == ["appdb", "legacydb"]

    page.close()
    app.quit()


def test_saving_without_reloading_preserves_database_selection() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    profile = build_profile(database_mode="multiple", databases=["appdb", "analytics"])

    page.set_profiles([profile])
    collected = page._collect_form_data()

    assert collected.databases == ["appdb", "analytics"]

    page.close()
    app.quit()


def test_loading_profile_restores_single_database_selection() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    profile = build_profile(database_mode="single", databases=["appdb"])

    page.set_profiles([profile])

    assert page.get_selected_databases() == ["appdb"]

    page.close()
    app.quit()


def test_collect_form_data_persists_network_destination_type() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    page.name_edit.setText("Primary DB")
    page.host_edit.setText("127.0.0.1")
    page.username_edit.setText("root")
    page.destination_type_combo.setCurrentIndex(1)
    page.destination_edit.setText(r"\\server\share\backup")

    collected = page._collect_form_data()

    assert collected.destination_type == "network"
    assert collected.destination == r"\\server\share\backup"

    page.close()
    app.quit()


def test_collect_form_data_persists_windows_network_login_fields() -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    page.name_edit.setText("Primary DB")
    page.host_edit.setText("127.0.0.1")
    page.username_edit.setText("root")
    page.destination_type_combo.setCurrentIndex(1)
    page.destination_edit.setText(r"\\server\share\backup")
    page.destination_network_username_edit.setText("backup-user")
    page.destination_network_password_edit.setText("secret")
    page.destination_network_domain_edit.setText("WORKGROUP")
    page.destination_network_remember_session_checkbox.setChecked(True)

    collected = page._collect_form_data()

    assert collected.destination_network_username == "backup-user"
    assert collected.destination_network_password == "secret"
    assert collected.destination_network_domain == "WORKGROUP"
    assert collected.destination_network_remember_session is True

    page.close()
    app.quit()


def test_mysql_test_destination_calls_validation_only(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
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
        page.mysql_service,
        "test_connection",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("connection test should not run")),
    )
    monkeypatch.setattr(
        "app.ui.mysql_profiles_page.QMessageBox.information",
        lambda *args: dialogs.append(("info", str(args[-1]))),
    )
    monkeypatch.setattr(
        "app.ui.mysql_profiles_page.QMessageBox.warning",
        lambda *args: dialogs.append(("warn", str(args[-1]))),
    )

    page._test_destination()

    assert calls == [(r"\\server\share\backup", "network")]
    assert dialogs and dialogs[0][0] == "info"
    assert dialogs[0][1] == diagnostic
    assert diagnostic in page.status_output.toPlainText()

    page.close()
    app.quit()


def test_mysql_test_destination_connects_then_disconnects_when_credentials_provided(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    page = MySQLProfilesPage(StubMySQLService())
    page.destination_type_combo.setCurrentIndex(1)
    page.destination_edit.setText(r"\\server\share\backup")
    page.destination_network_username_edit.setText("backup-user")
    page.destination_network_password_edit.setText("secret")
    page.destination_network_domain_edit.setText("WORKGROUP")
    order: list[str] = []

    monkeypatch.setattr(page.platform_service, "is_windows", lambda: True)
    monkeypatch.setattr(
        "app.ui.mysql_profiles_page.connect_share_diagnostic",
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
        lambda path, destination_type: (order.append("validate") or True, "diagnostic"),
    )
    monkeypatch.setattr(
        "app.ui.mysql_profiles_page.disconnect_share_diagnostic",
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
    monkeypatch.setattr("app.ui.mysql_profiles_page.get_current_windows_user", lambda: "WORKGROUP\\tester")
    monkeypatch.setattr("app.ui.mysql_profiles_page.QMessageBox.information", lambda *args: None)
    monkeypatch.setattr("app.ui.mysql_profiles_page.QMessageBox.warning", lambda *args: None)

    page._test_destination()

    assert order == ["connect", "validate", "disconnect"]
    status_text = page.status_output.toPlainText()
    assert "Share Root: \\\\server\\share" in status_text
    assert "Current Windows User: WORKGROUP\\tester" in status_text
    assert "Write Probe Result:\ndiagnostic" in status_text

    page.close()
    app.quit()
