"""Tests for platform helpers and transport guardrails."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.robocopy_transport import RobocopyTransport


def test_platform_service_command_exists() -> None:
    """command_exists should detect a known executable."""
    service = PlatformService()

    assert service.command_exists(Path(sys.executable).name)


def test_robocopy_unavailable_on_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """robocopy should not be allowed on Linux."""
    service = PlatformService()
    monkeypatch.setattr(service, "is_windows", lambda: False)
    transport = RobocopyTransport(LogService(tmp_path), service)
    profile = FolderBackupProfile(
        name="Linux Folder",
        source=str(tmp_path / "source"),
        destination=str(tmp_path / "destination"),
        engine="robocopy",
        mode="copy_new_changed",
    )

    with pytest.raises(RuntimeError, match="Windows"):
        transport.build_command(profile)


def build_robocopy_profile(**overrides) -> FolderBackupProfile:
    """Create the mapped-drive robocopy profile used by transport tests."""
    payload = {
        "name": "cctv",
        "source": "D:/CCTV",
        "destination": r"Z:\cctv",
        "destination_type": "network",
        "engine": "robocopy",
        "mode": "copy_new_changed",
    }
    payload.update(overrides)
    return FolderBackupProfile(**payload)


def run_robocopy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    profile: FolderBackupProfile | None = None,
    before_run=None,
):
    """Run the robocopy transport against a mocked subprocess."""
    service = PlatformService()
    monkeypatch.setattr(service, "is_windows", lambda: True)
    transport = RobocopyTransport(LogService(tmp_path / "logs"), service)
    current_profile = profile or build_robocopy_profile()
    captured: dict[str, object] = {}

    def fake_run(command, capture_output=True, text=True, check=False):  # type: ignore[no-untyped-def]
        captured["command"] = command
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("app.transports.robocopy_transport.subprocess.run", fake_run)
    if before_run is not None:
        before_run()
    progress_lines: list[str] = []
    result = transport.run(current_profile, progress_lines.append)
    return result, captured, progress_lines


def test_robocopy_command_passes_source_and_destination_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source and destination must reach robocopy exactly as configured."""
    _, captured, _ = run_robocopy(tmp_path, monkeypatch, returncode=0)

    command = captured["command"]
    assert command[0] == "robocopy"
    assert command[1] == "D:/CCTV"
    assert command[2] == r"Z:\cctv"
    assert not str(command[2]).startswith("\\\\")
    for option in ("/E", "/DCOPY:DA", "/COPY:DAT", "/R:10", "/W:5", "/MT:16", "/FFT", "/ETA"):
        assert option in command


@pytest.mark.parametrize("returncode", [0, 1, 7])
def test_robocopy_exit_code_below_8_is_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
) -> None:
    """Robocopy exit codes 0 through 7 mean the backup succeeded."""
    result, _, progress_lines = run_robocopy(
        tmp_path,
        monkeypatch,
        returncode=returncode,
        stdout="1 file copied",
    )

    assert result.success is True
    assert result.exit_code == returncode
    assert f"Robocopy exit code: {returncode}" in result.message
    assert "Backup completed successfully." in result.message
    assert "Robocopy backup failed." not in result.message
    status_lines = progress_lines[2:]
    assert status_lines == [f"Robocopy exit code: {returncode}", "Backup completed successfully."]
    assert "\n".join(status_lines) == result.message


def test_robocopy_exit_code_8_or_higher_fails_with_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Robocopy failures must surface the exit code and command output."""
    result, _, progress_lines = run_robocopy(
        tmp_path,
        monkeypatch,
        returncode=16,
        stdout="stdout detail",
        stderr="stderr detail",
    )

    assert result.success is False
    assert result.exit_code == 16
    assert "Robocopy backup failed." in result.message
    assert "Exit code: 16" in result.message
    assert "stdout detail" in result.message
    assert "stderr detail" in result.message
    assert "Backup completed successfully." not in result.message
    status_lines = progress_lines[2:]
    assert status_lines[0] == "Robocopy backup failed."
    assert "\n".join(status_lines) == result.message


def test_robocopy_run_does_not_create_destination_and_reports_status_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python must never mkdir the destination before robocopy runs."""
    profile = build_robocopy_profile()

    def forbid_mkdir(*args, **kwargs):
        raise AssertionError("Python mkdir must not run for a robocopy destination.")

    def before_run() -> None:
        monkeypatch.setattr(Path, "mkdir", forbid_mkdir)

    result, _, progress_lines = run_robocopy(
        tmp_path,
        monkeypatch,
        returncode=1,
        profile=profile,
        before_run=before_run,
    )

    assert result.success is True
    assert progress_lines[0] == f"Source: {profile.source}"
    assert progress_lines[1] == f"Destination: {profile.destination}"
    assert progress_lines[2] == "Robocopy exit code: 1"
    assert progress_lines[3] == "Backup completed successfully."
    assert not any("WinError" in line for line in progress_lines)

