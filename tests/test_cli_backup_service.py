"""Tests for CLI backup profile execution."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from io import StringIO
from pathlib import Path

from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.services.cli_backup_service import CliBackupService

APP_MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("app_entry", APP_MODULE_PATH)
assert APP_SPEC is not None and APP_SPEC.loader is not None
app_entry = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app_entry)


class StubBackupService:
    """Small fake backup service for CLI tests."""

    def __init__(
        self,
        *,
        profiles: list[FolderBackupProfile] | None = None,
        result: BackupResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._profiles = profiles or []
        self._result = result
        self._error = error
        self.run_profile_calls: list[str] = []

    def list_profiles(self) -> list[FolderBackupProfile]:
        return self._profiles

    def run_profile(self, profile_id: str) -> BackupResult:
        self.run_profile_calls.append(profile_id)
        if self._error is not None:
            raise self._error
        if self._result is None:
            raise AssertionError("Expected a result for this test.")
        return self._result


def build_result(*, success: bool) -> BackupResult:
    """Create a stable backup result for CLI assertions."""
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    return BackupResult(
        success=success,
        backup_type="folder",
        profile_id="profile-1",
        profile_name="Documents",
        started_at=now,
        finished_at=now,
        exit_code=0 if success else 2,
        message="Completed" if success else "Backup failed",
        log_file=None,
        output_file=None,
    )


def build_profile() -> FolderBackupProfile:
    """Create a folder profile for lookup tests."""
    return FolderBackupProfile(
        id="profile-1",
        name="Documents",
        source="C:/src",
        destination="C:/dst",
    )


def test_app_cli_args_route_without_starting_ui(monkeypatch) -> None:
    """CLI args should dispatch to CLI mode and skip desktop startup."""
    called: dict[str, object] = {}

    def fake_run_cli_mode(*, run_profile_id: str | None, run_profile_name: str | None) -> int:
        called["profile_id"] = run_profile_id
        called["profile_name"] = run_profile_name
        return 0

    def fail_desktop_start() -> int:
        raise AssertionError("Desktop UI should not start in CLI mode.")

    monkeypatch.setattr(app_entry, "run_cli_mode", fake_run_cli_mode)
    monkeypatch.setattr(app_entry, "start_desktop_app", fail_desktop_start)

    assert app_entry.main(["--run-profile-id", "profile-1"]) == 0
    assert called == {"profile_id": "profile-1", "profile_name": None}


def test_scheduler_service_cli_arg_routes_without_starting_ui(monkeypatch) -> None:
    """Scheduler service mode should skip the desktop UI."""
    called: dict[str, bool] = {"service": False}

    def fake_run_scheduler_service_mode() -> int:
        called["service"] = True
        return 0

    def fail_desktop_start() -> int:
        raise AssertionError("Desktop UI should not start in scheduler service mode.")

    monkeypatch.setattr(app_entry, "run_scheduler_service_mode", fake_run_scheduler_service_mode)
    monkeypatch.setattr(app_entry, "start_desktop_app", fail_desktop_start)

    assert app_entry.main(["--scheduler-service"]) == 0
    assert called["service"] is True


def test_cli_missing_profile_returns_non_zero() -> None:
    """Lookup failures should produce a non-zero exit code."""
    service = CliBackupService(StubBackupService(error=KeyError("Profile missing")))
    output = StringIO()

    exit_code = service.execute(profile_id="missing", stdout=output)

    assert exit_code == 1
    assert "Profile missing" in output.getvalue()


def test_cli_failed_backup_returns_non_zero() -> None:
    """A failed backup result should return a non-zero exit code."""
    service = CliBackupService(StubBackupService(result=build_result(success=False)))
    output = StringIO()

    exit_code = service.execute(profile_id="profile-1", stdout=output)

    assert exit_code == 1
    assert "[FAILED]" in output.getvalue()


def test_cli_profile_name_dispatches_to_backup_service() -> None:
    """Profile names should resolve to ids before execution."""
    backup_service = StubBackupService(
        profiles=[build_profile()],
        result=build_result(success=True),
    )
    service = CliBackupService(backup_service)
    output = StringIO()

    exit_code = service.execute(profile_name="Documents", stdout=output)

    assert exit_code == 0
    assert backup_service.run_profile_calls == ["profile-1"]
    assert "[SUCCESS]" in output.getvalue()
