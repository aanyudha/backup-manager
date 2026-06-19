"""Tests for MySQL profile page layout safeguards."""

from __future__ import annotations

import os
import platform

if platform.system().lower() == "linux":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget

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
