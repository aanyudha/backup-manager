"""MySQL backup engine built around mysqldump."""

from __future__ import annotations

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
from app.services.compression_service import CompressionService, CompressionServiceError
from app.services.log_service import LogService
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.windows_network_share_service import (
    connect_share_diagnostic,
    disconnect_share_diagnostic,
    extract_unc_share_root,
    should_connect_to_share,
)

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
    """Run `mysqldump` and capture its output to a `.sql` or `.sql.gz` file."""

    def __init__(
        self,
        log_service: LogService,
        compression_service: CompressionService | None = None,
        path_validation_service: PathValidationService | None = None,
        platform_service: PlatformService | None = None,
    ) -> None:
        self.log_service = log_service
        self.compression_service = compression_service or CompressionService()
        self.path_validation_service = path_validation_service or PathValidationService()
        self.platform_service = platform_service or PlatformService()

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

    def execute_dump(
        self,
        command: MySQLDumpCommand,
        output_path: Path,
        *,
        compress: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute mysqldump and write stdout to the final output path."""
        return self.compression_service.execute_mysql_dump(
            args=command.args,
            env=command.env,
            output_path=output_path,
            compress=compress,
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

    @staticmethod
    def _describe_destination_validation_context(
        profile: MySQLBackupProfile,
        *,
        net_use_attempted: bool,
        net_use_exit_code: str,
    ) -> str:
        """Build a password-safe diagnostic line for UNC validation order."""
        try:
            share_root = extract_unc_share_root(profile.destination) if profile.destination.strip().startswith("\\\\") else "(not UNC)"
        except ValueError as exc:
            share_root = f"(unavailable: {exc})"
        credentials_provided = bool(
            (profile.destination_network_username or "").strip() and (profile.destination_network_password or "")
        )
        return (
            "Destination validation diagnostics: "
            f"destination={profile.destination} | "
            f"share_root={share_root} | "
            f"network_credentials_provided={str(credentials_provided).lower()} | "
            f"net_use_attempted={str(net_use_attempted).lower()} | "
            f"net_use_exit_code={net_use_exit_code}"
        )

    def run(
        self,
        profile: MySQLBackupProfile,
        progress: ProgressCallback | None = None,
    ) -> BackupResult:
        """Execute a mysqldump process and persist the SQL output."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        should_disconnect_share = should_connect_to_share(
            profile.destination,
            profile.destination_type,
            profile.destination_network_username,
            profile.destination_network_password,
            platform_service=self.platform_service,
        )
        disconnect_warning: str | None = None
        completed = subprocess.CompletedProcess(args=[], returncode=1, stderr=b"")
        success = False
        message = "MySQL backup failed."
        output_path: Path | None = None
        command: MySQLDumpCommand | None = None

        logger.info(
            "%s",
            self._describe_destination_validation_context(
                profile,
                net_use_attempted=should_disconnect_share,
                net_use_exit_code="not-attempted",
            ),
        )
        if should_disconnect_share:
            connect_diagnostic = connect_share_diagnostic(
                profile.destination,
                profile.destination_network_username or "",
                profile.destination_network_password or "",
                profile.destination_network_domain,
            )
            logger.info("%s", connect_diagnostic.message)
            logger.info(
                "%s",
                self._describe_destination_validation_context(
                    profile,
                    net_use_attempted=True,
                    net_use_exit_code=str(connect_diagnostic.returncode),
                ),
            )
            if not connect_diagnostic.success:
                raise RuntimeError(connect_diagnostic.message)

        try:
            destination_ok, destination_message = self.path_validation_service.validate_destination_path(
                profile.destination,
                profile.destination_type,
            )
            if not destination_ok:
                raise RuntimeError(destination_message)

            destination_dir = Path(profile.destination).expanduser()
            output_path = self.compression_service.build_mysql_output_path(
                destination_dir=destination_dir,
                safe_profile_name=self.log_service.safe_name(profile.name),
                started_at=started_at,
                compress=profile.compress,
            )

            command = self.build_dump_command(profile)
            logger.info("Starting MySQL backup for profile '%s'.", profile.name)
            logger.info("Command: %s", self.build_log_command(profile, command))
            logger.info("MySQL Version: %s", self.get_mysql_version(profile))
            logger.info("mysqldump Version: %s", self.get_mysqldump_version(command.args[0]))
            logger.info("Database Mode: %s", profile.database_mode)
            logger.info("Selected Databases: %s", self.describe_selected_databases(profile))
            logger.info("Compression Enabled: %s", profile.compress)
            logger.info("Output Path: %s", output_path)
            if progress:
                progress(f"Running mysqldump for {profile.name}...")

            try:
                completed = self.execute_dump(command, output_path, compress=profile.compress)
                stderr_text = self.decode_stderr(completed)

                if completed.returncode != 0 and self.should_retry_without_column_statistics(stderr_text):
                    logger.warning("Retrying mysqldump without --column-statistics=0 for compatibility.")
                    command = self.build_dump_command(profile, include_column_statistics=False)
                    logger.info("Retry Command: %s", self.build_log_command(profile, command))
                    completed = self.execute_dump(command, output_path, compress=profile.compress)
                    stderr_text = self.decode_stderr(completed)

                success = completed.returncode == 0 and not self.contains_fatal_stderr(stderr_text)
                message = self.build_result_message(success=success, stderr_text=stderr_text)
            except CompressionServiceError as exc:
                completed_args = command.args if command is not None else []
                completed = subprocess.CompletedProcess(
                    args=completed_args,
                    returncode=1,
                    stderr=str(exc).encode("utf-8"),
                )
                success = False
                message = f"MySQL backup failed: Compression error: {exc}"
                logger.error("Compression failed: %s", exc)
        finally:
            if should_disconnect_share and not profile.destination_network_remember_session:
                disconnect_diagnostic = disconnect_share_diagnostic(profile.destination)
                logger.info("%s", disconnect_diagnostic.message)
                if not disconnect_diagnostic.success:
                    disconnect_warning = disconnect_diagnostic.message

        if disconnect_warning:
            message = f"{message} Disconnect warning: {disconnect_warning}"
            logger.warning("%s", disconnect_warning)
            if progress:
                progress(disconnect_warning)

        finished_at = datetime.now(timezone.utc)
        logger.info("Finished with exit code %s. %s", completed.returncode, message)
        if progress:
            progress(message)

        return BackupResult(
            success=success,
            backup_type="mysql",
            profile_id=profile.id,
            profile_name=profile.name,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=completed.returncode,
            message=message,
            log_file=str(log_path),
            output_file=str(output_path) if output_path and output_path.exists() else None,
        )
