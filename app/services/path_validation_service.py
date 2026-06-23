"""Validate destination folders for local and OS-mounted network paths."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4


class PathValidationService:
    """Best-effort filesystem validation for backup destinations."""

    @staticmethod
    def is_unc_path(path: str) -> bool:
        """Return whether the path uses a Windows UNC prefix."""
        return path.strip().startswith("\\\\")

    @staticmethod
    def is_windows_mapped_drive(path: str) -> bool:
        """Return whether the path starts with a Windows drive prefix."""
        return bool(re.match(r"^[A-Za-z]:[\\/]", path.strip()))

    @staticmethod
    def is_linux_mount_like_path(path: str) -> bool:
        """Return whether the path resembles a mounted Linux share location."""
        cleaned = path.strip()
        return cleaned.startswith("/mnt/") or cleaned.startswith("/media/")

    @classmethod
    def validate_destination_path(cls, path: str, destination_type: str) -> tuple[bool, str]:
        """Validate a destination path and verify it is writable."""
        cleaned = path.strip()
        if not cleaned:
            return False, "Destination folder is required."
        if destination_type not in {"local", "network"}:
            return False, f"Unsupported destination type: {destination_type}"
        return cls.ensure_destination_writable(cleaned)

    @staticmethod
    def ensure_destination_writable(path: str) -> tuple[bool, str]:
        """Create the destination if needed and verify write access with a temp file."""
        destination = Path(path).expanduser()
        try:
            destination.mkdir(parents=True, exist_ok=True)
            if not destination.is_dir():
                raise NotADirectoryError(path)
            probe_path = destination / f".heisenberg-write-test-{uuid4().hex}.tmp"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink(missing_ok=True)
        except Exception:
            return False, f"Destination folder is not accessible or writable: {path}"
        return True, ""
