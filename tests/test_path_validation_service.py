"""Tests for destination path validation."""

from __future__ import annotations

from pathlib import Path

from app.services.path_validation_service import PathValidationService


def test_destination_validation_rejects_empty_value() -> None:
    valid, message = PathValidationService.validate_destination_path("", "local")

    assert valid is False
    assert message == "Destination folder is required."


def test_destination_validation_accepts_unc_like_path_without_mangling(monkeypatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(
        PathValidationService,
        "ensure_destination_writable",
        staticmethod(lambda path: (seen.append(path) or True, "")),
    )

    valid, message = PathValidationService.validate_destination_path(r"\\server\share\backup", "network")

    assert valid is True
    assert message == ""
    assert seen == [r"\\server\share\backup"]


def test_destination_writable_check_creates_and_removes_temp_file(tmp_path: Path) -> None:
    destination = tmp_path / "destination"

    valid, message = PathValidationService.ensure_destination_writable(str(destination))

    assert valid is True
    assert message == ""
    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_destination_validation_returns_clear_error_if_not_writable(tmp_path: Path) -> None:
    existing_file = tmp_path / "not-a-directory"
    existing_file.write_text("data", encoding="utf-8")

    valid, message = PathValidationService.ensure_destination_writable(str(existing_file))

    assert valid is False
    assert message == f"Destination folder is not accessible or writable: {existing_file}"
