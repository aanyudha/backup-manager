"""Tests for Windows UNC share pre-connect helpers."""

from __future__ import annotations

import subprocess

from app.services.platform_service import PlatformService
from app.services.windows_network_share_service import (
    build_smb_conflict_guidance,
    connect_share,
    extract_unc_share_root,
    has_smb_session_conflict,
    should_connect_to_share,
)


def test_extract_unc_share_root_returns_server_and_share_only() -> None:
    assert extract_unc_share_root(r"\\192.168.23.6\Backup\1.55\folder") == r"\\192.168.23.6\Backup"


def test_connect_share_builds_net_use_command_and_masks_password() -> None:
    seen: list[list[str]] = []

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    ok, message = connect_share(
        r"\\192.168.23.6\Backup\1.55\folder",
        "backup-user",
        "super-secret",
        "WORKGROUP",
        runner=fake_run,
    )

    assert ok is True
    assert seen == [[
        "net",
        "use",
        r"\\192.168.23.6\Backup",
        r"/user:WORKGROUP\backup-user",
        "super-secret",
    ]]
    assert "super-secret" not in message
    assert "********" in message
    assert "Exit Code: 0" in message


def test_connect_share_failure_masks_stdout_and_stderr() -> None:
    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args,
            returncode=59,
            stdout="password super-secret rejected",
            stderr="super-secret is invalid",
        )

    ok, message = connect_share(
        r"\\192.168.23.6\Backup\1.55\folder",
        "backup-user",
        "super-secret",
        runner=fake_run,
    )

    assert ok is False
    assert "super-secret" not in message
    assert "********" in message
    assert "Exit Code: 59" in message


def test_conflict_message_detection_builds_disconnect_guidance() -> None:
    stdout_text = (
        "System error 1219 has occurred.\n"
        "Multiple connections to a server or shared resource by the same user are not allowed."
    )

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args, returncode=1219, stdout=stdout_text, stderr="")

    ok, message = connect_share(
        r"\\192.168.23.6\Backup\1.55\folder",
        "backup-user",
        "super-secret",
        runner=fake_run,
    )

    assert ok is False
    assert has_smb_session_conflict(stdout_text, "")
    assert build_smb_conflict_guidance(r"\\192.168.23.6\Backup") == (
        "Existing SMB session conflict detected. Disconnect the existing share session first:\n"
        r"net use \\192.168.23.6\Backup /delete /y"
    )
    assert "Existing SMB session conflict detected." in message
    assert r"net use \\192.168.23.6\Backup /delete /y" in message


def test_should_connect_to_share_is_false_for_non_windows_hosts() -> None:
    platform_service = PlatformService()
    platform_service.is_windows = lambda: False  # type: ignore[method-assign]

    assert should_connect_to_share(
        r"\\192.168.23.6\Backup\1.55\folder",
        "network",
        "backup-user",
        "secret",
        platform_service=platform_service,
    ) is False
