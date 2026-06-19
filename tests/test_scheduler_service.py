"""Tests for internal scheduler due-calculation rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.profile import MySQLBackupProfile
from app.repositories.scheduler_state_repository import SchedulerStateRepository
from app.services.scheduler_service import SchedulerService


def build_profile(
    tmp_path: Path,
    *,
    enabled: bool = True,
    schedule_enabled: bool = True,
    schedule_type: str = "daily",
    schedule_time: str | None = "10:00",
    schedule_days_of_week: list[int] | None = None,
    schedule_day_of_month: int | None = None,
    run_if_missed: bool = True,
) -> MySQLBackupProfile:
    """Create a valid MySQL profile with scheduler fields."""
    fake_dump = tmp_path / "mysqldump"
    fake_dump.write_text("", encoding="utf-8")
    return MySQLBackupProfile(
        name="Primary DB",
        host="127.0.0.1",
        port=3306,
        username="root",
        password="",
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
        run_if_missed=run_if_missed,
    )


def build_service(tmp_path: Path) -> SchedulerService:
    """Create a scheduler service with isolated state."""
    return SchedulerService(SchedulerStateRepository(tmp_path / "config"))


def test_daily_schedule_due_after_scheduled_time(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)
    now = datetime(2026, 6, 19, 10, 5, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is True


def test_daily_schedule_not_due_before_scheduled_time(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)
    now = datetime(2026, 6, 19, 9, 59, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is False


def test_daily_schedule_not_due_twice_same_day(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path)
    scheduled_window = datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)
    service.mark_run(profile, scheduled_window)

    assert service.is_due(profile, scheduled_window + timedelta(minutes=30)) is False


def test_weekly_schedule_due_on_selected_day(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="weekly", schedule_days_of_week=[4])
    now = datetime(2026, 6, 19, 10, 15, tzinfo=timezone.utc)

    assert now.weekday() == 4
    assert service.is_due(profile, now) is True


def test_weekly_schedule_not_due_on_unselected_day(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="weekly", schedule_days_of_week=[0])
    now = datetime(2026, 6, 19, 10, 15, tzinfo=timezone.utc)

    assert now.weekday() == 4
    assert service.is_due(profile, now) is False


def test_monthly_schedule_due_on_selected_day(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="monthly", schedule_day_of_month=19)
    now = datetime(2026, 6, 19, 10, 30, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is True


def test_monthly_schedule_runs_on_last_day_when_day_exceeds_month_length(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="monthly", schedule_day_of_month=31)
    now = datetime(2026, 4, 30, 10, 1, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is True


def test_run_if_missed_false_only_due_within_exact_minute(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, run_if_missed=False)
    in_window = datetime(2026, 6, 19, 10, 0, 30, tzinfo=timezone.utc)
    missed = datetime(2026, 6, 19, 10, 1, 1, tzinfo=timezone.utc)

    assert service.is_due(profile, in_window) is True
    assert service.is_due(profile, missed) is False


def test_disabled_schedule_is_never_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_enabled=False)
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is False


def test_manual_schedule_is_never_due(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    profile = build_profile(tmp_path, schedule_type="manual", schedule_enabled=True, schedule_time=None)
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)

    assert service.is_due(profile, now) is False


def test_invalid_schedule_time_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        build_profile(tmp_path, schedule_time="25:61")
