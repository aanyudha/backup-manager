"""Restore execution result models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RestoreResult(BaseModel):
    """Represents the outcome of one restore run."""

    success: bool
    restore_type: str
    source: str
    destination: str
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    message: str
    log_file: str | None = None
