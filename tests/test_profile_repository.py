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
    assert repository.list_profiles() == []
    assert repository.load_settings().default_log_folder == "logs"


def test_repository_create_update_delete(tmp_path: Path) -> None:
    """Profiles should round-trip through create, update, and delete."""
    repository = ProfileRepository(tmp_path / "config")
    profile = build_folder_profile()

    repository.create(profile)
    stored = repository.get_by_id(profile.id)
    assert stored is not None
    assert stored.name == "Documents"

    stored.name = "Pictures"
    repository.update(stored)
    updated = repository.get_by_id(profile.id)
    assert updated is not None
    assert updated.name == "Pictures"

    repository.delete(profile.id)
    assert repository.get_by_id(profile.id) is None

