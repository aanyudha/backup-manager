"""Tests for external scheduler export generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.profile import MySQLBackupProfile
from app.services.external_scheduler_service import ExternalSchedulerService


def build_profile(
    tmp_path: Path,
    *,
    schedule_type: str = "daily",
    schedule_time: str = "10:15",
    schedule_days_of_week: list[int] | None = None,
    schedule_day_of_month: int | None = None,
    enabled: bool = True,
    schedule_enabled: bool = True,
    schedule_runner: str = "external",
    name: str = "Primary DB",
) -> MySQLBackupProfile:
    """Create a schedulable profile for export tests."""
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    return MySQLBackupProfile(
        id="profile-1",
        name=name,
        host="127.0.0.1",
        port=3306,
        username="root",
        password="secret",
        database_mode="single",
        databases=["appdb"],
        mysqldump_path=str(fake_dump),
        destination=str(tmp_path / "backups"),
        enabled=enabled,
        schedule_enabled=schedule_enabled,
        schedule_runner=schedule_runner,  # type: ignore[arg-type]
        schedule_type=schedule_type,  # type: ignore[arg-type]
        schedule_time=schedule_time,
        schedule_days_of_week=schedule_days_of_week or [],
        schedule_day_of_month=schedule_day_of_month,
    )


def build_service(tmp_path: Path) -> ExternalSchedulerService:
    """Create an export service with test-specific paths."""
    return ExternalSchedulerService(
        app_script_path=tmp_path / "app.py",
        logs_dir=tmp_path / "logs",
        exports_dir=tmp_path / "exports" / "scheduler",
    )


def test_default_schedule_runner_is_internal(tmp_path: Path) -> None:
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    profile = MySQLBackupProfile(
        id="profile-1",
        name="Primary DB",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="secret",
        database_mode="single",
        databases=["appdb"],
        mysqldump_path=str(fake_dump),
        destination=str(tmp_path / "backups"),
    )

    assert profile.schedule_runner == "internal"


def test_daily_cron_expression(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="daily", schedule_time="10:15")

    assert service.schedule_to_cron_expression(profile) == "15 10 * * *"


def test_weekly_cron_expression(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="weekly",
        schedule_time="09:05",
        schedule_days_of_week=[0, 2, 4],
    )

    assert service.schedule_to_cron_expression(profile) == "5 9 * * MON,WED,FRI"


def test_monthly_cron_expression(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="monthly",
        schedule_time="23:45",
        schedule_day_of_month=19,
    )

    assert service.schedule_to_cron_expression(profile) == "45 23 19 * *"


def test_external_export_rejects_internal_runner_profiles(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_runner="internal")

    with pytest.raises(ValueError, match="Set Schedule Runner to External before exporting this profile."):
        service.validate_exportable(profile)


def test_external_export_allows_external_runner_profiles(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_runner="external")

    export = service.build_export(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert export.safe_profile_name == "Primary_DB"
    assert "--run-profile-id profile-1" in export.windows_register_command


def test_windows_source_mode_command_includes_python_and_app_py(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)
    python_path = Path(r"C:\backup-manager\.venv\Scripts\python.exe")
    app_path = str(tmp_path / "app.py")

    run_now_command = service.generate_run_now_command(profile, python_path, shell="windows")

    assert f'"{python_path}"' in run_now_command
    assert f'"{app_path}"' in run_now_command
    assert "--run-profile-id profile-1" in run_now_command


def test_windows_frozen_mode_command_includes_exe_only(tmp_path: Path) -> None:
    service = ExternalSchedulerService(
        app_script_path=None,
        logs_dir=tmp_path / "logs",
        exports_dir=tmp_path / "exports" / "scheduler",
    )
    profile = build_profile(tmp_path)
    exe_path = Path(r"C:\HBM\HeisenbergBackupManager.exe")

    run_now_command = service.generate_run_now_command(profile, exe_path, shell="windows")

    assert f'"{exe_path}" --run-profile-id profile-1' == run_now_command
    assert "app.py" not in run_now_command


def test_windows_task_register_command_quotes_tr_correctly(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)
    python_path = Path(r"C:\Program Files\Python 3.12\python.exe")
    app_path = str(tmp_path / "app.py")

    command = service.generate_windows_task_command(profile, python_path)

    assert f'/TR "\\"{python_path}\\" \\"{app_path}\\" --run-profile-id profile-1" ^' in command


def test_windows_register_script_states_it_does_not_run_immediately(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)

    export = service.build_export(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert "It does NOT run the backup immediately." in export.windows_register_script


def test_windows_run_now_script_does_not_include_schtasks(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)

    export = service.build_export(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert "schtasks" not in export.windows_run_now_script
    assert "--run-profile-id profile-1" in export.windows_run_now_script


def test_windows_register_command_includes_schedule_fields_but_run_now_does_not(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_time="14:54")

    export = service.build_export(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert "/SC DAILY" in export.windows_register_command
    assert "/ST 14:54" in export.windows_register_command
    assert "/SC" not in export.windows_run_now_command
    assert "/ST" not in export.windows_run_now_command


def test_linux_cron_export_uses_schedule_from_profile(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="weekly",
        schedule_time="09:05",
        schedule_days_of_week=[0, 2, 4],
    )

    cron_line = service.generate_cron_line(profile, "/usr/local/bin/python3")

    assert cron_line.startswith("5 9 * * MON,WED,FRI ")


def test_linux_run_now_command_excludes_cron_timing(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)

    run_now_command = service.generate_run_now_command(profile, "/usr/local/bin/python3", shell="linux")

    assert not run_now_command.startswith("15 10")
    assert ">>" not in run_now_command
    assert "--run-profile-id profile-1" in run_now_command


def test_linux_export_rejects_internal_runner_profiles(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_runner="internal")

    with pytest.raises(ValueError, match="Set Schedule Runner to External before exporting this profile."):
        service.generate_cron_line(profile, "/usr/local/bin/python3")


def test_paths_with_spaces_are_quoted_correctly(tmp_path: Path) -> None:
    service = ExternalSchedulerService(
        app_script_path="/opt/heisenberg backup/app.py",
        logs_dir=tmp_path / "logs",
        exports_dir=tmp_path / "exports" / "scheduler",
    )
    profile = build_profile(tmp_path, name="Primary DB")

    windows_command = service.generate_windows_task_command(
        profile,
        Path(r"C:\Program Files\Python 3.12\python.exe"),
    )
    cron_line = service.generate_cron_line(
        profile,
        "/usr/local/bin/python 3.12",
    )

    assert r'\"C:\Program Files\Python 3.12\python.exe\"' in windows_command
    assert "'/usr/local/bin/python 3.12'" in cron_line
    assert "'/opt/heisenberg backup/app.py'" in cron_line


def test_save_windows_exports_writes_register_and_run_now_files(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)

    paths = service.save_windows_exports(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert [path.name for path in paths] == [
        "Primary_DB_register_windows_task.cmd",
        "Primary_DB_run_now.cmd",
    ]
    assert "schtasks /Create" in paths[0].read_text(encoding="utf-8")
    assert "schtasks /Create" not in paths[1].read_text(encoding="utf-8")


def test_save_linux_exports_writes_cron_and_run_now_files(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)

    paths = service.save_linux_exports(profile, "/usr/local/bin/python3")

    assert [path.name for path in paths] == [
        "Primary_DB_linux_cron.txt",
        "Primary_DB_linux_run_now.sh",
    ]
    assert "Register this manually with:" in paths[0].read_text(encoding="utf-8")
    assert paths[1].read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\nset -e\n")


def test_disabled_profile_cannot_export(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, enabled=False)

    with pytest.raises(ValueError, match="Disabled profiles cannot be exported"):
        service.validate_exportable(profile)


def test_manual_schedule_cannot_export(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="manual",
        schedule_time="10:15",
        schedule_enabled=True,
    )

    with pytest.raises(ValueError, match="Manual schedules cannot be exported"):
        service.validate_exportable(profile)


def test_safe_task_name_sanitization(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    assert service.safe_profile_name('Prod: DB / Daily*Backup?') == "Prod_DB_Daily_Backup"
