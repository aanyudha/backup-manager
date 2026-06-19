"""Tests for the restore worker lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QCoreApplication

from app.models.restore_result import RestoreResult
from app.workers.restore_worker import RestoreWorker


class StubRestoreService:
    """Small stub used to drive worker tests."""

    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def _result(self, restore_type: str) -> RestoreResult:
        started_at = datetime.now(timezone.utc)
        finished_at = started_at + timedelta(seconds=1)
        return RestoreResult(
            success=True,
            restore_type=restore_type,
            source="source",
            destination="destination",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=1.0,
            message="restore complete",
            log_file="logs/restore.log",
        )

    def restore_mysql(self, *, progress=None, **kwargs):  # type: ignore[no-untyped-def]
        if self.should_fail:
            raise RuntimeError("boom")
        if progress:
            progress("step 1")
        return self._result("mysql")

    def restore_folder(self, *, progress=None, **kwargs):  # type: ignore[no-untyped-def]
        if self.should_fail:
            raise RuntimeError("boom")
        if progress:
            progress("step 1")
        return self._result("folder")


def test_restore_worker_emits_started_progress_and_finished() -> None:
    """Worker should emit the normal success lifecycle signals."""
    app = QCoreApplication.instance() or QCoreApplication([])
    _ = app
    worker = RestoreWorker(StubRestoreService(), "mysql", {"database": "appdb"})
    events: dict[str, object] = {"started": [], "progress": [], "finished": []}

    worker.started.connect(lambda value: events["started"].append(value))
    worker.progress.connect(lambda value: events["progress"].append(value))
    worker.finished.connect(lambda value: events["finished"].append(value))

    worker.run()

    assert events["started"] == ["mysql"]
    assert events["progress"] == ["step 1"]
    assert len(events["finished"]) == 1
    assert events["finished"][0].success is True


def test_restore_worker_emits_failed_on_exception() -> None:
    """Worker should surface raised exceptions through the failed signal."""
    app = QCoreApplication.instance() or QCoreApplication([])
    _ = app
    worker = RestoreWorker(StubRestoreService(should_fail=True), "folder", {"source": "a", "destination": "b"})
    failures: list[str] = []

    worker.failed.connect(failures.append)

    worker.run()

    assert failures == ["boom"]
