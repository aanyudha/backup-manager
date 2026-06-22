"""Folder backup engine that selects the appropriate transport."""

from __future__ import annotations

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

    def resolve_engine(self, profile: FolderBackupProfile) -> str:
        """Select an engine based on profile choice and host OS."""
        if profile.engine != "auto":
            return profile.engine

        if self.platform_service.is_windows():
            if self._is_localish_path(profile.source) and self.platform_service.command_exists("robocopy"):
                return "robocopy"
            return "local_copy"

        if self.platform_service.is_linux():
            if self.platform_service.command_exists("rsync"):
                return "rsync"
            return "local_copy"

        return "local_copy"

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
        self._validate_profile(profile, selected_engine)

        if progress:
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
