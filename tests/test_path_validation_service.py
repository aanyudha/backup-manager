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
