"""Helpers for sanitizing remote paths for local filesystem writes."""

from __future__ import annotations

import json
import os
import platform as platform_module
import posixpath
from pathlib import Path, PurePosixPath

CURRENT_PLATFORM = platform_module.system().lower()
WINDOWS_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
FILENAME_MAP_NAME = ".heisenberg_filename_map.json"


def _normalized_platform(platform: str) -> str:
    value = (platform or CURRENT_PLATFORM).strip().lower()
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    if value.startswith("darwin") or value.startswith("mac"):
        return "darwin"
    return value


def _is_windows_platform(platform: str) -> bool:
    return _normalized_platform(platform) == "windows"


def _is_control_character(character: str) -> bool:
    return ord(character) < 32 or ord(character) == 127


def _append_suffix_before_extension(name: str, suffix: str) -> str:
    stem, extension = os.path.splitext(name)
    if not stem and extension:
        return f"{name}{suffix}"
    return f"{stem}{suffix}{extension}"


def _normalize_remote_relative_path(remote_relative_path: str) -> str:
    raw_value = str(remote_relative_path or "").replace("\\", "/")
    parts = [part for part in raw_value.split("/") if part not in {"", "."}]
    if not parts:
        return "_"
    return posixpath.join(*parts)


def _safe_path_parts(relative_path: str) -> tuple[str, ...]:
    return PurePosixPath(relative_path).parts or ("_",)


def sanitize_filename_component(name: str, platform: str = CURRENT_PLATFORM) -> str:
    """Return one filesystem-safe filename component for the target platform."""
    normalized_platform = _normalized_platform(platform)
    cleaned_characters: list[str] = []
    invalid_characters = WINDOWS_INVALID_FILENAME_CHARS if normalized_platform == "windows" else {"/"}

    for character in str(name):
        if _is_control_character(character):
            continue
        if character in invalid_characters:
            cleaned_characters.append("_")
            continue
        cleaned_characters.append(character)

    candidate = "".join(cleaned_characters)
    if normalized_platform == "windows":
        stem, extension = os.path.splitext(candidate)
        stem = stem.rstrip(" .")
        extension = extension.rstrip(" .")
        candidate = f"{stem}{extension}".rstrip(" .")
    if candidate in {".", ".."}:
        candidate = ""
    if not candidate:
        candidate = "_"
    if normalized_platform == "windows":
        reserved_key = Path(candidate).stem.upper()
        if reserved_key in WINDOWS_RESERVED_NAMES:
            candidate = _append_suffix_before_extension(candidate, "_")
    return candidate


def sanitize_relative_path(remote_relative_path: str, platform: str = CURRENT_PLATFORM) -> str:
    """Sanitize each component of a relative path while preserving its structure."""
    normalized_platform = _normalized_platform(platform)
    parts = _safe_path_parts(_normalize_remote_relative_path(remote_relative_path))
    sanitized_parts = [sanitize_filename_component(part, normalized_platform) for part in parts]
    return posixpath.join(*sanitized_parts)


class PathSanitizerService:
    """Build stable, collision-safe local paths for remote downloads."""

    def __init__(self, destination_root: Path | str, platform: str = CURRENT_PLATFORM) -> None:
        self.destination_root = Path(destination_root)
        self.platform = _normalized_platform(platform)
        self._component_aliases_by_parent: dict[tuple[str, ...], dict[str, str]] = {}
        self._used_names_by_parent: dict[tuple[str, ...], set[str]] = {}
        self._resolved_relative_paths: dict[str, str] = {}
        self._filename_mappings: list[dict[str, str]] = []
        self._recorded_mappings: set[tuple[str, str]] = set()

    def _collision_key(self, name: str) -> str:
        return name.casefold() if _is_windows_platform(self.platform) else name

    def _assign_unique_component(self, parent_parts: tuple[str, ...], raw_component: str) -> str:
        aliases = self._component_aliases_by_parent.setdefault(parent_parts, {})
        if raw_component in aliases:
            return aliases[raw_component]

        candidate = sanitize_filename_component(raw_component, self.platform)
        used_names = self._used_names_by_parent.setdefault(parent_parts, set())
        unique_name = candidate
        counter = 1
        while self._collision_key(unique_name) in used_names:
            unique_name = _append_suffix_before_extension(candidate, f"__{counter}")
            counter += 1

        aliases[raw_component] = unique_name
        used_names.add(self._collision_key(unique_name))
        return unique_name

    def resolve_relative_path(
        self,
        remote_relative_path: str,
        *,
        record_mapping: bool = True,
    ) -> tuple[str, str, bool]:
        """Return the original normalized relative path and its safe local variant."""
        normalized_remote = _normalize_remote_relative_path(remote_relative_path)
        safe_relative = self._resolved_relative_paths.get(normalized_remote)
        if safe_relative is None:
            raw_parts = _safe_path_parts(normalized_remote)
            safe_parts: list[str] = []
            for raw_part in raw_parts:
                parent_parts = tuple(safe_parts)
                safe_parts.append(self._assign_unique_component(parent_parts, raw_part))
            safe_relative = posixpath.join(*safe_parts)
            self._resolved_relative_paths[normalized_remote] = safe_relative

        changed = safe_relative != normalized_remote
        if record_mapping and changed:
            mapping_key = (normalized_remote, safe_relative)
            if mapping_key not in self._recorded_mappings:
                self._filename_mappings.append(
                    {
                        "remote": normalized_remote,
                        "local": safe_relative,
                    }
                )
                self._recorded_mappings.add(mapping_key)
        return normalized_remote, safe_relative, changed

    def build_safe_relative_path(self, remote_relative_path: str, *, record_mapping: bool = True) -> str:
        """Return only the sanitized relative path."""
        _, safe_relative, _ = self.resolve_relative_path(remote_relative_path, record_mapping=record_mapping)
        return safe_relative

    def build_safe_local_path(self, remote_relative_path: str, *, record_mapping: bool = True) -> Path:
        """Return the full local filesystem path under the configured root."""
        safe_relative = self.build_safe_relative_path(remote_relative_path, record_mapping=record_mapping)
        return self.destination_root.joinpath(*_safe_path_parts(safe_relative))

    @property
    def filename_mappings(self) -> list[dict[str, str]]:
        """Return the collected remote-to-local filename mappings."""
        return list(self._filename_mappings)

    @property
    def has_sanitized_paths(self) -> bool:
        """Return whether any remote path changed for local compatibility."""
        return bool(self._filename_mappings)

    def write_filename_map(self, root: Path | str | None = None) -> Path | None:
        """Write the filename mapping file only when any path changed."""
        if not self._filename_mappings:
            return None
        target_root = Path(root) if root is not None else self.destination_root
        target_path = target_root / FILENAME_MAP_NAME
        target_path.write_text(json.dumps(self._filename_mappings, indent=2), encoding="utf-8")
        return target_path


def build_safe_local_path(
    destination_root: Path | str,
    remote_relative_path: str,
    platform: str = CURRENT_PLATFORM,
) -> Path:
    """Build one safe local path without preserving cross-call collision state."""
    return PathSanitizerService(destination_root, platform=platform).build_safe_local_path(remote_relative_path)
