"""Qt worker for background restore execution."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.models.restore_result import RestoreResult
from app.services.restore_service import RestoreService


class RestoreWorker(QObject):
    """Run one restore operation in a background thread."""

    started = Signal(str)
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, restore_service: RestoreService, restore_type: str, payload: dict[str, object]) -> None:
        super().__init__()
        self.restore_service = restore_service
        self.restore_type = restore_type
        self.payload = payload

    @Slot()
    def run(self) -> None:
        """Execute the restore and emit worker signals."""
        self.started.emit(self.restore_type)
        try:
            if self.restore_type == "mysql":
                result: RestoreResult = self.restore_service.restore_mysql(
                    progress=self.progress.emit,
                    **self.payload,
                )
            elif self.restore_type == "folder":
                result = self.restore_service.restore_folder(
                    progress=self.progress.emit,
                    **self.payload,
                )
            else:
                raise RuntimeError(f"Unsupported restore type: {self.restore_type}")
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
