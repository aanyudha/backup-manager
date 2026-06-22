"""Generate service-mode helper files without installing them."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ServiceModeExport:
    """Rendered service helper content for one operating system."""

    windows_task_script: str
    windows_run_now_script: str
    linux_unit: str
    linux_install_script: str


class ServiceModeExportService:
    """Write reviewable helper files for service-style scheduler startup."""

    def __init__(
        self,
        *,
        app_script_path: Path | str | None = None,
        working_directory: Path | str | None = None,
        exports_dir: Path | None = None,
    ) -> None:
        self.app_script_path = Path(app_script_path) if app_script_path is not None else None
        self.working_directory = Path(working_directory) if working_directory is not None else None
        self.exports_dir = exports_dir

    def _build_runner_args(self, executable_path: Path | str) -> list[str]:
        executable = str(executable_path)
        if self.app_script_path is None:
            return [executable, "--scheduler-service"]
        return [executable, str(self.app_script_path), "--scheduler-service"]

    def _windows_command(self, arguments: list[str]) -> str:
        tokens: list[str] = []
        for argument in arguments:
            escaped = argument.replace('"', '""')
            if any(character.isspace() for character in escaped) or ":" in escaped or "\\" in escaped:
                tokens.append(f'"{escaped}"')
            else:
                tokens.append(escaped)
        return " ".join(tokens)

    def _linux_command(self, arguments: list[str]) -> str:
        return " ".join(shlex.quote(argument) for argument in arguments)

    def build_export(self, executable_path: Path | str) -> ServiceModeExport:
        """Render service helper content for Windows and Linux."""
        runner_args = self._build_runner_args(executable_path)
        windows_command = self._windows_command(runner_args)
        escaped_windows_command = windows_command.replace('"', r'\"')
        linux_command = self._linux_command(runner_args)
        working_directory = str((self.working_directory or Path.cwd()).resolve())
        working_directory_quoted = shlex.quote(working_directory)

        windows_task_script = (
            "@echo off\r\n"
            "REM Heisenberg Backup Manager - Register Scheduler Service Task\r\n"
            "REM Review before running. This registers an ONSTART Task Scheduler job only.\r\n"
            "\r\n"
            "schtasks /Create ^\r\n"
            ' /TN "Heisenberg Backup Manager\\Service Runner" ^\r\n'
            f' /TR "{escaped_windows_command}" ^\r\n'
            " /SC ONSTART ^\r\n"
            " /F\r\n"
        )
        windows_run_now_script = f"@echo off\r\n{windows_command}\r\n"
        linux_unit = (
            "[Unit]\n"
            "Description=Heisenberg Backup Manager Scheduler Service\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={working_directory_quoted}\n"
            f"ExecStart={linux_command}\n"
            "Restart=always\n"
            "RestartSec=10\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )
        linux_install_script = (
            "#!/usr/bin/env bash\n"
            "# Review these commands before running them.\n"
            "set -e\n"
            "sudo cp heisenberg-backup-manager.service /etc/systemd/system/\n"
            "sudo systemctl daemon-reload\n"
            "sudo systemctl enable heisenberg-backup-manager\n"
            "sudo systemctl start heisenberg-backup-manager\n"
        )
        return ServiceModeExport(
            windows_task_script=windows_task_script,
            windows_run_now_script=windows_run_now_script,
            linux_unit=linux_unit,
            linux_install_script=linux_install_script,
        )

    def save_windows_exports(self, executable_path: Path | str) -> list[Path]:
        """Persist Windows service helper files."""
        export = self.build_export(executable_path)
        export_dir = self._require_exports_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        task_path = export_dir / "windows_scheduler_service_task.cmd"
        run_now_path = export_dir / "windows_scheduler_service_run_now.cmd"
        task_path.write_text(export.windows_task_script, encoding="utf-8")
        run_now_path.write_text(export.windows_run_now_script, encoding="utf-8")
        return [task_path, run_now_path]

    def save_linux_exports(self, executable_path: Path | str) -> list[Path]:
        """Persist Linux service helper files."""
        export = self.build_export(executable_path)
        export_dir = self._require_exports_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        unit_path = export_dir / "heisenberg-backup-manager.service"
        install_path = export_dir / "install_linux_service.sh"
        unit_path.write_text(export.linux_unit, encoding="utf-8")
        install_path.write_text(export.linux_install_script, encoding="utf-8")
        return [unit_path, install_path]

    def _require_exports_dir(self) -> Path:
        if self.exports_dir is None:
            raise ValueError("Exports directory is not configured.")
        return self.exports_dir
