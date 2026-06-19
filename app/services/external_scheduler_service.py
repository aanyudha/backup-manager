"""Export backup schedules to OS scheduler command formats."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from app.models.profile import Profile

CRON_WEEKDAY_NAMES = {
    0: "MON",
    1: "TUE",
    2: "WED",
    3: "THU",
    4: "FRI",
    5: "SAT",
    6: "SUN",
}

WINDOWS_XML_WEEKDAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


@dataclass(slots=True)
class ExternalScheduleExport:
    """Rendered external scheduler artifacts for one profile."""

    safe_profile_name: str
    windows_register_command: str
    windows_register_script: str
    windows_run_now_command: str
    windows_run_now_script: str
    linux_register_text: str
    linux_cron_line: str
    linux_run_now_command: str
    linux_run_now_script: str
    warnings: list[str]


class ExternalSchedulerService:
    """Generate reviewable scheduler exports without installing them."""

    def __init__(
        self,
        *,
        app_script_path: Path | str | None = None,
        logs_dir: Path | None = None,
        exports_dir: Path | None = None,
    ) -> None:
        self.app_script_path = app_script_path
        self.logs_dir = logs_dir
        self.exports_dir = exports_dir

    def build_export(self, profile: Profile, executable_path: Path | str) -> ExternalScheduleExport:
        """Render both Windows and Linux export variants for a profile."""
        self.validate_exportable(profile)
        safe_profile_name = self.safe_profile_name(profile.name)
        windows_register_command = self.generate_windows_task_command(profile, executable_path)
        windows_run_now_command = self.generate_run_now_command(profile, executable_path, shell="windows")
        linux_cron_line = self.generate_cron_line(profile, executable_path)
        linux_run_now_command = self.generate_run_now_command(profile, executable_path, shell="linux")
        warnings = self._warnings_for_profile(profile)
        return ExternalScheduleExport(
            safe_profile_name=safe_profile_name,
            windows_register_command=windows_register_command,
            windows_register_script=self._build_windows_register_script(
                windows_register_command,
                windows_run_now_command,
            ),
            windows_run_now_command=windows_run_now_command,
            windows_run_now_script=self._build_windows_run_now_script(windows_run_now_command),
            linux_register_text=self._build_linux_register_text(linux_cron_line),
            linux_cron_line=linux_cron_line,
            linux_run_now_command=linux_run_now_command,
            linux_run_now_script=self._build_linux_run_now_script(linux_run_now_command),
            warnings=warnings,
        )

    def validate_exportable(self, profile: Profile) -> None:
        """Reject profiles that should not be exported."""
        if not profile.enabled:
            raise ValueError("Disabled profiles cannot be exported.")
        if not profile.schedule_enabled:
            raise ValueError("Scheduling must be enabled before export.")
        if profile.schedule_runner != "external":
            raise ValueError("Set Schedule Runner to External before exporting this profile.")
        if profile.schedule_type == "manual":
            raise ValueError("Manual schedules cannot be exported.")
        if not profile.schedule_time:
            raise ValueError("Schedule time is required for external scheduler export.")
        if profile.schedule_type == "weekly" and not profile.schedule_days_of_week:
            raise ValueError("Weekly schedules require at least one selected day.")
        if profile.schedule_type == "monthly" and profile.schedule_day_of_month is None:
            raise ValueError("Monthly schedules require a day of month.")

    def schedule_to_cron_expression(self, profile: Profile) -> str:
        """Translate a profile schedule into a cron expression."""
        self.validate_exportable(profile)
        hour_text, minute_text = (profile.schedule_time or "00:00").split(":")
        minute = int(minute_text)
        hour = int(hour_text)
        if profile.schedule_type == "daily":
            return f"{minute} {hour} * * *"
        if profile.schedule_type == "weekly":
            days = ",".join(CRON_WEEKDAY_NAMES[day] for day in profile.schedule_days_of_week)
            return f"{minute} {hour} * * {days}"
        if profile.schedule_type == "monthly":
            return f"{minute} {hour} {profile.schedule_day_of_month} * *"
        raise ValueError(f"Unsupported schedule type: {profile.schedule_type}")

    def generate_windows_task_command(self, profile: Profile, executable_path: Path | str) -> str:
        """Build an `schtasks` command for the selected profile."""
        self.validate_exportable(profile)
        task_name = f"Heisenberg Backup Manager\\{self.safe_profile_name(profile.name)}"
        action_command = self.generate_run_now_command(profile, executable_path, shell="windows")
        escaped_action = action_command.replace('"', r'\"')
        lines = [
            "schtasks /Create ^",
            f' /TN "{task_name}" ^',
            f' /TR "{escaped_action}" ^',
            f" /SC {self._windows_schedule_code(profile)} ^",
        ]
        if profile.schedule_type == "weekly":
            day_list = ",".join(CRON_WEEKDAY_NAMES[day] for day in profile.schedule_days_of_week)
            lines.append(f" /D {day_list} ^")
        if profile.schedule_type == "monthly":
            lines.append(f" /D {profile.schedule_day_of_month} ^")
        lines.extend(
            [
                f" /ST {profile.schedule_time or '00:00'} ^",
                " /F",
            ]
        )
        return "\n".join(lines)

    def generate_windows_task_xml(self, profile: Profile, executable_path: Path | str) -> str:
        """Build Task Scheduler XML for manual import."""
        self.validate_exportable(profile)
        command, *arguments = self._build_runner_args(executable_path, profile.id)
        schedule_block = self._windows_xml_schedule_block(profile)
        argument_text = escape(self._windows_command(arguments)) if arguments else ""
        return (
            '<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
            "  <RegistrationInfo>\n"
            f"    <Description>{escape(f'Backup profile export for {profile.name}')}</Description>\n"
            "  </RegistrationInfo>\n"
            "  <Triggers>\n"
            f"{schedule_block}\n"
            "  </Triggers>\n"
            "  <Principals>\n"
            '    <Principal id="Author">\n'
            "      <RunLevel>LeastPrivilege</RunLevel>\n"
            "    </Principal>\n"
            "  </Principals>\n"
            "  <Settings>\n"
            "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
            "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
            "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
            "    <AllowHardTerminate>true</AllowHardTerminate>\n"
            "    <StartWhenAvailable>true</StartWhenAvailable>\n"
            "    <Enabled>true</Enabled>\n"
            "  </Settings>\n"
            '  <Actions Context="Author">\n'
            "    <Exec>\n"
            f"      <Command>{escape(command)}</Command>\n"
            f"      <Arguments>{argument_text}</Arguments>\n"
            "    </Exec>\n"
            "  </Actions>\n"
            "</Task>\n"
        )

    def generate_cron_line(self, profile: Profile, python_or_executable_path: Path | str) -> str:
        """Build a cron line for the selected profile."""
        self.validate_exportable(profile)
        cron_expression = self.schedule_to_cron_expression(profile)
        command = self.generate_run_now_command(profile, python_or_executable_path, shell="linux")
        log_path = self._cron_log_path(profile)
        return f"{cron_expression} {command} >> {shlex.quote(str(log_path))} 2>&1"

    def generate_run_now_command(
        self,
        profile: Profile,
        executable_path: Path | str,
        *,
        shell: str,
    ) -> str:
        """Build the command that runs one profile immediately."""
        arguments = self._build_runner_args(executable_path, profile.id)
        if shell == "windows":
            return self._windows_command(arguments)
        if shell == "linux":
            return self._linux_command(arguments)
        raise ValueError(f"Unsupported shell: {shell}")

    def save_windows_exports(self, profile: Profile, executable_path: Path | str) -> list[Path]:
        """Persist the Windows scheduler export files."""
        export = self.build_export(profile, executable_path)
        export_dir = self._require_exports_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        register_path = export_dir / f"{export.safe_profile_name}_register_windows_task.cmd"
        run_now_path = export_dir / f"{export.safe_profile_name}_run_now.cmd"
        register_path.write_text(export.windows_register_script, encoding="utf-8")
        run_now_path.write_text(export.windows_run_now_script, encoding="utf-8")
        return [register_path, run_now_path]

    def save_linux_exports(self, profile: Profile, executable_path: Path | str) -> list[Path]:
        """Persist the Linux scheduler export files."""
        export = self.build_export(profile, executable_path)
        export_dir = self._require_exports_dir()
        export_dir.mkdir(parents=True, exist_ok=True)
        cron_path = export_dir / f"{export.safe_profile_name}_linux_cron.txt"
        run_now_path = export_dir / f"{export.safe_profile_name}_linux_run_now.sh"
        cron_path.write_text(export.linux_register_text + "\n", encoding="utf-8")
        run_now_path.write_text(export.linux_run_now_script, encoding="utf-8")
        return [cron_path, run_now_path]

    @staticmethod
    def safe_profile_name(profile_name: str) -> str:
        """Create a filesystem-safe, task-safe profile name."""
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", profile_name.strip())
        cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
        cleaned = re.sub(r"_+", "_", cleaned)
        return cleaned or "profile"

    def _warnings_for_profile(self, profile: Profile) -> list[str]:
        warnings = [
            "This export registers an operating system schedule and does not run the backup immediately.",
            "If you change the profile schedule later, export again.",
        ]
        if profile.schedule_type == "monthly" and (profile.schedule_day_of_month or 0) > 28:
            warnings.append(
                "Cron monthly day may skip shorter months; the internal scheduler handles last-day fallback, but cron does not."
            )
        return warnings

    def _build_runner_args(self, executable_path: Path | str, profile_id: str) -> list[str]:
        executable = str(executable_path)
        if self.app_script_path is None:
            return [executable, "--run-profile-id", profile_id]
        return [executable, str(self.app_script_path), "--run-profile-id", profile_id]

    @staticmethod
    def _windows_schedule_code(profile: Profile) -> str:
        if profile.schedule_type == "daily":
            return "DAILY"
        if profile.schedule_type == "weekly":
            return "WEEKLY"
        if profile.schedule_type == "monthly":
            return "MONTHLY"
        raise ValueError(f"Unsupported schedule type: {profile.schedule_type}")

    def _windows_xml_schedule_block(self, profile: Profile) -> str:
        start_boundary = f"2026-01-01T{profile.schedule_time}:00"
        if profile.schedule_type == "daily":
            return (
                "    <CalendarTrigger>\n"
                f"      <StartBoundary>{start_boundary}</StartBoundary>\n"
                "      <ScheduleByDay>\n"
                "        <DaysInterval>1</DaysInterval>\n"
                "      </ScheduleByDay>\n"
                "    </CalendarTrigger>"
            )
        if profile.schedule_type == "weekly":
            day_entries = "\n".join(
                f"          <{WINDOWS_XML_WEEKDAY_NAMES[day]} />" for day in profile.schedule_days_of_week
            )
            return (
                "    <CalendarTrigger>\n"
                f"      <StartBoundary>{start_boundary}</StartBoundary>\n"
                "      <ScheduleByWeek>\n"
                "        <WeeksInterval>1</WeeksInterval>\n"
                "        <DaysOfWeek>\n"
                f"{day_entries}\n"
                "        </DaysOfWeek>\n"
                "      </ScheduleByWeek>\n"
                "    </CalendarTrigger>"
            )
        if profile.schedule_type == "monthly":
            return (
                "    <CalendarTrigger>\n"
                f"      <StartBoundary>{start_boundary}</StartBoundary>\n"
                "      <ScheduleByMonth>\n"
                "        <Months>\n"
                "          <January />\n"
                "          <February />\n"
                "          <March />\n"
                "          <April />\n"
                "          <May />\n"
                "          <June />\n"
                "          <July />\n"
                "          <August />\n"
                "          <September />\n"
                "          <October />\n"
                "          <November />\n"
                "          <December />\n"
                "        </Months>\n"
                "        <DaysOfMonth>\n"
                f"          <Day>{profile.schedule_day_of_month}</Day>\n"
                "        </DaysOfMonth>\n"
                "      </ScheduleByMonth>\n"
                "    </CalendarTrigger>"
            )
        raise ValueError(f"Unsupported schedule type: {profile.schedule_type}")

    def _cron_log_path(self, profile: Profile) -> Path:
        logs_dir = self.logs_dir or Path("logs")
        return logs_dir / f"cron_{self.safe_profile_name(profile.name)}.log"

    def _require_exports_dir(self) -> Path:
        if self.exports_dir is None:
            raise ValueError("Exports directory is not configured.")
        return self.exports_dir

    @staticmethod
    def _windows_command(arguments: list[str]) -> str:
        tokens: list[str] = []
        for index, argument in enumerate(arguments):
            force_quote = index == 0 or (len(arguments) == 4 and index == 1)
            tokens.append(ExternalSchedulerService._quote_windows_token(argument, force_quote=force_quote))
        return " ".join(tokens)

    @staticmethod
    def _linux_command(arguments: list[str]) -> str:
        return " ".join(shlex.quote(argument) for argument in arguments)

    @staticmethod
    def _quote_windows_token(argument: str, *, force_quote: bool = False) -> str:
        escaped = argument.replace('"', '""')
        if force_quote or any(character.isspace() for character in escaped):
            return f'"{escaped}"'
        return escaped

    @staticmethod
    def _build_windows_register_script(register_command: str, run_now_command: str) -> str:
        return (
            "@echo off\r\n"
            "REM Heisenberg Backup Manager - Register Windows Task\r\n"
            "REM This file registers a Windows Task Scheduler job.\r\n"
            "REM It does NOT run the backup immediately.\r\n"
            "REM Windows Task Scheduler will run the backup at the configured time.\r\n"
            "REM To run backup immediately, use the Run Now command shown below.\r\n"
            "\r\n"
            "echo Registering Windows Task Scheduler job...\r\n"
            f"{register_command}\r\n"
            "if errorlevel 1 (\r\n"
            "    echo Failed to register scheduled task.\r\n"
            "    pause\r\n"
            "    exit /b 1\r\n"
            ")\r\n"
            "\r\n"
            "echo.\r\n"
            "echo Scheduled task registered successfully.\r\n"
            "echo.\r\n"
            "echo To run backup now:\r\n"
            f'echo {run_now_command}\r\n'
            "echo.\r\n"
            "pause\r\n"
        )

    @staticmethod
    def _build_windows_run_now_script(run_now_command: str) -> str:
        return f"@echo off\r\n{run_now_command}\r\npause\r\n"

    @staticmethod
    def _build_linux_register_text(cron_line: str) -> str:
        return (
            "Register this manually with:\n"
            "crontab -e\n\n"
            "Cron line:\n"
            f"{cron_line}"
        )

    @staticmethod
    def _build_linux_run_now_script(run_now_command: str) -> str:
        return f"#!/usr/bin/env bash\nset -e\n{run_now_command}\n"
