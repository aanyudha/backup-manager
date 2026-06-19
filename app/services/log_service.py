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
        self.app_logger = self._build_daily_logger("app")
        self.restore_daily_logger = self._build_daily_logger("restore")
        self.scheduler_daily_logger = self._build_daily_logger("scheduler")

    def _logger_name(self, prefix: str) -> str:
        """Build a path-specific logger name to avoid handler leakage across tests."""
        suffix = self.safe_name(str(self.logs_dir.resolve()))
        return f"heisenberg_backup_manager.{prefix}.{suffix}"

    def _build_daily_logger(self, prefix: str) -> logging.Logger:
        """Create a daily logger for a named subsystem."""
        date_part = datetime.now().strftime("%Y%m%d")
        log_path = self.logs_dir / f"{prefix}_{date_part}.log"
        logger = logging.getLogger(self._logger_name(prefix))
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
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

    def restore_daily_log_path(self, started_at: datetime | None = None) -> Path:
        """Return the daily restore log path."""
        date_part = (started_at or datetime.now()).strftime("%Y%m%d")
        return self.logs_dir / f"restore_{date_part}.log"

    def restore_log_path(self, started_at: datetime | None = None) -> Path:
        """Return a per-run restore log path."""
        timestamp = (started_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
        return self.logs_dir / f"restore_{timestamp}.log"

    def create_restore_logger(self, started_at: datetime | None = None) -> tuple[logging.Logger, Path]:
        """Create a dedicated logger for one restore run and the daily restore log."""
        started_at = started_at or datetime.now()
        run_log_path = self.restore_log_path(started_at)
        daily_log_path = self.restore_daily_log_path(started_at)
        logger_name = f"heisenberg_backup_manager.restore.{run_log_path.stem}.{self.safe_name(str(self.logs_dir.resolve()))}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        run_handler = logging.FileHandler(run_log_path, encoding="utf-8")
        run_handler.setFormatter(formatter)
        daily_handler = logging.FileHandler(daily_log_path, encoding="utf-8")
        daily_handler.setFormatter(formatter)
        logger.addHandler(run_handler)
        logger.addHandler(daily_handler)
        return logger, run_log_path

    def log_app(self, message: str) -> None:
        """Write to the daily application log."""
        self.app_logger.info(message)

    def log_scheduler(self, message: str) -> None:
        """Write to the daily scheduler log."""
        self.scheduler_daily_logger.info(message)

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
