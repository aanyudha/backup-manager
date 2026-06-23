"""Folder backup engine that selects the appropriate transport."""

from __future__ import annotations

import re
from pathlib import Path

from app.engines.base import BaseBackupEngine, ProgressCallback
from app.models.profile import FolderBackupProfile
from app.models.result import BackupResult
from app.services.log_service import LogService
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.windows_network_share_service import (
    connect_share_diagnostic,
    disconnect_share_diagnostic,
    extract_unc_share_root,
    should_connect_to_share,
)
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
        self.path_validation_service = PathValidationService()

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
    def _destination_uses_rsync_syntax(cls, profile: FolderBackupProfile) -> bool:
        """Return whether the destination should be treated as an rsync remote."""
        if profile.destination_type == "network":
            return False
        return cls._looks_like_rsync_remote(profile.destination)

    @classmethod
    def resolve_engine_inputs(
        cls,
        *,
        platform_service: PlatformService,
        requested_engine: str,
        source: str,
        destination: str,
        source_type: str = "local",
        destination_type: str = "local",
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
            source_type=source_type,
            destination_type=destination_type,
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

        if profile.source_type == "sftp" or profile.has_sftp_configuration():
            return "sftp"
        if profile.source_type == "ftp" or profile.has_ftp_configuration():
            return "ftp"
        if (
            profile.source_type == "rsync"
            or cls._looks_like_rsync_remote(profile.source)
            or cls._destination_uses_rsync_syntax(profile)
        ):
            return "rsync"
        if platform_service.is_windows() and platform_service.command_exists("robocopy"):
            return "robocopy"
        return "local_copy"

    def resolve_engine(self, profile: FolderBackupProfile) -> str:
        """Select an engine based on profile choice and host OS."""
        return self.resolve_engine_for_profile(profile, self.platform_service)

    def _validate_profile(self, profile: FolderBackupProfile, engine: str) -> None:
        """Validate profile path assumptions before execution."""
        destination_is_rsync_remote = engine == "rsync" and self._destination_uses_rsync_syntax(profile)
        if not destination_is_rsync_remote:
            destination_ok, destination_message = self.path_validation_service.validate_destination_path(
                profile.destination,
                profile.destination_type,
            )
            if not destination_ok:
                raise RuntimeError(destination_message)

        if profile.source_type == "ftp" and engine not in {"auto", "ftp"}:
            raise RuntimeError("FTP source requires Engine auto or ftp.")
        if profile.source_type == "sftp" and engine not in {"auto", "sftp"}:
            raise RuntimeError("SFTP source requires Engine auto or sftp.")
        if profile.source_type == "rsync" and engine not in {"auto", "rsync"}:
            raise RuntimeError("Rsync source requires Engine auto or rsync.")
        if profile.source_type == "local" and engine in {"ftp", "sftp"}:
            raise RuntimeError("FTP/SFTP engine requires remote source type.")

        if engine in {"local_copy", "robocopy"}:
            source = Path(profile.source).expanduser()
            if not source.exists():
                raise FileNotFoundError(f"Source folder not found: {source}")
        elif engine == "rsync":
            if not self._looks_like_rsync_remote(profile.source) and not Path(profile.source).expanduser().exists():
                raise FileNotFoundError(f"Source folder not found: {profile.source}")

    @staticmethod
    def _describe_destination_validation_context(
        profile: FolderBackupProfile,
        *,
        net_use_attempted: bool,
        net_use_exit_code: str,
    ) -> str:
        """Build a password-safe diagnostic line for UNC validation order."""
        try:
            share_root = extract_unc_share_root(profile.destination) if profile.destination.strip().startswith("\\\\") else "(not UNC)"
        except ValueError as exc:
            share_root = f"(unavailable: {exc})"
        credentials_provided = bool(
            (profile.destination_network_username or "").strip() and (profile.destination_network_password or "")
        )
        return (
            "Destination validation diagnostics: "
            f"destination={profile.destination} | "
            f"share_root={share_root} | "
            f"network_credentials_provided={str(credentials_provided).lower()} | "
            f"net_use_attempted={str(net_use_attempted).lower()} | "
            f"net_use_exit_code={net_use_exit_code}"
        )

    def run(
        self,
        profile: FolderBackupProfile,
        progress: ProgressCallback | None = None,
    ) -> BackupResult:
        """Execute a folder backup using the resolved transport."""
        selected_engine = self.resolve_engine(profile)
        should_disconnect_share = should_connect_to_share(
            profile.destination,
            profile.destination_type,
            profile.destination_network_username,
            profile.destination_network_password,
            platform_service=self.platform_service,
        )
        disconnect_warning: str | None = None
        self.log_service.log_app(f"Requested engine: {profile.engine}")
        if profile.engine == "auto":
            self.log_service.log_app(f"Resolved engine: {selected_engine}")
        self.log_service.log_app(
            self._describe_destination_validation_context(
                profile,
                net_use_attempted=should_disconnect_share,
                net_use_exit_code="not-attempted",
            )
        )
        if should_disconnect_share:
            connect_diagnostic = connect_share_diagnostic(
                profile.destination,
                profile.destination_network_username or "",
                profile.destination_network_password or "",
                profile.destination_network_domain,
            )
            self.log_service.log_app(connect_diagnostic.message)
            self.log_service.log_app(
                self._describe_destination_validation_context(
                    profile,
                    net_use_attempted=True,
                    net_use_exit_code=str(connect_diagnostic.returncode),
                )
            )
            if not connect_diagnostic.success:
                raise RuntimeError(connect_diagnostic.message)

        try:
            self._validate_profile(profile, selected_engine)

            if progress:
                if profile.engine == "auto" and profile.has_sftp_configuration() and profile.has_ftp_configuration():
                    progress(
                        "Both SFTP and FTP settings are filled. Auto selected SFTP. "
                        "Clear unused settings to avoid confusion."
                    )
                progress(f"Using {selected_engine} engine for {profile.name}.")

            if selected_engine == "local_copy":
                result = LocalCopyTransport(self.log_service).run(profile, progress)
            elif selected_engine == "robocopy":
                result = RobocopyTransport(self.log_service, self.platform_service).run(profile, progress)
            elif selected_engine == "rsync":
                result = RsyncTransport(self.log_service, self.platform_service).run(profile, progress)
            elif selected_engine == "sftp":
                result = SftpTransport(self.log_service).run(profile, progress)
            elif selected_engine == "ftp":
                result = FtpTransport(self.log_service).run(profile, progress)
            else:
                raise RuntimeError(f"Unsupported folder engine: {selected_engine}")
        finally:
            if should_disconnect_share and not profile.destination_network_remember_session:
                disconnect_diagnostic = disconnect_share_diagnostic(profile.destination)
                self.log_service.log_app(disconnect_diagnostic.message)
                if not disconnect_diagnostic.success:
                    disconnect_warning = disconnect_diagnostic.message

        if disconnect_warning:
            result.message = f"{result.message} Disconnect warning: {disconnect_warning}"
            if progress:
                progress(disconnect_warning)
        return result
