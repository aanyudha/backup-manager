"""Tests for the internal scheduler worker."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.workers.scheduler_worker import SchedulerWorker


class StubBackupService:
    """Minimal backup service for scheduler worker tests."""

    def __init__(self, profiles: list[FolderBackupProfile]) -> None:
        self._profiles = profiles
        self.run_profile_calls: list[str] = []

    def list_profiles(self) -> list[FolderBackupProfile]:
        return self._profiles

    @staticmethod
    def is_running() -> bool:
        return False

    def run_profile(self, profile_id: str, progress=None) -> BackupResult:
        self.run_profile_calls.append(profile_id)
        now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
        return BackupResult(
            success=True,
            backup_type="folder",
            profile_id=profile_id,
            profile_name=profile_id,
            started_at=now,
            finished_at=now,
            exit_code=0,
            message="Completed",
            log_file=None,
            output_file=None,
        )


class StubSchedulerService:
    """Scheduler service stub that tracks which profiles were evaluated."""

    def __init__(self) -> None:
        self.is_due_calls: list[str] = []
        self.mark_run_calls: list[str] = []

    def is_due(self, profile: FolderBackupProfile, now: datetime) -> bool:
        self.is_due_calls.append(profile.id)
        return True

    @staticmethod
    def get_next_run(profile: FolderBackupProfile, now: datetime) -> datetime:
        return now

    def mark_run(self, profile: FolderBackupProfile, run_time: datetime) -> datetime:
        self.mark_run_calls.append(profile.id)
        return run_time


class StubLogService:
    """Collect scheduler log messages."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def log_scheduler(self, message: str) -> None:
        self.messages.append(message)


def build_profile(*, profile_id: str, schedule_runner: str) -> FolderBackupProfile:
    """Create a minimal folder profile for worker tests."""
    return FolderBackupProfile(
        id=profile_id,
        name=profile_id,
        source="C:/src",
        destination="C:/dst",
        schedule_enabled=True,
        schedule_runner=schedule_runner,  # type: ignore[arg-type]
        schedule_type="daily",
        schedule_time="10:00",
    )


def test_internal_scheduler_worker_ignores_external_profiles() -> None:
    backup_service = StubBackupService(
        [
            build_profile(profile_id="internal-profile", schedule_runner="internal"),
            build_profile(profile_id="external-profile", schedule_runner="external"),
        ]
    )
    scheduler_service = StubSchedulerService()
    log_service = StubLogService()
    worker = SchedulerWorker(backup_service, scheduler_service, log_service, run_once=True)

    worker._process_due_profiles(notify_when_idle=False)

    assert scheduler_service.is_due_calls == ["internal-profile"]
    assert backup_service.run_profile_calls == ["internal-profile"]
    assert scheduler_service.mark_run_calls == ["internal-profile"]
