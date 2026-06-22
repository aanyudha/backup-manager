"""Tests for MySQL profile page behavior and layout safeguards."""

from __future__ import annotations

import os
import platform

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
