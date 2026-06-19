"""Logging helpers for the application and backup runs."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from re import sub


class LogService:
    """Create and manage application and per-backup log files."""

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.app_logger = self._build_daily_logger()

    def _build_daily_logger(self) -> logging.Logger:
        """Create a daily app logger."""
        date_part = datetime.now().strftime("%Y%m%d")
        log_path = self.logs_dir / f"app_{date_part}.log"
        logger = logging.getLogger("heisenberg_backup_manager.app")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(handler)
        return logger

    def safe_name(self, value: str) -> str:
        """Convert a free-form name into a safe filename stem."""
        return sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_") or "backup"

    def backup_log_path(self, profile_name: str, started_at: datetime | None = None) -> Path:
        """Return a log path for one backup run."""
        timestamp = (started_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
        return self.logs_dir / f"{self.safe_name(profile_name)}_{timestamp}.log"

    def create_backup_logger(self, profile_name: str, started_at: datetime | None = None) -> tuple[logging.Logger, Path]:
        """Create a dedicated logger for a backup run."""
        log_path = self.backup_log_path(profile_name, started_at)
        logger_name = f"heisenberg_backup_manager.backup.{profile_name}.{log_path.stem}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        return logger, log_path

    def log_app(self, message: str) -> None:
        """Write to the daily application log."""
        self.app_logger.info(message)

    def mask_secret(self, value: str | None) -> str:
        """Mask one secret for logs."""
        if not value:
            return ""
        return "*" * 8

    def mask_command(self, args: list[str]) -> str:
        """Render a command list while masking password arguments."""
        masked: list[str] = []
        for arg in args:
            if arg.startswith("--password="):
                masked.append("--password=********")
            else:
                masked.append(arg)
        return " ".join(masked)
