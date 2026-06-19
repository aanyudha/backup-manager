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


def test_windows_daily_schtasks_command(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="daily", schedule_time="10:15")

    command = service.generate_windows_task_command(
        profile,
        Path(r"C:\Program Files\Heisenberg Backup Manager\HeisenbergBackupManager.exe"),
    )

    assert '/SC DAILY' in command
    assert '/ST 10:15' in command
    assert '--run-profile-id profile-1' in command


def test_windows_weekly_schtasks_command(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="weekly",
        schedule_time="09:05",
        schedule_days_of_week=[0, 2, 4],
    )

    command = service.generate_windows_task_command(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert '/SC WEEKLY' in command
    assert '/D MON,WED,FRI' in command
    assert '/ST 09:05' in command


def test_windows_monthly_schtasks_command(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(
        tmp_path,
        schedule_type="monthly",
        schedule_time="23:45",
        schedule_day_of_month=19,
    )

    command = service.generate_windows_task_command(profile, Path(r"C:\HBM\HeisenbergBackupManager.exe"))

    assert '/SC MONTHLY' in command
    assert '/D 19' in command
    assert '/ST 23:45' in command


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
