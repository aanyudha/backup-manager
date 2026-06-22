"""Tests for service-mode helper exports."""

from __future__ import annotations

from pathlib import Path

from app.services.service_mode_export_service import ServiceModeExportService


def build_service(tmp_path: Path, *, frozen: bool = False) -> ServiceModeExportService:
    """Create a service export helper with test-specific paths."""
    return ServiceModeExportService(
        app_script_path=None if frozen else tmp_path / "app.py",
        working_directory=tmp_path,
        exports_dir=tmp_path / "exports" / "service",
    )


def test_windows_service_export_includes_scheduler_service(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    paths = service.save_windows_exports(Path(r"C:\Python312\python.exe"))

    task_text = paths[0].read_text(encoding="utf-8")
    run_now_text = paths[1].read_text(encoding="utf-8")
    assert "--scheduler-service" in task_text
    assert "--scheduler-service" in run_now_text


def test_linux_service_export_includes_scheduler_service(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    paths = service.save_linux_exports("/usr/bin/python3")

    unit_text = paths[0].read_text(encoding="utf-8")
    install_text = paths[1].read_text(encoding="utf-8")
    assert "--scheduler-service" in unit_text
    assert "systemctl enable heisenberg-backup-manager" in install_text


def test_service_exports_do_not_include_passwords(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    paths = service.save_linux_exports("/usr/bin/python3")
    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "secret" not in combined_text
    assert "password" not in combined_text.lower()
