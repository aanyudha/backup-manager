"""Application settings model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AppSettings(BaseModel):
    """JSON-backed application settings for the MVP."""

    default_backup_folder: str = ""
    default_log_folder: str = "logs"
    default_mysqldump_path: str = ""
    auto_start_scheduler: bool = False
    run_as_service: bool = False
    service_runner_mode: Literal["internal_scheduler", "external_os_scheduler"] = "internal_scheduler"
