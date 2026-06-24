"""FTP transport for remote-to-local folder downloads."""

from __future__ import annotations

import ftplib
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.models.profile import FolderBackupProfile
from app.transports.base import BaseTransport, ProgressCallback


class FtpTransport(BaseTransport):
    """Download a remote directory tree over FTP."""

    @staticmethod
    def _close_logger_handlers(logger) -> None:
        """Flush and close per-run handlers so diagnostics are readable immediately."""
        for handler in list(logger.handlers):
            handler.flush()
            handler.close()
            logger.removeHandler(handler)

    def _validate_profile(self, profile: FolderBackupProfile) -> None:
        """Validate required FTP fields before connecting."""
        if not profile.ftp_host:
            raise RuntimeError("FTP host is required.")
        if profile.ftp_port <= 0:
            raise RuntimeError("FTP port must be a positive integer.")
        if not profile.ftp_username:
            raise RuntimeError("FTP username is required.")
        if not profile.ftp_remote_path:
            raise RuntimeError("FTP remote path is required.")
        if not profile.destination.strip():
            raise RuntimeError("Destination path is required.")

    def _connection_summary(self, profile: FolderBackupProfile) -> str:
        """Build a log-safe FTP connection summary."""
        password = self.log_service.mask_secret(profile.ftp_password)
        return (
            f"ftp://{profile.ftp_username}:{password}@{profile.ftp_host}:"
            f"{profile.ftp_port}{profile.ftp_remote_path}"
        )

    def _connect(self, profile: FolderBackupProfile) -> ftplib.FTP:
        """Create and authenticate an FTP client."""
        ftp = ftplib.FTP()
        ftp.connect(profile.ftp_host, profile.ftp_port, timeout=30)
        ftp.login(profile.ftp_username, profile.ftp_password or "")
        ftp.set_pasv(profile.ftp_passive)
        return ftp

    def _iter_remote_entries(
        self,
        ftp: ftplib.FTP,
        remote_root: PurePosixPath,
    ) -> list[tuple[PurePosixPath, dict[str, str]]]:
        """List one remote directory with MLSD when available and NLST as a fallback."""
        try:
            entries: list[tuple[PurePosixPath, dict[str, str]]] = []
            for entry_name, facts in ftp.mlsd(str(remote_root)):
                if entry_name in {".", ".."}:
                    continue
                entry_type = facts.get("type", "")
                if entry_type in {"cdir", "pdir"}:
                    continue
                entries.append((remote_root / entry_name, facts))
            return entries
        except (AttributeError, ftplib.error_perm):
            return self._iter_remote_entries_fallback(ftp, remote_root)

    def _iter_remote_entries_fallback(
        self,
        ftp: ftplib.FTP,
        remote_root: PurePosixPath,
    ) -> list[tuple[PurePosixPath, dict[str, str]]]:
        """List a directory when MLSD is unavailable."""
        try:
            names = ftp.nlst(str(remote_root))
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                return []
            raise

        entries: list[tuple[PurePosixPath, dict[str, str]]] = []
        for entry in names:
            entry_path = PurePosixPath(entry)
            if not entry_path.is_absolute() and remote_root != PurePosixPath("."):
                entry_path = remote_root / entry_path.name
            if entry_path == remote_root or entry_path.name in {".", ".."}:
                continue
            entry_type = "dir" if self._is_directory(ftp, entry_path) else "file"
            entries.append((entry_path, {"type": entry_type}))
        return entries

    def _is_directory(self, ftp: ftplib.FTP, remote_path: PurePosixPath) -> bool:
        """Probe whether a remote path is a directory."""
        current = ftp.pwd()
        try:
            ftp.cwd(str(remote_path))
            return True
        except ftplib.error_perm:
            return False
        finally:
            ftp.cwd(current)

    @staticmethod
    def _remote_size(ftp: ftplib.FTP, remote_path: PurePosixPath, facts: dict[str, str]) -> int | None:
        """Return the remote file size when available."""
        size_text = facts.get("size")
        if size_text:
            try:
                return int(size_text)
            except ValueError:
                return None
        try:
            return ftp.size(str(remote_path))
        except ftplib.all_errors:
            return None

    @staticmethod
    def _remote_timestamp(ftp: ftplib.FTP, remote_path: PurePosixPath, facts: dict[str, str]) -> int | None:
        """Return the remote file mtime as a unix timestamp when available."""
        modify_value = facts.get("modify")
        if modify_value:
            try:
                parsed = datetime.strptime(modify_value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                return int(parsed.timestamp())
            except ValueError:
                return None
        try:
            response = ftp.sendcmd(f"MDTM {remote_path}")
        except ftplib.all_errors:
            return None
        _, _, timestamp_text = response.partition(" ")
        if not timestamp_text:
            return None
        try:
            parsed = datetime.strptime(timestamp_text.strip(), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except ValueError:
            return None

    @staticmethod
    def _should_copy(local_path: Path, remote_size: int | None, remote_timestamp: int | None) -> bool:
        """Copy when the local file is missing, differently sized, or older."""
        if not local_path.exists():
            return True
        local_stat = local_path.stat()
        if remote_size is not None and local_stat.st_size != remote_size:
            return True
        if remote_timestamp is not None and remote_timestamp > int(local_stat.st_mtime):
            return True
        return False

    def _download_file(
        self,
        ftp: ftplib.FTP,
        remote_path: PurePosixPath,
        local_path: Path,
        remote_timestamp: int | None,
        logger,
    ) -> None:
        """Download one file and preserve the remote timestamp when available."""
        handle = None
        try:
            logger.info("Creating parent:\n%s", local_path.parent)
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                logger.info("Result:\nFAILED")
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="mkdir",
                    exception=exc,
                )
            logger.info("Result:\nOK")

            logger.info("Opening:\n%s", local_path)
            try:
                handle = local_path.open("wb")
            except Exception as exc:
                logger.info("Result:\nFAILED")
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="open",
                    exception=exc,
                )
            logger.info("Result:\nOK")

            def write_chunk(data: bytes) -> None:
                logger.info("Writing:\n%s", local_path)
                logger.info("Bytes:\n%s", len(data))
                try:
                    handle.write(data)
                except Exception as exc:
                    logger.info("Result:\nFAILED")
                    self._raise_write_failure(
                        logger,
                        remote_path=remote_path,
                        local_path=local_path,
                        operation="write",
                        exception=exc,
                    )
                logger.info("Result:\nOK")

            ftp.retrbinary(f"RETR {remote_path}", write_chunk)

            logger.info("Flushing:\n%s", local_path)
            try:
                handle.flush()
            except Exception as exc:
                logger.info("Result:\nFAILED")
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="flush",
                    exception=exc,
                )
            logger.info("Result:\nOK")

            logger.info("Closing:\n%s", local_path)
            try:
                handle.close()
            except Exception as exc:
                logger.info("Result:\nFAILED")
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="close",
                    exception=exc,
                )
            handle = None
            logger.info("Result:\nOK")

            if remote_timestamp is not None:
                os.utime(local_path, (remote_timestamp, remote_timestamp))
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass

    def _raise_write_failure(
        self,
        logger,
        *,
        remote_path: PurePosixPath,
        local_path: Path,
        operation: str,
        exception: Exception,
    ) -> None:
        """Raise a detailed FTP write failure for the first local-write error."""
        message = (
            "FTP Write Failure\n\n"
            f"Remote File:\n{remote_path}\n\n"
            f"Local File:\n{local_path}\n\n"
            f"Parent:\n{local_path.parent}\n\n"
            f"Operation:\n{operation}\n\n"
            f"Exception:\n{exception.__class__}\n{exception}"
        )
        logger.exception(message)
        raise RuntimeError(message) from exception

    @staticmethod
    def _log_download_target(
        logger,
        remote_path: PurePosixPath,
        local_path: Path,
    ) -> None:
        """Log the exact local write target before downloading one remote file."""
        logger.info("REMOTE FILE:\n%s", remote_path)
        logger.info("LOCAL FILE:\n%s", local_path)
        logger.info("PARENT:\n%s", local_path.parent)

    def _download_tree(
        self,
        ftp: ftplib.FTP,
        remote_root: PurePosixPath,
        local_root: Path,
        logger,
    ) -> int:
        """Recursively download new or updated files from the remote tree."""
        copied = 0
        for remote_path, facts in self._iter_remote_entries(ftp, remote_root):
            local_path = local_root / remote_path.relative_to(remote_root)
            if facts.get("type") == "dir":
                local_path.mkdir(parents=True, exist_ok=True)
                copied += self._download_tree(
                    ftp,
                    remote_path,
                    local_path,
                    logger,
                )
                continue

            remote_size = self._remote_size(ftp, remote_path, facts)
            remote_timestamp = self._remote_timestamp(ftp, remote_path, facts)
            if self._should_copy(local_path, remote_size, remote_timestamp):
                self._log_download_target(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                )
                self._download_file(ftp, remote_path, local_path, remote_timestamp, logger)
                copied += 1
                logger.info("Downloaded %s", remote_path)
        return copied

    def run(
        self,
        profile: FolderBackupProfile,
        progress: ProgressCallback | None = None,
    ):
        """Download files from an FTP source."""
        started_at = datetime.now(timezone.utc)
        logger, log_path = self.log_service.create_backup_logger(profile.name, started_at)
        try:
            self._validate_profile(profile)

            if profile.mode == "mirror_with_delete":
                return self.build_result(
                    success=False,
                    profile=profile,
                    started_at=started_at,
                    message="mirror_with_delete is not supported for FTP in the MVP.",
                    log_file=str(log_path),
                )

            local_destination = Path(profile.destination).expanduser()
            local_destination.mkdir(parents=True, exist_ok=True)
            remote_root = PurePosixPath(profile.ftp_remote_path or "/")
            connection_summary = self._connection_summary(profile)
            logger.info("Starting FTP download: %s (passive=%s)", connection_summary, profile.ftp_passive)
            if progress:
                progress(f"Downloading from FTP {profile.ftp_host}:{remote_root}...")

            ftp = self._connect(profile)
            try:
                copied = self._download_tree(
                    ftp,
                    remote_root,
                    local_destination,
                    logger,
                )
            finally:
                try:
                    ftp.quit()
                except ftplib.all_errors:
                    ftp.close()

            message = f"Downloaded {copied} file(s) from FTP."
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
        finally:
            self._close_logger_handlers(logger)
