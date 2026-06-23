"""Folder backup engine that selects the appropriate transport."""

from __future__ import annotations

import re
from pathlib import Path

from app.engines.base import BaseBackupEngine, ProgressCallback
from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService
from app.services.platform_service import PlatformService
from app.transports.ftp_transport import FtpTransport
from app.transports.local_copy_transport import LocalCopyTransport
from app.transports.robocopy_transport import RobocopyTransport
from app.transports.rsync_transport import RsyncTransport
from app.transports.sftp_transport import SftpTransport


class FolderBackupEngine(BaseBackupEngine):
    """Pick and execute a folder backup transport."""

    def __init__(self, platform_service: PlatformService, log_service: LogService) -> None:
        self.platform_service = platform_service
        self.log_service = log_service

    def _is_localish_path(self, value: str) -> bool:
        """Return True for local, UNC, or mounted paths."""
        return not (":" in value and not value.startswith("\\\\") and not Path(value).drive)

    @staticmethod
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

    @classmethod
    def resolve_engine_inputs(
        cls,
        *,
        platform_service: PlatformService,
        requested_engine: str,
        source: str,
        destination: str,
        sftp_host: str | None = None,
        sftp_remote_path: str | None = None,
        ftp_host: str | None = None,
        ftp_remote_path: str | None = None,
    ) -> str:
        """Resolve a folder engine from raw form inputs without model validation."""
        profile = FolderBackupProfile.model_construct(
            name="preview",
            type="folder",
            source=source,
            destination=destination,
            engine=requested_engine,
            sftp_host=sftp_host,
            sftp_remote_path=sftp_remote_path,
            ftp_host=ftp_host,
            ftp_remote_path=ftp_remote_path,
        )
        return cls.resolve_engine_for_profile(profile, platform_service)

    @classmethod
    def resolve_engine_for_profile(
        cls,
        profile: FolderBackupProfile,
        platform_service: PlatformService,
    ) -> str:
        """Resolve the effective engine for a folder profile."""
        if profile.engine != "auto":
            return profile.engine

        if profile.has_sftp_configuration():
            return "sftp"
        if profile.has_ftp_configuration():
            return "ftp"
        if cls._looks_like_rsync_remote(profile.source) or cls._looks_like_rsync_remote(profile.destination):
            return "rsync"
        if platform_service.is_windows() and platform_service.command_exists("robocopy"):
            return "robocopy"
        return "local_copy"

    def resolve_engine(self, profile: FolderBackupProfile) -> str:
        """Select an engine based on profile choice and host OS."""
        return self.resolve_engine_for_profile(profile, self.platform_service)

    def _validate_profile(self, profile: FolderBackupProfile, engine: str) -> None:
        """Validate profile path assumptions before execution."""
        if engine in {"local_copy", "robocopy"}:
            source = Path(profile.source).expanduser()
            if not source.exists():
                raise FileNotFoundError(f"Source folder not found: {source}")
            Path(profile.destination).expanduser().mkdir(parents=True, exist_ok=True)
        elif engine == "rsync":
            if ":" not in profile.source and not Path(profile.source).expanduser().exists():
                raise FileNotFoundError(f"Source folder not found: {profile.source}")
            if ":" not in profile.destination:
                Path(profile.destination).expanduser().mkdir(parents=True, exist_ok=True)
        elif engine == "sftp":
            Path(profile.destination).expanduser().mkdir(parents=True, exist_ok=True)
        elif engine == "ftp":
            Path(profile.destination).expanduser().mkdir(parents=True, exist_ok=True)

    def run(
        self,
        profile: FolderBackupProfile,
        progress: ProgressCallback | None = None,
    ) -> BackupResult:
        """Execute a folder backup using the resolved transport."""
        selected_engine = self.resolve_engine(profile)
        self.log_service.log_app(f"Requested engine: {profile.engine}")
        self.log_service.log_app(f"Resolved engine: {selected_engine}")
        self._validate_profile(profile, selected_engine)

        if progress:
            if profile.engine == "auto" and profile.has_sftp_configuration() and profile.has_ftp_configuration():
                progress(
                    "Both SFTP and FTP settings are filled. Auto selected SFTP. "
                    "Clear unused settings to avoid confusion."
                )
            progress(f"Using {selected_engine} engine for {profile.name}.")

        if selected_engine == "local_copy":
            return LocalCopyTransport(self.log_service).run(profile, progress)
        if selected_engine == "robocopy":
            return RobocopyTransport(self.log_service, self.platform_service).run(profile, progress)
        if selected_engine == "rsync":
            return RsyncTransport(self.log_service, self.platform_service).run(profile, progress)
        if selected_engine == "sftp":
            return SftpTransport(self.log_service).run(profile, progress)
        if selected_engine == "ftp":
            return FtpTransport(self.log_service).run(profile, progress)
        raise RuntimeError(f"Unsupported folder engine: {selected_engine}")
