"""Schedule-related profile fields and helpers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ScheduleType = Literal["manual", "daily", "weekly", "monthly"]
ScheduleRunner = Literal["internal", "external"]
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ScheduleFields(BaseModel):
    """Reusable schedule configuration stored on backup profiles."""

    schedule_enabled: bool = False
    schedule_runner: ScheduleRunner = "internal"
    schedule_type: ScheduleType = "manual"
    schedule_time: str | None = None
    schedule_days_of_week: list[int] = Field(default_factory=list)
    schedule_day_of_month: int | None = None
    run_if_missed: bool = True

    @field_validator("schedule_time")
    @classmethod
    def validate_schedule_time(cls, value: str | None) -> str | None:
        """Normalize and validate HH:MM schedule times."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        parts = cleaned.split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError("Schedule time must use HH:MM format.")
        hour, minute = (int(part) for part in parts)
        if hour not in range(24) or minute not in range(60):
            raise ValueError("Schedule time must use HH:MM format.")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("schedule_days_of_week")
    @classmethod
    def validate_schedule_days_of_week(cls, value: list[int]) -> list[int]:
        """Keep weekday values unique and within the supported range."""
        cleaned = sorted(set(value))
        if any(day < 0 or day > 6 for day in cleaned):
            raise ValueError("Schedule days of week must use values from 0 (Monday) to 6 (Sunday).")
        return cleaned

    @field_validator("schedule_day_of_month")
    @classmethod
    def validate_schedule_day_of_month(cls, value: int | None) -> int | None:
        """Restrict monthly schedules to real calendar day numbers."""
        if value is None:
            return None
        if value < 1 or value > 31:
            raise ValueError("Schedule day of month must be between 1 and 31.")
        return value

    @model_validator(mode="after")
    def validate_schedule_rules(self) -> "ScheduleFields":
        """Require the fields needed by the selected schedule mode."""
        if not self.schedule_enabled or self.schedule_type == "manual":
            return self
        if self.schedule_time is None:
            raise ValueError("Schedule time is required when scheduling is enabled.")
        if self.schedule_type == "weekly" and not self.schedule_days_of_week:
            raise ValueError("Weekly schedules require at least one selected day.")
        if self.schedule_type == "monthly" and self.schedule_day_of_month is None:
            raise ValueError("Monthly schedules require a day of month.")
        return self
