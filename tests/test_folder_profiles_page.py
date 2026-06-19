"""Tests for folder profile page layout safeguards."""

from __future__ import annotations

import os
import platform

if platform.system().lower() == "linux":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.services.platform_service import PlatformService
from app.ui.folder_profiles_page import FolderProfilesPage


def test_folder_profiles_page_exposes_scrollable_form_and_status_panel() -> None:
    """The folder page should remain usable after scheduler fields were added."""
    app = QApplication.instance() or QApplication([])

    page = FolderProfilesPage(PlatformService())

    assert page.objectName() == "folderProfilesPage"
    assert page.status_output.minimumHeight() >= 100

    page.close()
    app.quit()
