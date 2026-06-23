"""Validate destination folders for local and OS-mounted network paths."""

from __future__ import annotations

import os
import re
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

    @staticmethod
    def _bool_text(value: bool) -> str:
        return "true" if value else "false"

    @classmethod
    def _build_failure_message(
        cls,
        *,
        path: str,
        exists: bool,
        is_dir: bool,
        create_folder: str,
        write_test: str,
        delete_test: str,
        exception: Exception,
    ) -> str:
        return (
            "Destination validation failed:\n"
            f"Path: {path}\n"
            f"Exists: {cls._bool_text(exists)}\n"
            f"Is Dir: {cls._bool_text(is_dir)}\n"
            f"Create Folder: {create_folder}\n"
            f"Write Test: {write_test}\n"
            f"Delete Test: {delete_test}\n"
            f"Exception: {exception.__class__.__name__}: {exception}"
        )

    @staticmethod
    def _safe_exists(path: str) -> bool:
        try:
            return os.path.exists(path)
        except OSError:
            return False

    @staticmethod
    def _safe_is_dir(path: str) -> bool:
        try:
            return os.path.isdir(path)
        except OSError:
            return False

    @classmethod
    def validate_destination_path(cls, path: str, destination_type: str) -> tuple[bool, str]:
        """Validate a destination path and verify it is writable."""
        cleaned = path.strip()
        if not cleaned:
            return (
                False,
                cls._build_failure_message(
                    path=cleaned,
                    exists=False,
                    is_dir=False,
                    create_folder="skipped",
                    write_test="skipped",
                    delete_test="skipped",
                    exception=ValueError("Destination folder is required."),
                ),
            )
        if destination_type not in {"local", "network"}:
            return (
                False,
                cls._build_failure_message(
                    path=cleaned,
                    exists=cls._safe_exists(cleaned),
                    is_dir=cls._safe_is_dir(cleaned),
                    create_folder="skipped",
                    write_test="skipped",
                    delete_test="skipped",
                    exception=ValueError(f"Unsupported destination type: {destination_type}"),
                ),
            )
        return cls.ensure_destination_writable(cleaned)

    @classmethod
    def ensure_destination_writable(cls, path: str) -> tuple[bool, str]:
        """Create the destination if needed and verify write access with a temp file."""
        create_folder = "skipped"
        write_test = "skipped"
        delete_test = "skipped"
        probe_path = os.path.join(path, f".heisenberg-write-test-{uuid4().hex}.tmp")

        try:
            existed_before = cls._safe_exists(path)
            if existed_before:
                create_folder = "skipped"
            else:
                os.makedirs(path, exist_ok=True)
                create_folder = "ok"

            if not cls._safe_is_dir(path):
                raise NotADirectoryError(f"Destination is not a directory: {path}")

            with open(probe_path, "w", encoding="utf-8") as handle:
                handle.write("ok")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            write_test = "ok"

            os.remove(probe_path)
            delete_test = "ok"
        except Exception as exc:
            if write_test == "skipped" and cls._safe_exists(probe_path):
                write_test = "failed"
            if delete_test == "skipped" and write_test == "ok":
                delete_test = "failed"
            return (
                False,
                cls._build_failure_message(
                    path=path,
                    exists=cls._safe_exists(path),
                    is_dir=cls._safe_is_dir(path),
                    create_folder=create_folder if create_folder != "skipped" or cls._safe_exists(path) else "failed",
                    write_test=write_test,
                    delete_test=delete_test,
                    exception=exc,
                ),
            )
        return True, ""
