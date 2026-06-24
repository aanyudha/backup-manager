"""SFTP transport for remote-to-local folder downloads."""

from __future__ import annotations

import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import paramiko

from app.models.profile import FolderBackupProfile
from app.services.log_service import LogService
from app.transports.base import BaseTransport, ProgressCallback


class SftpTransport(BaseTransport):
    """Download a remote directory tree over SFTP."""

    def __init__(self, log_service: LogService) -> None:
        super().__init__(log_service)

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
        if profile.mode == "mirror_with_delete":
            return self.build_result(
                success=False,
                profile=profile,
                started_at=started_at,
                message="mirror_with_delete is not supported for SFTP in the MVP.",
                log_file=str(log_path),
            )

        local_destination = Path(profile.destination).expanduser()
        try:
            self.ensure_local_directory(local_destination)
        except Exception as exc:
            self._raise_local_write_failure(
                logger,
                operation="mkdir destination root",
                target=local_destination,
                exception=exc,
            )
        remote_root = PurePosixPath(profile.sftp_remote_path or "/")
        if progress:
            progress(f"Downloading from SFTP {profile.sftp_host}:{remote_root}...")

        client = self._connect(profile)
        try:
            copied = self._download_tree(client, remote_root, local_destination, logger)
        finally:
            transport = client.get_channel().get_transport()
            client.close()
            if transport:
                transport.close()

        message = f"Downloaded {copied} file(s) from SFTP."
        logger.info(message)
        if progress:
            progress(message)
        return self.build_result(
            success=True,
            profile=profile,
            started_at=started_at,
            message=message,
            log_file=str(log_path),
            output_file=str(local_destination),
        )
