"""Diagnose Windows UNC session state and write access for one destination."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.path_validation_service import PathValidationService
from app.services.windows_network_share_service import (
    connect_share_diagnostic,
    disconnect_share_diagnostic,
    extract_unc_share_root,
    get_current_windows_user,
    inspect_net_use,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for UNC session debugging."""
    parser = argparse.ArgumentParser(
        description="Diagnose SMB session state and write access for a UNC destination.",
    )
    parser.add_argument("unc_path", help=r'UNC destination path, for example "\\server\share\folder"')
    parser.add_argument("--username", help="Windows share username")
    parser.add_argument("--password", help="Windows share password")
    parser.add_argument("--domain", help="Optional Windows domain/workgroup")
    return parser


def _emit(text: str, *, out) -> None:
    print(text, file=out)


def _emit_failure(step: str, *, out, traceback_text: str | None = None) -> None:
    _emit(f"Failing Step: {step}", out=out)
    if traceback_text:
        _emit("Traceback:", out=out)
        _emit(traceback_text.rstrip(), out=out)
    else:
        _emit("Traceback: none (command returned a non-zero exit code)", out=out)


def run_debug_session(
    unc_path: str,
    *,
    username: str | None = None,
    password: str | None = None,
    domain: str | None = None,
    runner=None,
    out=None,
) -> int:
    """Run the UNC diagnostic flow and write a human-readable report."""
    out = out or sys.stdout
    _emit(f"UNC Path: {unc_path}", out=out)
    _emit(f"Current Windows User: {get_current_windows_user()}", out=out)

    try:
        share_root = extract_unc_share_root(unc_path)
    except Exception:
        _emit_failure("extract share root", out=out, traceback_text=traceback.format_exc())
        return 1

    _emit(f"Share Root: {share_root}", out=out)

    try:
        inspect_all = inspect_net_use(runner=runner)
    except Exception:
        _emit_failure("inspect all SMB sessions", out=out, traceback_text=traceback.format_exc())
        return 1
    _emit("[net use]", out=out)
    _emit(inspect_all.message, out=out)

    try:
        inspect_share = inspect_net_use(share_root, runner=runner)
    except Exception:
        _emit_failure(f"inspect SMB session for {share_root}", out=out, traceback_text=traceback.format_exc())
        return 1
    _emit(f"[net use {share_root}]", out=out)
    _emit(inspect_share.message, out=out)

    if username and password:
        try:
            disconnect_result = disconnect_share_diagnostic(unc_path, runner=runner)
        except Exception:
            _emit_failure("disconnect existing SMB session", out=out, traceback_text=traceback.format_exc())
            return 1
        _emit(f"[net use {share_root} /delete /y]", out=out)
        _emit(disconnect_result.message, out=out)

        try:
            connect_result = connect_share_diagnostic(
                unc_path,
                username,
                password,
                domain,
                runner=runner,
            )
        except Exception:
            _emit_failure("connect share with provided credentials", out=out, traceback_text=traceback.format_exc())
            return 1
        _emit(f"[net use {share_root} /user:<masked> <masked>]", out=out)
        _emit(connect_result.message, out=out)
        if not connect_result.success:
            _emit_failure("connect share with provided credentials", out=out)
            return 1

    try:
        writable, probe_report = PathValidationService.ensure_destination_writable(
            unc_path,
            destination_type="network",
        )
    except Exception:
        _emit_failure("destination write probe", out=out, traceback_text=traceback.format_exc())
        return 1

    _emit("[destination write probe]", out=out)
    _emit(probe_report, out=out)
    if not writable:
        _emit_failure("destination write probe", out=out)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_debug_session(
        args.unc_path,
        username=args.username,
        password=args.password,
        domain=args.domain,
    )


if __name__ == "__main__":
    raise SystemExit(main())
