"""Qt worker for background backup execution."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.models.result import BackupResult
from app.services.backup_service import BackupService


class BackupWorker(QObject):
    """Run one backup in a background thread."""

    started = Signal(str)
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, backup_service: BackupService, profile_id: str) -> None:
        super().__init__()
        self.backup_service = backup_service
        self.profile_id = profile_id

    @Slot()
    def run(self) -> None:
        """Execute the backup and emit worker signals."""
        self.started.emit(self.profile_id)
        try:
            result: BackupResult = self.backup_service.run_profile(
                self.profile_id,
                progress=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
