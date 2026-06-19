"""JSON-backed repository for profiles and application settings."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.models.profile import Profile, parse_profile
from app.models.restore_result import RestoreResult
from app.models.settings import AppSettings


class ProfileRepository:
    """Persist profiles and settings in JSON files."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.profiles_path = self.config_dir / "profiles.json"
        self.settings_path = self.config_dir / "settings.json"
        self.restore_history_path = self.config_dir / "restore_history.json"
        self._ensure_files()

    def _ensure_files(self) -> None:
        """Create missing config files with valid defaults."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.profiles_path.exists():
            self._atomic_write_json(self.profiles_path, {"profiles": []})
        if not self.settings_path.exists():
            self._atomic_write_json(self.settings_path, AppSettings().model_dump())
        if not self.restore_history_path.exists():
            self._atomic_write_json(self.restore_history_path, {"history": []})

    def _atomic_write_json(self, path: Path, payload: object) -> None:
        """Write JSON atomically by replacing a temporary file."""
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, indent=2, ensure_ascii=True, default=str)
            temp_file.flush()
            temp_path = Path(temp_file.name)
        temp_path.replace(path)

    def list_profiles(self) -> list[Profile]:
        """Return all stored profiles."""
        data = json.loads(self.profiles_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items = data.get("profiles", [])
        else:
            items = data
        return [parse_profile(item) for item in items]

    def get_by_id(self, profile_id: str) -> Profile | None:
        """Fetch one profile by identifier."""
        for profile in self.list_profiles():
            if profile.id == profile_id:
                return profile
        return None

    def create(self, profile: Profile) -> Profile:
        """Insert a new profile."""
        profiles = self.list_profiles()
        profiles.append(profile)
        self._save_profiles(profiles)
        return profile

    def update(self, profile: Profile) -> Profile:
        """Replace an existing profile."""
        profiles = self.list_profiles()
        updated = False
        for index, existing in enumerate(profiles):
            if existing.id == profile.id:
                profiles[index] = profile
                updated = True
                break
        if not updated:
            raise KeyError(f"Profile {profile.id} not found.")
        self._save_profiles(profiles)
        return profile

    def delete(self, profile_id: str) -> None:
        """Delete a profile by identifier."""
        profiles = [profile for profile in self.list_profiles() if profile.id != profile_id]
        self._save_profiles(profiles)

    def _save_profiles(self, profiles: list[Profile]) -> None:
        """Persist profile collection."""
        payload = {"profiles": [profile.model_dump(mode="json") for profile in profiles]}
        self._atomic_write_json(self.profiles_path, payload)

    def load_settings(self) -> AppSettings:
        """Load application settings from disk."""
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        return AppSettings.model_validate(data)

    def save_settings(self, settings: AppSettings) -> AppSettings:
        """Persist application settings."""
        self._atomic_write_json(self.settings_path, settings.model_dump())
        return settings

    def list_restore_history(self) -> list[RestoreResult]:
        """Return persisted restore runs."""
        data = json.loads(self.restore_history_path.read_text(encoding="utf-8"))
        items = data.get("history", []) if isinstance(data, dict) else data
        return [RestoreResult.model_validate(item) for item in items]

    def append_restore_result(self, result: RestoreResult) -> RestoreResult:
        """Append one restore result to the persisted history."""
        history = self.list_restore_history()
        history.append(result)
        payload = {"history": [entry.model_dump(mode="json") for entry in history]}
        self._atomic_write_json(self.restore_history_path, payload)
        return result
