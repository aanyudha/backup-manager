"""Profile models used by the backup manager."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal, TypeAlias
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from app.models.schedule import ScheduleFields
from app.services.path_validation_service import PathValidationService


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


FolderSourceType: TypeAlias = Literal["local", "ftp", "sftp", "rsync"]
DestinationType: TypeAlias = Literal["local", "network"]


def _clean_optional_text(value: object) -> str | None:
    """Normalize possibly-blank text values for inference helpers."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _looks_like_rsync_remote(value: str) -> bool:
    """Return whether a path resembles rsync remote syntax."""
    cleaned = value.strip()
    if not cleaned or cleaned.startswith("\\\\"):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", cleaned):
        return False
    return bool(
        re.match(r"^[^@\s:/\\]+@[^:\s]+:.+", cleaned)
        or re.match(r"^[A-Za-z0-9._-]+:.+", cleaned)
    )


def _infer_destination_type(destination: object) -> str:
    """Infer destination type for older profiles that do not store it explicitly."""
    destination_text = _clean_optional_text(destination)
    if not destination_text:
        return "local"
    if PathValidationService.is_unc_path(destination_text):
        return "network"
    if PathValidationService.is_linux_mount_like_path(destination_text):
        return "network"
    return "local"


def _infer_folder_source_type(data: dict) -> str:
    """Infer source type for older folder profiles that predate source_type."""
    if _clean_optional_text(data.get("sftp_host")) or _clean_optional_text(data.get("sftp_remote_path")):
        return "sftp"
    if _clean_optional_text(data.get("ftp_host")) or _clean_optional_text(data.get("ftp_remote_path")):
        return "ftp"
    source = _clean_optional_text(data.get("source")) or ""
    if _looks_like_rsync_remote(source):
        return "rsync"
    return "local"


class BaseProfile(ScheduleFields):
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
    destination_type: DestinationType = "local"
    destination_network_username: str | None = None
    destination_network_password: str | None = None
    destination_network_domain: str | None = None
    destination_network_remember_session: bool = False
    compress: bool = False

    @model_validator(mode="before")
    @classmethod
    def apply_destination_type_defaults(cls, data: object) -> object:
        """Backfill destination_type for profiles created before the field existed."""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not _clean_optional_text(payload.get("destination_type")):
            payload["destination_type"] = _infer_destination_type(payload.get("destination"))
        return payload

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

    @field_validator(
        "mysqldump_path",
        "destination_network_username",
        "destination_network_password",
        "destination_network_domain",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional strings."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

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
    source: str = ""
    destination: str
    source_type: FolderSourceType = "local"
    destination_type: DestinationType = "local"
    destination_network_username: str | None = None
    destination_network_password: str | None = None
    destination_network_domain: str | None = None
    destination_network_remember_session: bool = False
    engine: Literal["auto", "local_copy", "robocopy", "rsync", "sftp", "ftp"] = "auto"
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
    ftp_host: str | None = None
    ftp_port: int = 21
    ftp_username: str | None = None
    ftp_password: str | None = None
    ftp_remote_path: str | None = None
    ftp_passive: bool = True
    rsync_extra_args: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def apply_transport_defaults(cls, data: object) -> object:
        """Backfill source and destination types for older folder profiles."""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not _clean_optional_text(payload.get("source_type")):
            payload["source_type"] = _infer_folder_source_type(payload)
        if not _clean_optional_text(payload.get("destination_type")):
            payload["destination_type"] = _infer_destination_type(payload.get("destination"))
        return payload

    def has_sftp_configuration(self) -> bool:
        """Return whether SFTP fields are populated enough to influence auto-detection."""
        return bool(self.sftp_host or self.sftp_remote_path)

    def has_ftp_configuration(self) -> bool:
        """Return whether FTP fields are populated enough to influence auto-detection."""
        return bool(self.ftp_host or self.ftp_remote_path)

    @field_validator("destination")
    @classmethod
    def validate_path_fields(cls, value: str) -> str:
        """Require non-empty path fields."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned

    @field_validator("source")
    @classmethod
    def normalize_source_field(cls, value: str) -> str:
        """Normalize the source field so FTP profiles may leave it blank."""
        return value.strip()

    @field_validator(
        "log_folder",
        "sftp_host",
        "sftp_username",
        "sftp_password",
        "sftp_private_key",
        "sftp_remote_path",
        "ftp_host",
        "ftp_username",
        "ftp_password",
        "ftp_remote_path",
        "destination_network_username",
        "destination_network_password",
        "destination_network_domain",
    )
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

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "FolderBackupProfile":
        """Validate engine-specific fields without forcing the UI to over-specialize."""
        if self.source_type == "ftp" and self.engine not in {"auto", "ftp"}:
            raise ValueError("FTP source requires Engine auto or ftp.")
        if self.source_type == "sftp" and self.engine not in {"auto", "sftp"}:
            raise ValueError("SFTP source requires Engine auto or sftp.")
        if self.source_type == "rsync" and self.engine not in {"auto", "rsync"}:
            raise ValueError("Rsync source requires Engine auto or rsync.")
        if self.source_type == "local" and self.engine in {"ftp", "sftp"}:
            raise ValueError("FTP/SFTP engine requires remote source type.")

        if self.source_type in {"local", "rsync"} and not self.source:
            raise ValueError("Source is required for Local Folder and Rsync sources.")

        validation_engine = self.engine
        if validation_engine == "auto":
            if self.source_type == "sftp" or self.has_sftp_configuration():
                validation_engine = "sftp"
            elif self.source_type == "ftp" or self.has_ftp_configuration():
                validation_engine = "ftp"
            elif self.source_type == "rsync" or _looks_like_rsync_remote(self.source):
                validation_engine = "rsync"

        if validation_engine == "ftp":
            if not self.ftp_host:
                raise ValueError("FTP host is required when engine=ftp.")
            if self.ftp_port <= 0:
                raise ValueError("FTP port must be greater than 0.")
            if not self.ftp_username:
                raise ValueError("FTP username is required when engine=ftp.")
            if not self.ftp_remote_path:
                raise ValueError("FTP remote path is required when engine=ftp.")
        if validation_engine == "sftp":
            if not self.sftp_host:
                raise ValueError("SFTP host is required when engine=sftp.")
            if (self.sftp_port or 0) <= 0:
                raise ValueError("SFTP port must be greater than 0.")
            if not self.sftp_username:
                raise ValueError("SFTP username is required when engine=sftp.")
            if not self.sftp_remote_path:
                raise ValueError("SFTP remote path is required when engine=sftp.")
        return self


Profile: TypeAlias = MySQLBackupProfile | FolderBackupProfile


def parse_profile(data: dict) -> Profile:
    """Deserialize a profile payload into the correct model."""
    profile_type = data.get("type")
    if profile_type == "mysql":
        return MySQLBackupProfile.model_validate(data)
    if profile_type == "folder":
        return FolderBackupProfile.model_validate(data)
    raise ValueError(f"Unsupported profile type: {profile_type!r}")
