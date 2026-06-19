"""Qt worker for the internal backup scheduler."""

from __future__ import annotations

from datetime import datetime
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from app.services.backup_service import BackupService
from app.services.log_service import LogService
from app.services.scheduler_service import SchedulerService


class SchedulerWorker(QObject):
    """Check for due schedules and run them sequentially."""

    started = Signal()
    progress = Signal(str)
    profile_completed = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(
        self,
        backup_service: BackupService,
        scheduler_service: SchedulerService,
        log_service: LogService,
        *,
        interval_seconds: int = 60,
        run_once: bool = False,
    ) -> None:
        super().__init__()
        self.backup_service = backup_service
        self.scheduler_service = scheduler_service
        self.log_service = log_service
        self.interval_seconds = interval_seconds
        self.run_once = run_once
        self._stop_event = Event()
        self._wake_event = Event()

    @Slot()
    def run(self) -> None:
        """Start the scheduler loop."""
        self.started.emit()
        try:
            start_message = "Scheduler started." if not self.run_once else "Running due schedules once."
            self._emit_message(start_message)
            self.log_service.log_scheduler(start_message)

            while not self._stop_event.is_set():
                self._process_due_profiles(notify_when_idle=self.run_once)
                if self.run_once:
                    break
                self._wake_event.wait(self.interval_seconds)
                self._wake_event.clear()

            stop_message = "Scheduler stopped." if not self.run_once else "Due schedule check finished."
            self._emit_message(stop_message)
            self.log_service.log_scheduler(stop_message)
        except Exception as exc:
            self.failed.emit(str(exc))
            self.log_service.log_scheduler(f"Scheduler failed: {exc}")
        finally:
            self.finished.emit()

    @Slot()
    def stop(self) -> None:
        """Request that the scheduler loop stop."""
        self._stop_event.set()
        self._wake_event.set()

    def request_run_due_now(self) -> None:
        """Wake the worker so it checks due profiles immediately."""
        self._wake_event.set()

    def _process_due_profiles(self, *, notify_when_idle: bool) -> None:
        profiles = sorted(self.backup_service.list_profiles(), key=lambda item: item.name.lower())
        now = datetime.now().astimezone()
        due_profiles = [profile for profile in profiles if self.scheduler_service.is_due(profile, now)]

        if not due_profiles:
            if notify_when_idle:
                self._emit_message("No due schedules found.")
            return

        for profile in due_profiles:
            if self._stop_event.is_set():
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
                result = self.backup_service.run_profile(profile.id, progress=self.progress.emit)
                self._emit_message(f"Scheduled backup finished for '{profile.name}': {result.message}")
                self.log_service.log_scheduler(
                    f"Backup finished for '{profile.name}' with success={result.success}: {result.message}"
                )
            except Exception as exc:
                self._emit_message(f"Skipped profile '{profile.name}': {exc}")
                self.log_service.log_scheduler(f"Skipped profile '{profile.name}': {exc}")
            finally:
                self.scheduler_service.mark_run(profile, scheduled_window)
                self.profile_completed.emit(profile.id)

    def _emit_message(self, message: str) -> None:
        self.progress.emit(message)
