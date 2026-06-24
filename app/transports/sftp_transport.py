"""SFTP transport for remote-to-local folder downloads."""

from __future__ import annotations

import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import paramiko

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.staging_service import StagingService
from app.transports.base import BaseTransport, ProgressCallback


class SftpTransport(BaseTransport):
    """Download a remote directory tree over SFTP."""

    def __init__(
        self,
        log_service: LogService,
        *,
        platform_service: PlatformService | None = None,
        staging_service: StagingService | None = None,
    ) -> None:
        super().__init__(log_service)
        self.platform_service = platform_service or PlatformService()
        self.staging_service = staging_service or StagingService(
            platform_service=self.platform_service,
            log_service=log_service,
        )

    @staticmethod
    def _close_logger_handlers(logger) -> None:
        """Flush and close per-run handlers so diagnostics are readable immediately."""
        for handler in list(logger.handlers):
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    def _connect(self, profile: FolderBackupProfile) -> paramiko.SFTPClient:
        """Create an SFTP client from profile credentials."""
        if not profile.sftp_host or not profile.sftp_username:
            raise RuntimeError("SFTP host and username are required.")

        transport = paramiko.Transport((profile.sftp_host, profile.sftp_port or 22))
        if profile.sftp_private_key:
            key = paramiko.RSAKey.from_private_key_file(profile.sftp_private_key)
            transport.connect(username=profile.sftp_username, pkey=key)
        else:
            transport.connect(username=profile.sftp_username, password=profile.sftp_password or "")
        return paramiko.SFTPClient.from_transport(transport)

    @staticmethod
    def _log_operation_failure(
        logger,
        *,
        operation: str,
        target: Path | str,
        exception: Exception,
    ) -> None:
        """Log one failed filesystem operation in a concise diagnostic format."""
        logger.info(
            "Operation:\n%s\n\nTarget:\n%s\n\nException:\n%s\n%s",
            operation,
            target,
            exception.__class__,
            exception,
        )

    def _raise_local_write_failure(
        self,
        logger,
        *,
        operation: str,
        target: Path | str,
        exception: Exception,
    ) -> None:
        """Raise a detailed SFTP write failure with concise logger context."""
        self._log_operation_failure(
            logger,
            operation=operation,
            target=target,
            exception=exception,
        )
        raise RuntimeError(
            "SFTP Write Failure\n\n"
            f"Operation:\n{operation}\n\n"
            f"Target:\n{target}\n\n"
            f"Exception:\n{exception.__class__}\n{exception}"
        ) from exception

    def _should_use_staging(self, profile: FolderBackupProfile) -> bool:
        """Return whether this SFTP profile should stage locally before copying."""
        return (
            self.platform_service.is_windows()
            and profile.source_type == "sftp"
            and profile.destination_type == "network"
            and PathValidationService.is_unc_path(profile.destination)
        )

    @staticmethod
    def _log_staging_details(logger, *, staging_path: Path, destination_path: Path) -> None:
        """Log the staging strategy details for UNC reliability mode."""
        logger.info("Remote Source:\nsftp")
        logger.info("Destination:\nUNC")
        logger.info("Strategy:\nlocal staging + robocopy")
        logger.info("Staging Folder:\n%s", staging_path)
        logger.info("Final Destination Root:\n%s", destination_path)

    @staticmethod
    def _build_staging_failure_message(message: str, staging_folder: Path) -> str:
        """Append the kept staging folder path to a failure message."""
        return f"{message}\n\nStaging Folder Kept:\n{staging_folder}"

    def _download_tree(
        self,
        client: paramiko.SFTPClient,
        remote_root: PurePosixPath,
        local_root: Path,
        logger,
    ) -> int:
        """Recursively download new or updated files."""
        copied = 0
        for entry in client.listdir_attr(str(remote_root)):
            remote_path = remote_root / entry.filename
            local_path = local_root / entry.filename
            if stat.S_ISDIR(entry.st_mode):
                try:
                    self.ensure_local_directory(local_path)
                except Exception as exc:
                    self._raise_local_write_failure(
                        logger,
                        operation="mkdir parent",
                        target=local_path,
                        exception=exc,
                    )
                copied += self._download_tree(client, remote_path, local_path, logger)
                continue

            should_copy = True
            if local_path.exists():
                local_mtime = int(local_path.stat().st_mtime)
                should_copy = entry.st_mtime > local_mtime or entry.st_size != local_path.stat().st_size
            if should_copy:
                try:
                    self.ensure_local_directory(local_path.parent)
                except Exception as exc:
                    self._raise_local_write_failure(
                        logger,
                        operation="mkdir parent",
                        target=local_path.parent,
                        exception=exc,
                    )
                try:
                    client.get(str(remote_path), str(local_path))
                except Exception as exc:
                    self._raise_local_write_failure(
                        logger,
                        operation="download file",
                        target=local_path,
                        exception=exc,
                    )
                copied += 1
                logger.info("Downloaded %s", remote_path)
        return copied

    def run(self, profile: FolderBackupProfile, progress: ProgressCallback | None = None):
        """Download files from an SFTP source."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        try:
            if profile.mode == "mirror_with_delete":
                return self.build_result(
                    success=False,
                    profile=profile,
                    started_at=started_at,
                    message="mirror_with_delete is not supported for SFTP in the MVP.",
                    log_file=str(log_path),
                )

            destination_root = Path(profile.destination).expanduser()
            staging_folder: Path | None = None
            download_root = destination_root
            use_staging = self._should_use_staging(profile)
            if use_staging:
                staging_folder = self.staging_service.create_staging_folder(profile.id or profile.name)
                download_root = staging_folder
                self._log_staging_details(
                    logger,
                    staging_path=staging_folder,
                    destination_path=destination_root,
                )
                if progress:
                    progress("Using local staging for network destination reliability.")

            try:
                self.ensure_local_directory(download_root)
            except Exception as exc:
                if staging_folder is not None:
                    logger.info("Final Status:\nFAILED")
                    logger.info("Staging Folder Kept:\n%s", staging_folder)
                    raise RuntimeError(
                        self._build_staging_failure_message(
                            "SFTP Write Failure\n\n"
                            "Operation:\nmkdir destination root\n\n"
                            f"Target:\n{download_root}\n\n"
                            f"Exception:\n{exc.__class__}\n{exc}",
                            staging_folder,
                        )
                    ) from exc
                self._raise_local_write_failure(
                    logger,
                    operation="mkdir destination root",
                    target=download_root,
                    exception=exc,
                )
            remote_root = PurePosixPath(profile.sftp_remote_path or "/")
            if progress:
                progress(f"Downloading from SFTP {profile.sftp_host}:{remote_root}...")

            try:
                client = self._connect(profile)
                try:
                    copied = self._download_tree(client, remote_root, download_root, logger)
                finally:
                    transport = client.get_channel().get_transport()
                    client.close()
                    if transport:
                        transport.close()

                if staging_folder is not None:
                    copy_result = self.staging_service.copy_staging_to_destination_with_robocopy(
                        staging_folder,
                        destination_root,
                    )
                    logger.info("Robocopy Command:\n%s", " ".join(copy_result.command))
                    logger.info("Robocopy Exit Code:\n%s", copy_result.returncode)
                    logger.info(copy_result.output)
                    if progress:
                        progress("Copying staged files to network destination with robocopy...")
                    if not copy_result.success:
                        logger.info("Final Status:\nFAILED")
                        logger.info("Staging Folder Kept:\n%s", staging_folder)
                        raise RuntimeError(
                            self._build_staging_failure_message(
                                f"Robocopy failed with exit code {copy_result.returncode}.",
                                staging_folder,
                            )
                        )
                    self.staging_service.cleanup_staging_folder(staging_folder)
            except Exception as exc:
                if staging_folder is not None:
                    logger.info("Final Status:\nFAILED")
                    logger.info("Staging Folder Kept:\n%s", staging_folder)
                    if progress:
                        progress(f"Backup failed. Staging kept at {staging_folder}")
                    if "Staging Folder Kept:" not in str(exc):
                        raise RuntimeError(
                            self._build_staging_failure_message(str(exc), staging_folder)
                        ) from exc
                raise

            message = f"Downloaded {copied} file(s) from SFTP."
            logger.info(message)
            logger.info("Final Status:\nSUCCESS")
            if progress:
                progress(message)
            return self.build_result(
                success=True,
                profile=profile,
                started_at=started_at,
                message=message,
                log_file=str(log_path),
                output_file=str(destination_root),
            )
        finally:
            self._close_logger_handlers(logger)
