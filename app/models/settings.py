"""Application settings model."""

from __future__ import annotations

from pydantic import BaseModel


class AppSettings(BaseModel):
    """JSON-backed application settings for the MVP."""

    default_backup_folder: str = ""
    default_log_folder: str = "logs"
    default_mysqldump_path: str = ""
    auto_start_scheduler: bool = False
