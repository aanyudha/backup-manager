"""Validate destination folders for local and OS-mounted network paths."""

from __future__ import annotations

import os
import re
import traceback
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

    @staticmethod
    def _bool_text(value: bool) -> str:
        return "true" if value else "false"

    @staticmethod
    def _safe_getlogin() -> str:
        try:
            return os.getlogin()
        except Exception as exc:  # pragma: no cover - platform/session dependent
            return f"unavailable ({exc.__class__.__name__}: {exc})"

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
    def _build_report(
        cls,
        *,
        success: bool,
        path: str,
        destination_type: str,
        pathlib_path: str,
        cwd: str,
        login_name: str,
        exists: bool,
        is_dir: bool,
        parent_exists: bool,
        mkdir_result: str,
        temp_filename: str,
        open_write_result: str,
        flush_result: str,
        close_result: str,
        delete_result: str,
        exception: Exception | None,
        traceback_text: str | None,
    ) -> str:
        title = "Destination validation passed:" if success else "Destination validation failed:"
        lines = [
            title,
            f"Path: {path}",
            f"Path Repr: {path!r}",
            f"Destination Type: {destination_type}",
            f"Current Working Directory: {cwd}",
            f"OS Login: {login_name}",
            f"Pathlib Path: {pathlib_path}",
            f"Exists: {cls._bool_text(exists)}",
            f"Is Dir: {cls._bool_text(is_dir)}",
            f"Parent Exists: {cls._bool_text(parent_exists)}",
            f"Mkdir Result: {mkdir_result}",
            f"Temp Filename Used: {temp_filename}",
            f"Open/Write Result: {open_write_result}",
            f"Flush Result: {flush_result}",
            f"Close Result: {close_result}",
            f"Delete Result: {delete_result}",
        ]
        if exception is None:
            lines.append("Exception: none")
        else:
            lines.append(f"Exception: {exception.__class__.__name__}: {exception}")
        if traceback_text:
            lines.append("Traceback:")
            lines.append(traceback_text.rstrip())
        return "\n".join(lines)

    @classmethod
    def _build_input_failure_message(
        cls,
        *,
        path: str,
        destination_type: str,
        exception: Exception,
    ) -> str:
        pathlib_path = str(Path(path)) if path else "."
        parent_path = str(Path(path).parent) if path else "."
        return cls._build_report(
            success=False,
            path=path,
            destination_type=destination_type,
            pathlib_path=pathlib_path,
            cwd=os.getcwd(),
            login_name=cls._safe_getlogin(),
            exists=cls._safe_exists(path),
            is_dir=cls._safe_is_dir(path),
            parent_exists=cls._safe_exists(parent_path),
            mkdir_result="skipped",
            temp_filename="(not created)",
            open_write_result="skipped",
            flush_result="skipped",
            close_result="skipped",
            delete_result="skipped",
            exception=exception,
            traceback_text=None,
        )

    @classmethod
    def validate_destination_path(cls, path: str, destination_type: str) -> tuple[bool, str]:
        """Validate a destination path and verify it is writable."""
        cleaned = path.strip()
        if not cleaned:
            return (
                False,
                cls._build_input_failure_message(
                    path=cleaned,
                    destination_type=destination_type,
                    exception=ValueError("Destination folder is required."),
                ),
            )
        if destination_type not in {"local", "network"}:
            return (
                False,
                cls._build_input_failure_message(
                    path=cleaned,
                    destination_type=destination_type,
                    exception=ValueError(f"Unsupported destination type: {destination_type}"),
                ),
            )
        if destination_type == "network" and cleaned.startswith("//"):
            return (
                False,
                cls._build_input_failure_message(
                    path=cleaned,
                    destination_type=destination_type,
                    exception=ValueError(
                        "Invalid Windows network path '//server/share'. "
                        r"Use a UNC path like '\\server\share\folder'."
                    ),
                ),
            )
        return cls.ensure_destination_writable(cleaned, destination_type=destination_type)

    @classmethod
    def ensure_destination_writable(
        cls,
        path: str,
        *,
        destination_type: str = "unknown",
    ) -> tuple[bool, str]:
        """Create the destination if needed and verify write access with a temp file."""
        cwd = os.getcwd()
        login_name = cls._safe_getlogin()
        pathlib_path = str(Path(path))
        parent_path = str(Path(path).parent)
        mkdir_result = "skipped"
        open_write_result = "skipped"
        flush_result = "skipped"
        close_result = "skipped"
        delete_result = "skipped"
        temp_filename = os.path.join(path, f".heisenberg-write-test-{uuid4().hex}.tmp")
        handle = None
        failure: Exception | None = None
        failure_traceback: str | None = None

        try:
            if cls._safe_exists(path):
                mkdir_result = "skipped (already exists)"
            else:
                try:
                    os.makedirs(path, exist_ok=True)
                    mkdir_result = "ok"
                except Exception as exc:
                    mkdir_result = f"failed ({exc.__class__.__name__}: {exc})"
                    raise

            if not cls._safe_is_dir(path):
                raise NotADirectoryError(f"Destination is not a directory: {path}")

            try:
                handle = open(temp_filename, "w", encoding="utf-8")
            except Exception as exc:
                open_write_result = f"open failed ({exc.__class__.__name__}: {exc})"
                raise

            try:
                handle.write("ok")
                open_write_result = "ok"
            except Exception as exc:
                open_write_result = f"write failed ({exc.__class__.__name__}: {exc})"
                raise

            try:
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError as exc:
                    flush_result = f"ok (fsync ignored: {exc.__class__.__name__}: {exc})"
                else:
                    flush_result = "ok"
            except Exception as exc:
                flush_result = f"failed ({exc.__class__.__name__}: {exc})"
                raise

            try:
                handle.close()
                handle = None
                close_result = "ok"
            except Exception as exc:
                close_result = f"failed ({exc.__class__.__name__}: {exc})"
                raise

            try:
                os.remove(temp_filename)
                delete_result = "ok"
            except Exception as exc:
                delete_result = f"failed ({exc.__class__.__name__}: {exc})"
                raise
        except Exception as exc:
            failure = exc
            failure_traceback = traceback.format_exc()
        finally:
            if handle is not None:
                try:
                    handle.close()
                    if close_result == "skipped":
                        close_result = "ok (finally)"
                except Exception as close_exc:
                    close_result = f"failed ({close_exc.__class__.__name__}: {close_exc})"
                    if failure is None:
                        failure = close_exc
                        failure_traceback = traceback.format_exc()
                handle = None

            if delete_result == "skipped" and cls._safe_exists(temp_filename):
                try:
                    os.remove(temp_filename)
                    delete_result = "ok (cleanup)"
                except Exception as delete_exc:
                    delete_result = f"failed ({delete_exc.__class__.__name__}: {delete_exc})"
                    if failure is None:
                        failure = delete_exc
                        failure_traceback = traceback.format_exc()

        report = cls._build_report(
            success=failure is None,
            path=path,
            destination_type=destination_type,
            pathlib_path=pathlib_path,
            cwd=cwd,
            login_name=login_name,
            exists=cls._safe_exists(path),
            is_dir=cls._safe_is_dir(path),
            parent_exists=cls._safe_exists(parent_path),
            mkdir_result=mkdir_result,
            temp_filename=temp_filename,
            open_write_result=open_write_result,
            flush_result=flush_result,
            close_result=close_result,
            delete_result=delete_result,
            exception=failure,
            traceback_text=failure_traceback,
        )
        return failure is None, report
