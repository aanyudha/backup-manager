"""Headless internal scheduler runner for service-style execution."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import TextIO

from app.models.schedule import ScheduleRunner
from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.scheduler_service import SchedulerService


class SchedulerServiceRunner:
    """Run the internal scheduler loop without Qt."""

    def __init__(
        self,
        backup_service: BackupService,
        scheduler_service: SchedulerService,
        log_service: LogService,
        *,
        interval_seconds: int = 60,
        stdout: TextIO | None = None,
        runner_mode: ScheduleRunner = "service",
    ) -> None:
        self.backup_service = backup_service
        self.scheduler_service = scheduler_service
        self.log_service = log_service
        self.interval_seconds = interval_seconds
        self.stdout = stdout or sys.stdout
        self.runner_mode = runner_mode
        self._stop_requested = False

    def stop(self) -> None:
        """Request that the loop stop after the current iteration."""
        self._stop_requested = True

    def run_forever(self) -> None:
        """Run the internal scheduler until interrupted."""
        self._emit_message("Scheduler service started.")
        self.log_service.log_scheduler("Scheduler service started.")
        try:
            while not self._stop_requested:
                self.process_due_profiles(notify_when_idle=False)
                if self._stop_requested:
                    break
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            self._emit_message("Scheduler service interrupted.")
            self.log_service.log_scheduler("Scheduler service interrupted.")
        finally:
            self._emit_message("Scheduler service stopped.")
            self.log_service.log_scheduler("Scheduler service stopped.")

    def process_due_profiles(self, *, notify_when_idle: bool) -> None:
        """Run due internal profiles sequentially."""
        profiles = sorted(self.backup_service.list_profiles(), key=lambda item: item.name.lower())
        now = datetime.now().astimezone()
        due_profiles = [
            profile
            for profile in profiles
            if profile.schedule_runner == self.runner_mode
            and self.scheduler_service.is_due(profile, now, runner_mode=self.runner_mode)
        ]

        if not due_profiles:
            if notify_when_idle:
                self._emit_message("No due schedules found.")
            return

        for profile in due_profiles:
            if self._stop_requested:
                return

            scheduled_window = self.scheduler_service.get_next_run(profile, now) or datetime.now().astimezone()
            self._emit_message(f"Due profile found: '{profile.name}'.")
            self.log_service.log_scheduler(f"Due profile found: '{profile.name}'.")

            if self.backup_service.is_running():
                wait_message = f"Backup already running. Waiting for slot before scheduled run for '{profile.name}'."
                self._emit_message(wait_message)
                self.log_service.log_scheduler(wait_message)

            self._emit_message(f"Scheduled backup started for '{profile.name}'.")
            self.log_service.log_scheduler(f"Backup started for '{profile.name}'.")
            try:
                result = self.backup_service.run_profile(profile.id, progress=self._emit_message)
                self._emit_message(f"Scheduled backup finished for '{profile.name}': {result.message}")
                self.log_service.log_scheduler(
                    f"Backup finished for '{profile.name}' with success={result.success}: {result.message}"
                )
            except Exception as exc:
                self._emit_message(f"Skipped profile '{profile.name}': {exc}")
                self.log_service.log_scheduler(f"Skipped profile '{profile.name}': {exc}")
            finally:
                self.scheduler_service.mark_run(profile, scheduled_window)

    def _emit_message(self, message: str) -> None:
        self.stdout.write(f"{message}\n")
        self.stdout.flush()
