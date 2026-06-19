"""Backup verification helpers for SHA256 metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.models.backup_metadata import BackupMetadata
from app.models.result import BackupResult


class VerificationService:
    """Compute artifact hashes and normalize backup metadata."""

    def sha256_file(self, path: str | Path) -> str:
        """Return the SHA256 hex digest for one file."""
        file_path = Path(path)
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def build_metadata(self, result: BackupResult) -> BackupMetadata:
        """Create a metadata model from a successful backup result."""
        if not result.output_file:
            raise FileNotFoundError("Backup result does not include an output file.")

        output_path = Path(result.output_file)
        if not output_path.exists():
            raise FileNotFoundError(f"Backup output file not found: {output_path}")
        if not output_path.is_file():
            raise IsADirectoryError(f"Backup output is not a file: {output_path}")

        duration = max((result.finished_at - result.started_at).total_seconds(), 0.0)
        file_size_bytes = output_path.stat().st_size
        return BackupMetadata(
            profile_id=result.profile_id,
            profile_name=result.profile_name,
            backup_type=result.backup_type,
            output_file=str(output_path),
            sha256=self.sha256_file(output_path),
            file_size_bytes=file_size_bytes,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_seconds=duration,
            success=result.success,
            message=result.message,
        )
