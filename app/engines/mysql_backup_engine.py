"""MySQL backup engine built around mysqldump."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pymysql

from app.engines.base import BaseBackupEngine, ProgressCallback
from app.models.profile import MySQLBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService

FATAL_STDERR_PATTERNS = (
    "access denied",
    "error ",
    "mysqldump: error:",
    "got error:",
    "unknown database",
    "can't connect",
    "lost connection",
)
DEFAULT_MYSQLDUMP_OPTIONS = (
    "--single-transaction",
    "--quick",
    "--routines",
    "--triggers",
    "--events",
    "--no-tablespaces",
)
COLUMN_STATISTICS_OPTION = "--column-statistics=0"


@dataclass
class MySQLDumpCommand:
    """Actual and masked command representations."""

    args: list[str]
    masked_args: list[str]
    env: dict[str, str]


class MySQLBackupEngine(BaseBackupEngine):
    """Run `mysqldump` and capture its output to a `.sql` file."""

    def __init__(self, log_service: LogService) -> None:
        self.log_service = log_service

    def resolve_mysqldump(self, profile: MySQLBackupProfile) -> str:
        """Resolve the mysqldump executable path."""
        if profile.mysqldump_path:
            candidate = Path(profile.mysqldump_path)
            if not candidate.exists():
                raise FileNotFoundError(f"mysqldump path not found: {candidate}")
            return str(candidate)
        resolved = shutil.which("mysqldump")
        if not resolved:
            raise FileNotFoundError("mysqldump was not found on PATH.")
        return resolved

    def build_dump_command(
        self,
        profile: MySQLBackupProfile,
        *,
        include_column_statistics: bool = True,
    ) -> MySQLDumpCommand:
        """Build mysqldump command arguments without exposing passwords."""
        executable = self.resolve_mysqldump(profile)
        args = [
            executable,
            f"--host={profile.host}",
            f"--port={profile.port}",
            f"--user={profile.username}",
            *DEFAULT_MYSQLDUMP_OPTIONS,
            "--skip-lock-tables",
        ]
        if include_column_statistics:
            args.append(COLUMN_STATISTICS_OPTION)
        if profile.database_mode == "all":
            args.append("--all-databases")
        elif profile.database_mode == "single":
            args.append(profile.databases[0])
        else:
            args.extend(["--databases", *profile.databases])

        env = os.environ.copy()
        if profile.password:
            env["MYSQL_PWD"] = profile.password

        masked_args = args.copy()
        return MySQLDumpCommand(args=args, masked_args=masked_args, env=env)

    def build_log_command(
        self,
        profile: MySQLBackupProfile,
        command: MySQLDumpCommand | None = None,
    ) -> str:
        """Return a masked command preview for tests and logs."""
        command = command or self.build_dump_command(profile)
        parts = command.masked_args.copy()
        if profile.password:
            parts.append("--password=********")
        return self.log_service.mask_command(parts)

    def describe_selected_databases(self, profile: MySQLBackupProfile) -> str:
        """Return a log-friendly summary of the selected databases."""
        if profile.database_mode == "all":
            return "All databases"
        return ", ".join(profile.databases)

    def get_mysql_version(self, profile: MySQLBackupProfile) -> str:
        """Best-effort lookup of the connected MySQL server version."""
        connection = None
        try:
            connection = pymysql.connect(
                host=profile.host,
                port=profile.port,
                user=profile.username,
                password=profile.password,
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
                cursorclass=pymysql.cursors.Cursor,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                row = cursor.fetchone()
            if row and row[0]:
                return str(row[0])
            return "unknown"
        except pymysql.MySQLError as exc:
            return f"unavailable ({exc})"
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def get_mysqldump_version(self, executable: str) -> str:
        """Best-effort lookup of the mysqldump client version."""
        try:
            completed = subprocess.run(
                [executable, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            return f"unavailable ({exc})"

        version_text = completed.stdout.decode("utf-8", errors="replace").strip()
        if not version_text:
            version_text = completed.stderr.decode("utf-8", errors="replace").strip()
        return version_text or "unknown"

    def execute_dump(self, command: MySQLDumpCommand, output_path: Path) -> subprocess.CompletedProcess[bytes]:
        """Execute mysqldump and write stdout to the output path."""
        with output_path.open("wb") as output_file:
            return subprocess.run(
                command.args,
                stdout=output_file,
                stderr=subprocess.PIPE,
                env=command.env,
                check=False,
            )

    def decode_stderr(self, completed: subprocess.CompletedProcess[bytes]) -> str:
        """Decode stderr into UTF-8 text."""
        return completed.stderr.decode("utf-8", errors="replace").strip()

    def contains_fatal_stderr(self, stderr_text: str) -> bool:
        """Return whether stderr includes a fatal mysqldump error pattern."""
        lowered = stderr_text.lower()
        return any(pattern in lowered for pattern in FATAL_STDERR_PATTERNS)

    def should_retry_without_column_statistics(self, stderr_text: str) -> bool:
        """Return whether mysqldump should be retried without column statistics."""
        lowered = stderr_text.lower()
        return "unknown variable 'column-statistics" in lowered

    def summarize_stderr(self, stderr_text: str, *, fatal_only: bool = False) -> str:
        """Collapse stderr into a compact one-line summary."""
        seen: set[str] = set()
        summaries: list[str] = []
        for raw_line in stderr_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            is_fatal = any(pattern in lowered for pattern in FATAL_STDERR_PATTERNS)
            if fatal_only and not is_fatal:
                continue
            if not fatal_only and "warning" not in lowered and not is_fatal:
                continue
            if line in seen:
                continue
            seen.add(line)
            summaries.append(line)
        if not summaries and stderr_text.strip():
            return stderr_text.strip().splitlines()[0].strip()
        return "; ".join(summaries[:3])

    def build_result_message(self, *, success: bool, stderr_text: str) -> str:
        """Build the user-facing result message."""
        if not success:
            summary = self.summarize_stderr(stderr_text, fatal_only=True) or self.summarize_stderr(stderr_text)
            if not summary:
                summary = "mysqldump exited with an error."
            return f"MySQL backup failed: {summary}"

        warning_summary = self.summarize_stderr(stderr_text)
        if warning_summary:
            return f"MySQL backup completed with warning: {warning_summary}"
        return "MySQL backup completed successfully."

    def run(
        self,
        profile: MySQLBackupProfile,
        progress: ProgressCallback | None = None,
    ) -> BackupResult:
        """Execute a mysqldump process and persist the SQL output."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        destination_dir = Path(profile.destination).expanduser()
        destination_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{self.log_service.safe_name(profile.name)}_{started_at.strftime('%Y%m%d_%H%M%S')}.sql"
        output_path = destination_dir / filename

        command = self.build_dump_command(profile)
        logger.info("Starting MySQL backup for profile '%s'.", profile.name)
        logger.info("Command: %s", self.build_log_command(profile, command))
        logger.info("MySQL Version: %s", self.get_mysql_version(profile))
        logger.info("mysqldump Version: %s", self.get_mysqldump_version(command.args[0]))
        logger.info("Database Mode: %s", profile.database_mode)
        logger.info("Selected Databases: %s", self.describe_selected_databases(profile))
        if progress:
            progress(f"Running mysqldump for {profile.name}...")

        completed = self.execute_dump(command, output_path)
        stderr_text = self.decode_stderr(completed)

        if completed.returncode != 0 and self.should_retry_without_column_statistics(stderr_text):
            logger.warning("Retrying mysqldump without --column-statistics=0 for compatibility.")
            command = self.build_dump_command(profile, include_column_statistics=False)
            logger.info("Retry Command: %s", self.build_log_command(profile, command))
            completed = self.execute_dump(command, output_path)
            stderr_text = self.decode_stderr(completed)

        success = completed.returncode == 0 and not self.contains_fatal_stderr(stderr_text)

        if profile.compress and success:
            compressed_path = output_path.with_suffix(".sql.gz")
            with output_path.open("rb") as source_handle, gzip.open(compressed_path, "wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
            output_path.unlink(missing_ok=True)
            output_path = compressed_path
        message = self.build_result_message(success=success, stderr_text=stderr_text)

        finished_at = datetime.now(timezone.utc)
        logger.info("Finished with exit code %s. %s", completed.returncode, message)
        if progress:
            progress(message)

        return BackupResult(
            success=success,
            profile_id=profile.id,
            profile_name=profile.name,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=completed.returncode,
            message=message,
            log_file=str(log_path),
            output_file=str(output_path),
        )
