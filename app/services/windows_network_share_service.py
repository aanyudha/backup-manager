"""Helpers for pre-connecting Windows UNC shares with ``net use``."""

from __future__ import annotations

from dataclasses import dataclass
import getpass
import os
import subprocess

from app.services.platform_service import PlatformService

MASKED_PASSWORD = "********"
SMB_CONFLICT_PATTERNS = (
    "multiple connections to a server or shared resource by the same user",
    "using more than one user name",
    "system error 1219",
    "credential conflict",
)


@dataclass(frozen=True)
class NetUseDiagnostic:
    """Structured ``net use`` execution details with masked output."""

    success: bool
    action: str
    target: str
    share_root: str | None
    returncode: int
    command_preview: str
    stdout: str
    stderr: str
    message: str
    conflict_detected: bool = False


def _clean_text(value: str | None) -> str:
    """Trim a possibly-empty string."""
    return value.strip() if isinstance(value, str) else ""


def _mask_text(value: str, secret: str) -> str:
    """Replace one secret inside command output."""
    if not value:
        return ""
    if secret:
        return value.replace(secret, MASKED_PASSWORD)
    return value


def _qualify_username(username: str, domain: str | None = None) -> str:
    """Build a ``DOMAIN\\user`` login only when needed."""
    cleaned_username = _clean_text(username)
    cleaned_domain = _clean_text(domain)
    if not cleaned_domain or "\\" in cleaned_username or "@" in cleaned_username:
        return cleaned_username
    return f"{cleaned_domain}\\{cleaned_username}"


def extract_unc_share_root(path: str) -> str:
    """Return the ``\\\\server\\share`` portion of a UNC path."""
    cleaned = path.strip()
    if cleaned.startswith("//"):
        raise ValueError(
            "Invalid Windows network path '//server/share'. Use a UNC path like "
            r"'\\server\share\folder'."
        )
    if not cleaned.startswith("\\\\"):
        raise ValueError("Windows network share login requires a UNC path like '\\\\server\\share\\folder'.")

    segments = cleaned[2:].split("\\")
    if len(segments) < 2 or not segments[0].strip() or not segments[1].strip():
        raise ValueError("Windows UNC path must include both server and share names.")
    return f"\\\\{segments[0].strip()}\\{segments[1].strip()}"


def get_current_windows_user() -> str:
    """Return the current Windows login name when possible."""
    try:
        return os.getlogin()
    except Exception:
        return getpass.getuser() or "unavailable"


def has_smb_session_conflict(stdout_text: str, stderr_text: str) -> bool:
    """Return whether ``net use`` output suggests a conflicting SMB session."""
    combined = f"{stdout_text}\n{stderr_text}".lower()
    return any(pattern in combined for pattern in SMB_CONFLICT_PATTERNS)


def build_smb_conflict_guidance(share_root: str) -> str:
    """Return a user-facing suggestion for clearing a conflicting session."""
    return (
        "Existing SMB session conflict detected. Disconnect the existing share session first:\n"
        f"net use {share_root} /delete /y"
    )


def should_connect_to_share(
    path: str,
    destination_type: str,
    username: str | None,
    password: str | None,
    *,
    platform_service: PlatformService | None = None,
) -> bool:
    """Return whether a Windows UNC pre-connect should run."""
    platform_service = platform_service or PlatformService()
    return (
        platform_service.is_windows()
        and destination_type == "network"
        and path.strip().startswith("\\\\")
        and bool(_clean_text(username))
        and bool(password)
    )


def _run_command(
    args: list[str],
    *,
    masked_args: list[str],
    action: str,
    target: str,
    password: str,
    runner,
    share_root: str | None = None,
) -> NetUseDiagnostic:
    """Execute ``net use`` and return a masked diagnostic."""
    completed = runner(args, capture_output=True, text=True, check=False)
    command_preview = " ".join(masked_args)
    stdout_text = _mask_text((completed.stdout or "").strip(), password) or "(empty)"
    stderr_text = _mask_text((completed.stderr or "").strip(), password) or "(empty)"
    conflict_detected = bool(share_root) and has_smb_session_conflict(stdout_text, stderr_text)
    if completed.returncode == 0:
        message = (
            f"Windows network share {action} succeeded for {target}. "
            f"Command: {command_preview} | Exit Code: {completed.returncode} | "
            f"Stdout: {stdout_text} | Stderr: {stderr_text}"
        )
    else:
        message = (
            f"Windows network share {action} failed for {target}. "
            f"Command: {command_preview} | Exit Code: {completed.returncode} | "
            f"Stdout: {stdout_text} | Stderr: {stderr_text}"
        )
    if conflict_detected and share_root:
        message = f"{message}\n{build_smb_conflict_guidance(share_root)}"
    return NetUseDiagnostic(
        success=completed.returncode == 0,
        action=action,
        target=target,
        share_root=share_root,
        returncode=completed.returncode,
        command_preview=command_preview,
        stdout=stdout_text,
        stderr=stderr_text,
        message=message,
        conflict_detected=conflict_detected,
    )


def inspect_net_use(
    share_root: str | None = None,
    *,
    runner=None,
) -> NetUseDiagnostic:
    """Inspect global or per-share ``net use`` state."""
    runner = runner or subprocess.run
    args = ["net", "use"]
    target = "(all connections)"
    if share_root:
        args.append(share_root)
        target = share_root
    return _run_command(
        args,
        masked_args=args,
        action="inspect",
        target=target,
        share_root=share_root,
        password="",
        runner=runner,
    )


def connect_share_diagnostic(
    path: str,
    username: str,
    password: str,
    domain: str | None = None,
    *,
    runner=None,
) -> NetUseDiagnostic:
    """Connect a UNC share with ``net use`` and keep detailed diagnostics."""
    runner = runner or subprocess.run
    share_root = extract_unc_share_root(path)
    qualified_username = _qualify_username(username, domain)
    args = ["net", "use", share_root, f"/user:{qualified_username}", password]
    masked_args = ["net", "use", share_root, f"/user:{qualified_username}", MASKED_PASSWORD]
    return _run_command(
        args,
        masked_args=masked_args,
        action="connect",
        target=share_root,
        share_root=share_root,
        password=password,
        runner=runner,
    )


def disconnect_share_diagnostic(
    path: str,
    *,
    runner=None,
) -> NetUseDiagnostic:
    """Disconnect a UNC share with ``net use /delete`` and keep detailed diagnostics."""
    runner = runner or subprocess.run
    share_root = extract_unc_share_root(path)
    args = ["net", "use", share_root, "/delete", "/y"]
    return _run_command(
        args,
        masked_args=args,
        action="disconnect",
        target=share_root,
        share_root=share_root,
        password="",
        runner=runner,
    )


def connect_share(
    path: str,
    username: str,
    password: str,
    domain: str | None = None,
    *,
    runner=None,
) -> tuple[bool, str]:
    """Connect a UNC share with ``net use``."""
    diagnostic = connect_share_diagnostic(path, username, password, domain, runner=runner)
    return diagnostic.success, diagnostic.message


def disconnect_share(
    path: str,
    *,
    runner=None,
) -> tuple[bool, str]:
    """Disconnect a UNC share with ``net use /delete``."""
    diagnostic = disconnect_share_diagnostic(path, runner=runner)
    return diagnostic.success, diagnostic.message
