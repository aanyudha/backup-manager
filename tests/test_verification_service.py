"""Tests for backup verification metadata."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.result import BackupResult
from app.services.verification_service import VerificationService


def test_sha256_file_returns_expected_hash(tmp_path: Path) -> None:
    """The verification service should return the file SHA256 digest."""
    target = tmp_path / "backup.sql.gz"
    target.write_bytes(b"heisenberg-backup")
    service = VerificationService()

    digest = service.sha256_file(target)

    assert digest == hashlib.sha256(b"heisenberg-backup").hexdigest()


def test_build_metadata_uses_result_and_output_file_details(tmp_path: Path) -> None:
    """Metadata should capture the core backup artifact details."""
    target = tmp_path / "backup.sql.gz"
    target.write_bytes(b"backup bytes")
    started_at = datetime.now(timezone.utc)
    finished_at = started_at + timedelta(seconds=3)
    result = BackupResult(
        success=True,
        backup_type="mysql",
        profile_id="profile-1",
        profile_name="Primary DB",
        started_at=started_at,
        finished_at=finished_at,
        message="MySQL backup completed successfully.",
        output_file=str(target),
    )

    metadata = VerificationService().build_metadata(result)

    assert metadata.profile_id == "profile-1"
    assert metadata.output_file == str(target)
    assert metadata.file_size_bytes == target.stat().st_size
    assert metadata.duration_seconds == 3.0
