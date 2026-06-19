"""Backup execution result models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BackupResult(BaseModel):
    """Represents the outcome of one backup run."""

    success: bool
    backup_type: Literal["mysql", "folder"]
    profile_id: str
    profile_name: str
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    message: str
    log_file: str | None = None
    output_file: str | None = None
    sha256: str | None = None
    file_size_bytes: int | None = None
