"""Profile models used by the backup manager."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class BaseProfile(BaseModel):
    """Common profile fields shared across all backup types."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    type: Literal["mysql", "folder"]
    enabled: bool = True
    retention_enabled: bool = False
    retention_days: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_message: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a non-empty display name."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Profile name is required.")
        return cleaned

    @model_validator(mode="after")
    def validate_retention_settings(self) -> "BaseProfile":
        """Require a positive retention window when retention is enabled."""
        if self.retention_enabled and (self.retention_days is None or self.retention_days <= 0):
            raise ValueError("Retention days must be greater than 0 when retention is enabled.")
        if not self.retention_enabled and self.retention_days is not None and self.retention_days <= 0:
            self.retention_days = None
        return self


class MySQLBackupProfile(BaseProfile):
    """Configuration for MySQL backups."""

    type: Literal["mysql"] = "mysql"
    host: str
    port: int = 3306
    username: str
    password: str = ""
    database_mode: Literal["all", "single", "multiple"] = "all"
    databases: list[str] = Field(default_factory=list)
    mysqldump_path: str | None = None
    destination: str
    compress: bool = False

    @field_validator("host", "username", "destination")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """Reject blank required strings."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned

    @field_validator("databases")
    @classmethod
    def normalize_databases(cls, value: list[str]) -> list[str]:
        """Trim database names and remove empty entries."""
        return [entry.strip() for entry in value if entry.strip()]

    @model_validator(mode="after")
    def validate_database_mode(self) -> "MySQLBackupProfile":
        """Ensure database selections match the selected mode."""
        if self.database_mode == "single" and len(self.databases) != 1:
            raise ValueError("Single database mode requires exactly one database.")
        if self.database_mode == "multiple" and not self.databases:
            raise ValueError("Multiple database mode requires at least one database.")
        return self


class FolderBackupProfile(BaseProfile):
    """Configuration for folder backups."""

    type: Literal["folder"] = "folder"
    source: str
    destination: str
    engine: Literal["auto", "local_copy", "robocopy", "rsync", "sftp"] = "auto"
    mode: Literal["copy_new_changed", "sync_without_delete", "mirror_with_delete"] = (
        "copy_new_changed"
    )
    log_folder: str | None = None
    sftp_host: str | None = None
    sftp_port: int | None = 22
    sftp_username: str | None = None
    sftp_password: str | None = None
    sftp_private_key: str | None = None
    sftp_remote_path: str | None = None
    rsync_extra_args: list[str] = Field(default_factory=list)

    @field_validator("source", "destination")
    @classmethod
    def validate_path_fields(cls, value: str) -> str:
        """Require non-empty path fields."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned

    @field_validator("log_folder", "sftp_host", "sftp_username", "sftp_password", "sftp_private_key", "sftp_remote_path")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional strings."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("rsync_extra_args")
    @classmethod
    def normalize_rsync_args(cls, value: list[str]) -> list[str]:
        """Trim rsync extra arguments."""
        return [item.strip() for item in value if item.strip()]


Profile: TypeAlias = MySQLBackupProfile | FolderBackupProfile


def parse_profile(data: dict) -> Profile:
    """Deserialize a profile payload into the correct model."""
    profile_type = data.get("type")
    if profile_type == "mysql":
        return MySQLBackupProfile.model_validate(data)
    if profile_type == "folder":
        return FolderBackupProfile.model_validate(data)
    raise ValueError(f"Unsupported profile type: {profile_type!r}")
