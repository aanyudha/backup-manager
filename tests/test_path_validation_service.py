"""Tests for destination path validation."""

from __future__ import annotations

from pathlib import Path

import app.services.path_validation_service as path_validation_module
from app.services.path_validation_service import PathValidationService


def test_destination_validation_rejects_empty_value() -> None:
    valid, message = PathValidationService.validate_destination_path("", "local")

    assert valid is False
    assert "Destination validation failed:" in message
    assert "Mkdir Result: skipped" in message
    assert "Open/Write Result: skipped" in message
    assert "Delete Result: skipped" in message
    assert "Exception: ValueError: Destination folder is required." in message


def test_destination_validation_accepts_unc_like_path_without_mangling(monkeypatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(
        PathValidationService,
        "ensure_destination_writable",
        staticmethod(lambda path, destination_type="unknown": (seen.append(path) or True, "diagnostic")),
    )

    valid, message = PathValidationService.validate_destination_path(r"\\server\share\backup", "network")

    assert valid is True
    assert message == "diagnostic"
    assert seen == [r"\\server\share\backup"]


def test_destination_validation_does_not_call_resolve_for_unc_paths(monkeypatch) -> None:
    unc_path = r"\\server\share\backup"
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(path_validation_module.os.path, "exists", lambda current: current == unc_path)
    monkeypatch.setattr(path_validation_module.os.path, "isdir", lambda current: current == unc_path)
    monkeypatch.setattr(path_validation_module.os, "makedirs", lambda current, exist_ok=True: calls.append(("makedirs", current)))
    monkeypatch.setattr(path_validation_module.os, "remove", lambda current: calls.append(("remove", current)))
    monkeypatch.setattr(path_validation_module.os, "fsync", lambda fd: None)

    def fake_open(current, mode="r", encoding=None):  # type: ignore[no-untyped-def]
        calls.append(("open", current))

        class Handle:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
                return False

            def close(self) -> None:
                return None

            def write(self, text: str) -> int:
                return len(text)

            def flush(self) -> None:
                return None

            def fileno(self) -> int:
                return 1

        return Handle()

    monkeypatch.setattr(path_validation_module, "open", fake_open, raising=False)
    monkeypatch.setattr(Path, "resolve", lambda self, *args, **kwargs: (_ for _ in ()).throw(AssertionError("resolve should not be used")))

    valid, message = PathValidationService.ensure_destination_writable(unc_path)

    assert valid is True
    assert "Destination validation passed:" in message
    assert f"Path Repr: {unc_path!r}" in message
    assert "Mkdir Result: skipped (already exists)" in message
    assert "Open/Write Result: ok" in message
    assert "Flush Result: ok" in message
    assert "Close Result: ok" in message
    assert "Delete Result: ok" in message
    assert len(calls) == 2
    assert ("makedirs", unc_path) not in calls
    assert calls[0][0] == "open"
    assert isinstance(calls[0][1], str)
    assert str(calls[0][1]).startswith(f"{unc_path}\\")
    assert calls[1] == ("remove", calls[0][1])


def test_destination_writable_check_creates_and_removes_temp_file(tmp_path: Path) -> None:
    destination = tmp_path / "destination"

    valid, message = PathValidationService.ensure_destination_writable(str(destination))

    assert valid is True
    assert "Destination validation passed:" in message
    assert "Mkdir Result: ok" in message
    assert "Delete Result: ok" in message
    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_destination_validation_returns_clear_error_if_not_writable(tmp_path: Path) -> None:
    existing_file = tmp_path / "not-a-directory"
    existing_file.write_text("data", encoding="utf-8")

    valid, message = PathValidationService.ensure_destination_writable(str(existing_file))

    assert valid is False
    assert "Destination validation failed:" in message
    assert f"Path: {existing_file}" in message
    assert "Exists: true" in message
    assert "Is Dir: false" in message
    assert "Mkdir Result: skipped (already exists)" in message
    assert "Open/Write Result: skipped" in message
    assert "Delete Result: skipped" in message
    assert "Exception: NotADirectoryError:" in message


def test_network_destination_rejects_forward_slash_unc_path() -> None:
    valid, message = PathValidationService.validate_destination_path("//server/share/folder", "network")

    assert valid is False
    assert "Invalid Windows network path '//server/share'" in message
    assert r"Use a UNC path like '\\server\share\folder'." in message


def test_get_windows_drive_root_returns_drive_root() -> None:
    assert PathValidationService.get_windows_drive_root(r"Z:\cctv") == "Z:\\"
    assert PathValidationService.get_windows_drive_root(r"Z:\backup\folder") == "Z:\\"
    assert PathValidationService.get_windows_drive_root("Z:/cctv") == "Z:\\"
    assert PathValidationService.get_windows_drive_root(r"\\server\share\folder") == ""
    assert PathValidationService.get_windows_drive_root("/mnt/data") == ""
    assert PathValidationService.get_windows_drive_root("") == ""


def test_robocopy_destination_preflight_requires_input_and_valid_syntax() -> None:
    valid, message = PathValidationService.validate_robocopy_destination("", "network")

    assert valid is False
    assert message == "Destination folder is required."

    valid, message = PathValidationService.validate_robocopy_destination("//server/share/folder", "network")

    assert valid is False
    assert "Invalid Windows network path '//server/share'" in message

    valid, message = PathValidationService.validate_robocopy_destination(r"Z:\cctv", "mysql")

    assert valid is False
    assert message == "Unsupported destination type: mysql"


def test_robocopy_destination_preflight_skips_mkdir_and_write_probe(
    monkeypatch,
) -> None:
    """The robocopy preflight must never create or write to the destination."""
    monkeypatch.setattr(PathValidationService, "_safe_is_dir", staticmethod(lambda path: True))
    monkeypatch.setattr(
        path_validation_module.os,
        "makedirs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("mkdir must not run")),
    )
    monkeypatch.setattr(
        PathValidationService,
        "ensure_destination_writable",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("write probe must not run"))),
    )

    valid, message = PathValidationService.validate_robocopy_destination(r"Z:\cctv", "network")

    assert valid is True
    assert message == r"Robocopy destination preflight passed: Z:\cctv"


def test_robocopy_destination_preflight_reports_inaccessible_mapped_drive(monkeypatch) -> None:
    monkeypatch.setattr(PathValidationService, "_safe_is_dir", staticmethod(lambda path: False))
    monkeypatch.setattr(
        PathValidationService,
        "is_running_under_scheduler_or_service",
        staticmethod(lambda: False),
    )

    valid, message = PathValidationService.validate_robocopy_destination(r"Z:\cctv", "network")

    assert valid is False
    assert message == "Mapped network drive Z: is not accessible to this process."


def test_robocopy_destination_preflight_appends_unc_guidance_for_scheduler_runs(monkeypatch) -> None:
    monkeypatch.setattr(PathValidationService, "_safe_is_dir", staticmethod(lambda path: False))
    monkeypatch.setattr(
        PathValidationService,
        "is_running_under_scheduler_or_service",
        staticmethod(lambda: True),
    )

    valid, message = PathValidationService.validate_robocopy_destination(r"Z:\cctv", "network")

    assert valid is False
    assert message.startswith("Mapped network drive Z: is not accessible to this process.")
    assert "Mapped drives may not be available to Windows Task Scheduler or service accounts." in message
    assert r"Prefer a UNC destination such as \\server\share\folder." in message


def test_scheduler_context_detected_from_cli_and_environment(monkeypatch) -> None:
    monkeypatch.setattr(path_validation_module.sys, "argv", ["app.py", "--scheduler-service"])
    assert PathValidationService.is_running_under_scheduler_or_service() is True

    monkeypatch.setattr(path_validation_module.sys, "argv", ["app.py"])
    monkeypatch.delenv("SESSIONNAME", raising=False)
    monkeypatch.delenv("BACKUP_MANAGER_SCHEDULER_MODE", raising=False)
    assert PathValidationService.is_running_under_scheduler_or_service() is False

    monkeypatch.setenv("SESSIONNAME", "Services-0")
    assert PathValidationService.is_running_under_scheduler_or_service() is True

    monkeypatch.setenv("SESSIONNAME", "Console")
    monkeypatch.setenv("BACKUP_MANAGER_SCHEDULER_MODE", "true")
    assert PathValidationService.is_running_under_scheduler_or_service() is True
