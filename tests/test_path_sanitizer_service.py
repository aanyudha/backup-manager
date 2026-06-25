"""Tests for remote path sanitization helpers."""

from __future__ import annotations

from pathlib import Path

from app.services.path_sanitizer_service import (
    FILENAME_MAP_NAME,
    PathSanitizerService,
    WINDOWS_INVALID_FILENAME_CHARS,
    sanitize_filename_component,
    sanitize_relative_path,
)


def test_windows_filename_sanitizer_replaces_invalid_characters() -> None:
    assert sanitize_filename_component("57915_535352720 |.pdf", platform="windows") == "57915_535352720 _.pdf"


def test_windows_filename_sanitizer_avoids_reserved_names() -> None:
    assert sanitize_filename_component("CON.txt", platform="windows") == "CON_.txt"


def test_windows_filename_sanitizer_strips_trailing_dots_and_spaces() -> None:
    assert sanitize_filename_component("report.txt. ", platform="windows") == "report.txt"


def test_relative_path_sanitizer_preserves_nested_structure() -> None:
    assert (
        sanitize_relative_path("pdf/57915_535352720 |.pdf", platform="windows")
        == "pdf/57915_535352720 _.pdf"
    )


def test_collision_gets_unique_suffix(tmp_path: Path) -> None:
    service = PathSanitizerService(tmp_path, platform="windows")

    first = service.build_safe_local_path("a|b.pdf")
    second = service.build_safe_local_path("a?b.pdf")

    assert first.name == "a_b.pdf"
    assert second.name == "a_b__1.pdf"


def test_sanitized_windows_path_has_no_invalid_characters() -> None:
    sanitized = sanitize_relative_path('bad<dir>/bad|name?.txt', platform="windows")

    for component in sanitized.split("/"):
        assert component
        assert component == component.rstrip(" .")
        assert not any(character in WINDOWS_INVALID_FILENAME_CHARS for character in component)


def test_filename_map_is_written_only_when_any_path_changes(tmp_path: Path) -> None:
    service = PathSanitizerService(tmp_path, platform="windows")
    assert service.write_filename_map() is None

    service.build_safe_local_path("pdf/57915_535352720 |.pdf")
    map_path = service.write_filename_map()

    assert map_path == tmp_path / FILENAME_MAP_NAME
    assert map_path is not None
    assert map_path.read_text(encoding="utf-8") == (
        '[\n'
        '  {\n'
        '    "remote": "pdf/57915_535352720 |.pdf",\n'
        '    "local": "pdf/57915_535352720 _.pdf"\n'
        '  }\n'
        ']'
    )
