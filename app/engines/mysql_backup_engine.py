"""MySQL backup engine built around mysqldump."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.engines.base import BaseBackupEngine, ProgressCallback
from app.models.profile import MySQLBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService


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

    def build_dump_command(self, profile: MySQLBackupProfile) -> MySQLDumpCommand:
        """Build mysqldump command arguments without exposing passwords."""
        executable = self.resolve_mysqldump(profile)
        args = [
            executable,
            f"--host={profile.host}",
            f"--port={profile.port}",
            f"--user={profile.username}",
            "--single-transaction",
            "--skip-lock-tables",
        ]
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

    def build_log_command(self, profile: MySQLBackupProfile) -> str:
        """Return a masked command preview for tests and logs."""
        command = self.build_dump_command(profile)
        parts = command.masked_args.copy()
        if profile.password:
            parts.append("--password=********")
        return self.log_service.mask_command(parts)

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
        logger.info("Command: %s", self.build_log_command(profile))
        if progress:
            progress(f"Running mysqldump for {profile.name}...")

        with output_path.open("wb") as output_file:
            completed = subprocess.run(
                command.args,
                stdout=output_file,
                stderr=subprocess.PIPE,
                env=command.env,
                check=False,
            )

        message = completed.stderr.decode("utf-8", errors="replace").strip()
        success = completed.returncode == 0

        if profile.compress and success:
            compressed_path = output_path.with_suffix(".sql.gz")
            with output_path.open("rb") as source_handle, gzip.open(compressed_path, "wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
            output_path.unlink(missing_ok=True)
            output_path = compressed_path
            message = "Backup completed with gzip compression."

        if not message:
            message = "Backup completed successfully." if success else "mysqldump failed."

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

