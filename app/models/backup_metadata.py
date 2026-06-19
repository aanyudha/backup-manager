"""Persisted verification metadata for completed backups."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BackupMetadata(BaseModel):
    """Verification and retention metadata for one backup artifact."""

    profile_id: str
    profile_name: str
    backup_type: Literal["mysql", "folder"]
    output_file: str
    sha256: str
    file_size_bytes: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    success: bool
    message: str
    deleted_by_retention: bool = False
    deleted_at: datetime | None = None
