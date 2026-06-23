"""Tests for the UNC session debugging script."""

from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys


def load_module():  # type: ignore[no-untyped-def]
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "debug_unc_session.py"
    spec = importlib.util.spec_from_file_location("debug_unc_session", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load debug_unc_session.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("debug_unc_session", module)
    spec.loader.exec_module(module)
    return module


def test_debug_command_masks_password(monkeypatch) -> None:
    module = load_module()
    output = StringIO()

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(module, "get_current_windows_user", lambda: "tester")
    monkeypatch.setattr(
        module.PathValidationService,
        "ensure_destination_writable",
        staticmethod(lambda path, destination_type="unknown": (True, "write probe ok")),
    )

    exit_code = module.run_debug_session(
        r"\\192.168.23.6\Backup\1.55\folder",
        username="backup-user",
        password="super-secret",
        domain="WORKGROUP",
        runner=fake_run,
        out=output,
    )

    rendered = output.getvalue()
    assert exit_code == 0
    assert "super-secret" not in rendered
    assert "********" in rendered


def test_net_use_attempted_before_write_probe(monkeypatch) -> None:
    module = load_module()
    output = StringIO()
    order: list[str] = []

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        order.append("net_use")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    def fake_probe(path, destination_type="unknown"):  # type: ignore[no-untyped-def]
        order.append("write_probe")
        return True, "write probe ok"

    monkeypatch.setattr(module, "get_current_windows_user", lambda: "tester")
    monkeypatch.setattr(
        module.PathValidationService,
        "ensure_destination_writable",
        staticmethod(fake_probe),
    )

    exit_code = module.run_debug_session(
        r"\\192.168.23.6\Backup\1.55\folder",
        username="backup-user",
        password="super-secret",
        runner=fake_run,
        out=output,
    )

    assert exit_code == 0
    assert order == ["net_use", "net_use", "net_use", "net_use", "write_probe"]
