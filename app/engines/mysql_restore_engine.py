"""MySQL restore engine built around the `mysql` client."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.engines.base import ProgressCallback
from app.models.restore_result import RestoreResult
from app.services.log_service import LogService

FATAL_RESTORE_PATTERNS = (
    "mysql: [error]",
    "error ",
    "access denied",
    "unknown database",
    "can't connect",
    "lost connection",
)


@dataclass
class MySQLRestoreCommand:
    """Actual and masked command representations."""

    args: list[str]
    masked_args: list[str]
    env: dict[str, str]


class MySQLRestoreEngine:
    """Run a MySQL client restore from a `.sql` or `.sql.gz` file."""

    def __init__(self, log_service: LogService) -> None:
        self.log_service = log_service

    def resolve_mysql(self, mysql_path: str | None) -> str:
        """Resolve the mysql executable path."""
        if mysql_path:
            candidate = Path(mysql_path).expanduser()
            if not candidate.exists():
                raise FileNotFoundError(f"mysql client path not found: {candidate}")
            return str(candidate)

        resolved = shutil.which("mysql")
        if not resolved:
            raise FileNotFoundError("mysql client was not found on PATH.")
        return resolved

    def validate_sql_file(self, sql_file: str) -> Path:
        """Validate and normalize the incoming SQL restore file."""
        path = Path(sql_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"SQL file not found: {path}")
        if not path.is_file():
            raise ValueError(f"SQL file path is not a file: {path}")
        if not self.is_supported_sql_file(path):
            raise ValueError("SQL file must end with .sql or .sql.gz.")
        return path

    def is_supported_sql_file(self, path: Path) -> bool:
        """Return whether the SQL source extension is supported."""
        name = path.name.lower()
        return name.endswith(".sql") or name.endswith(".sql.gz")

    def build_restore_command(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        mysql_path: str | None = None,
    ) -> MySQLRestoreCommand:
        """Build mysql command arguments without exposing passwords."""
        executable = self.resolve_mysql(mysql_path)
        args = [
            executable,
            f"--host={host.strip()}",
            f"--port={port}",
            f"--user={username.strip()}",
            database.strip(),
        ]
        env = os.environ.copy()
        if password:
            env["MYSQL_PWD"] = password
        return MySQLRestoreCommand(args=args, masked_args=list(args), env=env)

    def build_log_command(self, command: MySQLRestoreCommand, *, has_password: bool) -> str:
        """Return a masked command preview for logs."""
        parts = list(command.masked_args)
        if has_password:
            parts.append("--password=********")
        return self.log_service.mask_command(parts)

    @contextmanager
    def prepared_sql_file(self, sql_file: Path):  # type: ignore[no-untyped-def]
        """Yield a plain `.sql` file, inflating `.sql.gz` into a temporary file when needed."""
        if sql_file.name.lower().endswith(".sql"):
            yield sql_file
            return

        with gzip.open(sql_file, "rb") as source_handle:
            with NamedTemporaryFile("wb", suffix=".sql", delete=False) as temp_handle:
                shutil.copyfileobj(source_handle, temp_handle)
                temp_path = Path(temp_handle.name)

        try:
            yield temp_path
        finally:
            temp_path.unlink(missing_ok=True)

    def execute_restore(
        self,
        command: MySQLRestoreCommand,
        input_path: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute mysql using the SQL file as stdin."""
        with input_path.open("rb") as sql_handle:
            return subprocess.run(
                command.args,
                stdin=sql_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=command.env,
                check=False,
            )

    def decode_output(self, output: bytes) -> str:
        """Decode subprocess output into text."""
        return output.decode("utf-8", errors="replace").strip()

    def contains_fatal_error(self, text: str) -> bool:
        """Return whether the output contains a fatal mysql error."""
        lowered = text.lower()
        return any(pattern in lowered for pattern in FATAL_RESTORE_PATTERNS)

    def summarize_error(self, stdout_text: str, stderr_text: str) -> str:
        """Collapse stderr/stdout into one concise line."""
        combined = "\n".join(part for part in [stderr_text, stdout_text] if part.strip())
        if not combined.strip():
            return "mysql exited with an error."

        for raw_line in combined.splitlines():
            line = raw_line.strip()
            if line:
                return line
        return "mysql exited with an error."

    def validate_request(
        self,
        *,
        sql_file: str,
        host: str,
        port: int,
        username: str,
        database: str,
        mysql_path: str | None = None,
    ) -> Path:
        """Validate restore inputs before execution."""
        if not host.strip():
            raise ValueError("Host is required.")
        if not username.strip():
            raise ValueError("Username is required.")
        if not database.strip():
            raise ValueError("Database is required.")
        if port <= 0:
            raise ValueError("Port must be greater than zero.")
        validated_file = self.validate_sql_file(sql_file)
        self.resolve_mysql(mysql_path)
        return validated_file

    def run(
        self,
        *,
        sql_file: str,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        mysql_path: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> RestoreResult:
        """Execute a MySQL restore using the configured SQL file."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_restore_logger(started_at)
        source_path = self.validate_request(
            sql_file=sql_file,
            host=host,
            port=port,
            username=username,
            database=database,
            mysql_path=mysql_path,
        )
        command = self.build_restore_command(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            mysql_path=mysql_path,
        )

        logger.info("Starting MySQL restore.")
        logger.info("Source file: %s", source_path)
        logger.info("Host: %s", host)
        logger.info("Database: %s", database)
        logger.info("Command: %s", self.build_log_command(command, has_password=bool(password)))
        if progress:
            progress(f"Preparing MySQL restore for {database}...")

        with self.prepared_sql_file(source_path) as prepared_path:
            if prepared_path != source_path:
                logger.info("Decompressed %s to temporary SQL file %s.", source_path.name, prepared_path.name)
            if progress:
                progress(f"Running mysql restore for {database}...")
            completed = self.execute_restore(command, prepared_path)

        stdout_text = self.decode_output(completed.stdout)
        stderr_text = self.decode_output(completed.stderr)
        fatal_text = "\n".join(part for part in [stderr_text, stdout_text] if part.strip())
        success = completed.returncode == 0 and not self.contains_fatal_error(fatal_text)
        if success:
            message = "MySQL restore completed successfully."
        else:
            message = f"MySQL restore failed: {self.summarize_error(stdout_text, stderr_text)}"

        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - started_at).total_seconds()
        logger.info("Finished MySQL restore with exit code %s.", completed.returncode)
        if stdout_text:
            logger.info("stdout: %s", stdout_text)
        if stderr_text:
            logger.info("stderr: %s", stderr_text)
        logger.info("Duration: %.2f seconds", duration)
        logger.info("Result: %s", message)
        if progress:
            progress(message)

        return RestoreResult(
            success=success,
            restore_type="mysql",
            source=str(source_path),
            destination=f"{database}@{host}:{port}",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            message=message,
            log_file=str(log_path),
        )
