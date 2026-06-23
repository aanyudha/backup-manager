"""Tests for the JSON-backed profile repository."""

from __future__ import annotations

from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.repositories.profile_repository import ProfileRepository


def build_folder_profile(name: str = "Documents") -> FolderBackupProfile:
    """Create a valid folder profile for tests."""
    return FolderBackupProfile(
        name=name,
        source="/tmp/source",
        destination="/tmp/destination",
        engine="local_copy",
        mode="copy_new_changed",
    )


def test_repository_creates_config_files(tmp_path: Path) -> None:
    """Repository should auto-create config files with defaults."""
    config_dir = tmp_path / "config"

    repository = ProfileRepository(config_dir)

    assert repository.profiles_path.exists()
    assert repository.settings_path.exists()
    assert repository.restore_history_path.exists()
    assert repository.list_profiles() == []
    assert repository.list_restore_history() == []
    assert repository.load_settings().default_log_folder == "logs"
    assert repository.load_settings().auto_start_scheduler is False
    assert repository.load_settings().run_as_service is False
    assert repository.load_settings().service_runner_mode == "internal_scheduler"


def test_repository_create_update_delete(tmp_path: Path) -> None:
    """Profiles should round-trip through create, update, and delete."""
    repository = ProfileRepository(tmp_path / "config")
    profile = build_folder_profile()
    profile.schedule_enabled = True
    profile.schedule_runner = "external_os"
    profile.schedule_type = "daily"
    profile.schedule_time = "10:00"

    repository.create(profile)
    stored = repository.get_by_id(profile.id)
    assert stored is not None
    assert stored.name == "Documents"
    assert stored.schedule_runner == "external_os"

    stored.name = "Pictures"
    repository.update(stored)
    updated = repository.get_by_id(profile.id)
    assert updated is not None
    assert updated.name == "Pictures"

    repository.delete(profile.id)
    assert repository.get_by_id(profile.id) is None


def test_repository_normalizes_legacy_schedule_runner_values(tmp_path: Path) -> None:
    """Legacy runner names should load as the new normalized values."""
    repository = ProfileRepository(tmp_path / "config")
    profile = build_folder_profile()
    profile.schedule_enabled = True
    profile.schedule_runner = "internal_app"
    repository.create(profile)

    repository.profiles_path.write_text(
        """
{
  "profiles": [
    {
      "id": "legacy-profile",
      "name": "Legacy Runner",
      "type": "folder",
      "source": "/tmp/source",
      "destination": "/tmp/destination",
      "engine": "local_copy",
      "mode": "copy_new_changed",
      "schedule_enabled": true,
      "schedule_runner": "external",
      "schedule_type": "daily",
      "schedule_time": "10:00"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    stored = repository.list_profiles()[0]

    assert stored.schedule_runner == "external_os"
