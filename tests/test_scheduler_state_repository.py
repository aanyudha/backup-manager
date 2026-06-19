"""Tests for scheduler runtime state persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.repositories.scheduler_state_repository import SchedulerStateRepository


def test_scheduler_state_repository_creates_state_file(tmp_path: Path) -> None:
    repository = SchedulerStateRepository(tmp_path / "config")

    assert repository.state_path.exists()
    assert repository.load() == {}


def test_scheduler_state_repository_saves_and_loads_last_run(tmp_path: Path) -> None:
    repository = SchedulerStateRepository(tmp_path / "config")
    run_time = datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc)

    repository.set_last_run("profile-1", run_time)

    assert repository.get_last_run("profile-1") == run_time
    payload = json.loads(repository.state_path.read_text(encoding="utf-8"))
    assert payload["last_runs"]["profile-1"] == run_time.isoformat()


def test_scheduler_state_repository_writes_atomically_without_tmp_files_left_behind(tmp_path: Path) -> None:
    repository = SchedulerStateRepository(tmp_path / "config")
    repository.set_last_run("profile-1", datetime(2026, 6, 19, 10, 0, tzinfo=timezone.utc))

    assert list(repository.config_dir.glob("*.tmp")) == []
