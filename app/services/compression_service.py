"""Streaming helpers for MySQL gzip backup output."""

from __future__ import annotations

import gzip
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


class CompressionServiceError(RuntimeError):
    """Raised when streamed compression fails."""


class CompressionService:
    """Build output paths and stream mysqldump output when gzip is enabled."""

    def build_mysql_output_path(
        self,
        *,
        destination_dir: Path,
        safe_profile_name: str,
        started_at: datetime,
        compress: bool,
    ) -> Path:
        """Return the final output path for the current dump run."""
        suffix = ".sql.gz" if compress else ".sql"
        filename = f"{safe_profile_name}_{started_at.strftime('%Y%m%d_%H%M%S')}{suffix}"
        return destination_dir / filename

    def execute_mysql_dump(
        self,
        *,
        args: list[str],
        env: dict[str, str],
        output_path: Path,
        compress: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute mysqldump, optionally streaming stdout into gzip."""
        output_path.unlink(missing_ok=True)
        if not compress:
            with output_path.open("wb") as output_file:
                return subprocess.run(
                    args,
                    stdout=output_file,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                )
        return self._execute_mysql_dump_with_gzip(args=args, env=env, output_path=output_path)

    def _execute_mysql_dump_with_gzip(
        self,
        *,
        args: list[str],
        env: dict[str, str],
        output_path: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        """Pipe mysqldump stdout through gzip without a temporary .sql file."""
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if process.stdout is None:
                raise CompressionServiceError("mysqldump did not provide a stdout stream.")
            with gzip.open(output_path, "wb") as compressed_output:
                shutil.copyfileobj(process.stdout, compressed_output)
            process.stdout.close()
            stderr_bytes = process.stderr.read() if process.stderr is not None else b""
            if process.stderr is not None:
                process.stderr.close()
            returncode = process.wait()
            return subprocess.CompletedProcess(args=args, returncode=returncode, stderr=stderr_bytes)
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            raise CompressionServiceError(str(exc)) from exc
