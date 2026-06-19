"""Scheduling rules for the internal backup scheduler."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from app.models.profile import Profile
from app.models.schedule import WEEKDAY_NAMES
from app.repositories.scheduler_state_repository import SchedulerStateRepository


class SchedulerService:
    """Determine due schedules and track completed schedule windows."""

    def __init__(self, state_repository: SchedulerStateRepository) -> None:
        self.state_repository = state_repository

    def is_due(self, profile: Profile, now: datetime) -> bool:
        """Return whether the given profile should run now."""
        candidate = self._current_window(profile, now)
        if candidate is None:
            return False
        return self._is_due_for_candidate(profile, candidate, now)

    def mark_run(self, profile: Profile, run_time: datetime) -> datetime:
        """Record one scheduled run attempt."""
        return self.state_repository.set_last_run(profile.id, run_time)

    def get_schedule_summary(self, profile: Profile) -> str:
        """Return a human-readable description of the profile schedule."""
        if not profile.schedule_enabled:
            return "Disabled"
        if profile.schedule_type == "manual":
            return "Manual only"
        if profile.schedule_type == "daily":
            return f"Daily at {profile.schedule_time}"
        if profile.schedule_type == "weekly":
            days = ", ".join(WEEKDAY_NAMES[day] for day in profile.schedule_days_of_week)
            return f"Weekly on {days} at {profile.schedule_time}"
        effective_last_day_note = ""
        if profile.schedule_day_of_month and profile.schedule_day_of_month > 28:
            effective_last_day_note = " (or last day)"
        return (
            f"Monthly on day {profile.schedule_day_of_month}{effective_last_day_note} "
            f"at {profile.schedule_time}"
        )

    def get_next_run(self, profile: Profile, now: datetime) -> datetime | None:
        """Return the next scheduled run time for a profile."""
        if not self._is_schedulable(profile):
            return None

        if profile.schedule_type == "daily":
            return self._next_daily_run(profile, now)
        if profile.schedule_type == "weekly":
            return self._next_weekly_run(profile, now)
        if profile.schedule_type == "monthly":
            return self._next_monthly_run(profile, now)
        return None

    def _is_schedulable(self, profile: Profile) -> bool:
        return (
            profile.enabled
            and profile.schedule_enabled
            and profile.schedule_runner == "internal"
            and profile.schedule_type != "manual"
        )

    def _time_value(self, profile: Profile) -> time:
        hour_text, minute_text = (profile.schedule_time or "00:00").split(":")
        return time(hour=int(hour_text), minute=int(minute_text))

    def _candidate_for_date(self, target_date: date, schedule_time: time, now: datetime) -> datetime:
        return now.replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=schedule_time.hour,
            minute=schedule_time.minute,
            second=0,
            microsecond=0,
        )

    def _current_window(self, profile: Profile, now: datetime) -> datetime | None:
        if not self._is_schedulable(profile):
            return None

        schedule_time = self._time_value(profile)
        if profile.schedule_type == "daily":
            return self._candidate_for_date(now.date(), schedule_time, now)
        if profile.schedule_type == "weekly":
            if now.weekday() not in profile.schedule_days_of_week:
                return None
            return self._candidate_for_date(now.date(), schedule_time, now)
        if profile.schedule_type == "monthly":
            configured_day = profile.schedule_day_of_month or 1
            last_day = monthrange(now.year, now.month)[1]
            effective_day = min(configured_day, last_day)
            if now.day != effective_day:
                return None
            return self._candidate_for_date(now.date(), schedule_time, now)
        return None

    def _has_run_candidate(self, profile: Profile, candidate: datetime) -> bool:
        last_run = self.state_repository.get_last_run(profile.id)
        return last_run is not None and last_run >= candidate

    def _is_due_for_candidate(self, profile: Profile, candidate: datetime, now: datetime) -> bool:
        if now < candidate or self._has_run_candidate(profile, candidate):
            return False
        if profile.run_if_missed:
            return True
        return now.replace(second=0, microsecond=0) == candidate

    def _next_daily_run(self, profile: Profile, now: datetime) -> datetime:
        schedule_time = self._time_value(profile)
        today = self._candidate_for_date(now.date(), schedule_time, now)
        if today >= now or self._is_due_for_candidate(profile, today, now):
            return today
        return self._candidate_for_date(now.date() + timedelta(days=1), schedule_time, now)

    def _next_weekly_run(self, profile: Profile, now: datetime) -> datetime:
        schedule_time = self._time_value(profile)
        for offset in range(0, 14):
            target_date = now.date() + timedelta(days=offset)
            if target_date.weekday() not in profile.schedule_days_of_week:
                continue
            candidate = self._candidate_for_date(target_date, schedule_time, now)
            if offset == 0 and candidate < now and not self._is_due_for_candidate(profile, candidate, now):
                continue
            return candidate
        raise RuntimeError("Weekly schedules should always resolve within two weeks.")

    def _next_monthly_run(self, profile: Profile, now: datetime) -> datetime:
        schedule_time = self._time_value(profile)
        configured_day = profile.schedule_day_of_month or 1
        year = now.year
        month = now.month
        for _ in range(0, 24):
            last_day = monthrange(year, month)[1]
            effective_day = min(configured_day, last_day)
            target_date = date(year, month, effective_day)
            candidate = self._candidate_for_date(target_date, schedule_time, now)
            if candidate >= now or (
                target_date == now.date() and self._is_due_for_candidate(profile, candidate, now)
            ):
                return candidate
            month += 1
            if month > 12:
                month = 1
                year += 1
        raise RuntimeError("Monthly schedules should resolve within two years.")
