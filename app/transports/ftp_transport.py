"""FTP transport for remote-to-local folder downloads."""

from __future__ import annotations

import ftplib
import os
import posixpath
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.models.profile import FolderBackupProfile
from app.services.path_sanitizer_service import PathSanitizerService
from app.services.path_validation_service import PathValidationService
from app.services.platform_service import PlatformService
from app.services.staging_service import StagingService
from app.transports.base import BaseTransport, ProgressCallback


class FtpTransport(BaseTransport):
    """Download a remote directory tree over FTP."""

    def __init__(
        self,
        log_service,
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
        self._current_remote_root: PurePosixPath | None = None
        self._current_path_sanitizer: PathSanitizerService | None = None
        self._logged_sanitized_paths: set[str] = set()

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

    @staticmethod
    def _log_operation_failure(
        logger,
        *,
        operation: str,
        target: Path | str,
        exception: Exception,
    ) -> None:
        """Log one failed filesystem operation in the requested diagnostic format."""
        logger.info(
            "Operation:\n%s\n\nTarget:\n%s\n\nResult:\nFAILED\n\nException:\n%s\n%s",
            operation,
            target,
            exception.__class__,
            exception,
        )

    @staticmethod
    def _log_destination_root(logger, destination_root: Path) -> None:
        """Log the destination root once before the first file write."""
        logger.info("Destination Root:\n%s", destination_root)

    @staticmethod
    def _log_staging_details(logger, *, source_type: str, staging_path: Path, destination_path: Path) -> None:
        """Log the staging strategy details for UNC reliability mode."""
        logger.info("Remote Source:\n%s", source_type)
        logger.info("Destination:\nUNC")
        logger.info("Strategy:\nlocal staging + robocopy")
        logger.info("Staging Folder:\n%s", staging_path)
        logger.info("Final Destination Root:\n%s", destination_path)

    @staticmethod
    def _log_first_file(
        logger,
        *,
        remote_path: PurePosixPath,
        local_path: Path,
    ) -> None:
        """Log the first file pair before the first download attempt."""
        logger.info("Remote File:\n%s", remote_path)
        logger.info("Local File:\n%s", local_path)

    def _connection_summary(self, profile: FolderBackupProfile) -> str:
        """Build a log-safe FTP connection summary."""
        password = self.log_service.mask_secret(profile.ftp_password)
        return (
            f"ftp://{profile.ftp_username}:{password}@{profile.ftp_host}:"
            f"{profile.ftp_port}{profile.ftp_remote_path}"
        )

    def _should_use_staging(self, profile: FolderBackupProfile) -> bool:
        """Return whether this FTP profile should stage locally before copying."""
        return (
            self.platform_service.is_windows()
            and profile.source_type == "ftp"
            and profile.destination_type == "network"
            and PathValidationService.is_unc_path(profile.destination)
        )

    @staticmethod
    def _build_staging_failure_message(message: str, staging_folder: Path) -> str:
        """Append the kept staging folder path to a failure message."""
        return f"{message}\n\nStaging Folder Kept:\n{staging_folder}"

    @staticmethod
    def _log_sanitized_path(logger, *, original_relative_path: str, local_relative_path: str) -> None:
        """Log when a remote path must change for the local filesystem."""
        logger.warning(
            "Remote filename sanitized:\nOriginal: %s\nLocal: %s",
            original_relative_path,
            local_relative_path,
        )

    @staticmethod
    def _raise_mapping_write_failure(logger, *, target: Path, exception: Exception) -> None:
        """Raise a detailed error when the filename map cannot be written."""
        logger.info(
            "Operation:\nwrite filename map\n\nTarget:\n%s\n\nResult:\nFAILED\n\nException:\n%s\n%s",
            target,
            exception.__class__,
            exception,
        )
        raise RuntimeError(
            "FTP Write Failure\n\n"
            "Operation:\nwrite filename map\n\n"
            f"Target:\n{target}\n\n"
            f"Exception:\n{exception.__class__}\n{exception}"
        ) from exception

    def _resolve_local_path(
        self,
        remote_path: PurePosixPath,
        *,
        record_mapping: bool,
        logger,
    ) -> Path:
        """Map a remote path into a collision-safe local path under the active root."""
        if self._current_remote_root is None or self._current_path_sanitizer is None:
            raise RuntimeError("FTP path sanitizer state is not initialized.")

        remote_relative_path = posixpath.relpath(remote_path.as_posix(), self._current_remote_root.as_posix())
        original_relative_path, local_relative_path, changed = self._current_path_sanitizer.resolve_relative_path(
            remote_relative_path,
            record_mapping=record_mapping,
        )
        if changed and original_relative_path not in self._logged_sanitized_paths:
            self._log_sanitized_path(
                logger,
                original_relative_path=original_relative_path,
                local_relative_path=local_relative_path,
            )
            self._logged_sanitized_paths.add(original_relative_path)
        return self._current_path_sanitizer.build_safe_local_path(
            remote_relative_path,
            record_mapping=record_mapping,
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
            try:
                self.ensure_local_directory(local_path.parent)
            except Exception as exc:
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="mkdir parent",
                    target=local_path.parent,
                    exception=exc,
                )

            try:
                handle = local_path.open("wb")
            except Exception as exc:
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="open destination file",
                    target=local_path,
                    exception=exc,
                )

            def write_chunk(data: bytes) -> None:
                try:
                    handle.write(data)
                except Exception as exc:
                    self._raise_write_failure(
                        logger,
                        remote_path=remote_path,
                        local_path=local_path,
                        operation="write chunk",
                        target=local_path,
                        exception=exc,
                    )

            ftp.retrbinary(f"RETR {remote_path}", write_chunk)

            try:
                handle.flush()
            except Exception as exc:
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="flush",
                    target=local_path,
                    exception=exc,
                )

            try:
                handle.close()
            except Exception as exc:
                self._raise_write_failure(
                    logger,
                    remote_path=remote_path,
                    local_path=local_path,
                    operation="close",
                    target=local_path,
                    exception=exc,
                )
            handle = None

            if remote_timestamp is not None:
                try:
                    os.utime(local_path, (remote_timestamp, remote_timestamp))
                except Exception as exc:
                    self._raise_write_failure(
                        logger,
                        remote_path=remote_path,
                        local_path=local_path,
                        operation="os.utime",
                        target=local_path,
                        exception=exc,
                    )
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
        target: Path | str,
        exception: Exception,
    ) -> None:
        """Raise a detailed FTP write failure for the first local-write error."""
        self._log_operation_failure(
            logger,
            operation=operation,
            target=target,
            exception=exception,
        )
        message = (
            "FTP Write Failure\n\n"
            f"Remote File:\n{remote_path}\n\n"
            f"Local File:\n{local_path}\n\n"
            f"Operation:\n{operation}\n\n"
            f"Target:\n{target}\n\n"
            f"Exception:\n{exception.__class__}\n{exception}"
        )
        raise RuntimeError(message) from exception

    def _download_tree(
        self,
        ftp: ftplib.FTP,
        remote_root: PurePosixPath,
        local_root: Path,
        logger,
        first_file_logged: list[bool],
    ) -> int:
        """Recursively download new or updated files from the remote tree."""
        copied = 0
        for remote_path, facts in self._iter_remote_entries(ftp, remote_root):
            local_path = self._resolve_local_path(remote_path, record_mapping=False, logger=logger)
            if facts.get("type") == "dir":
                try:
                    self.ensure_local_directory(local_path)
                except Exception as exc:
                    self._raise_write_failure(
                        logger,
                        remote_path=remote_path,
                        local_path=local_path,
                        operation="mkdir parent",
                        target=local_path,
                        exception=exc,
                    )
                copied += self._download_tree(
                    ftp,
                    remote_path,
                    local_path,
                    logger,
                    first_file_logged,
                )
                continue

            remote_size = self._remote_size(ftp, remote_path, facts)
            remote_timestamp = self._remote_timestamp(ftp, remote_path, facts)
            if self._should_copy(local_path, remote_size, remote_timestamp):
                if not first_file_logged[0]:
                    self._log_first_file(
                        logger,
                        remote_path=remote_path,
                        local_path=local_path,
                    )
                    first_file_logged[0] = True
                local_path = self._resolve_local_path(remote_path, record_mapping=True, logger=logger)
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

            destination_root = Path(profile.destination).expanduser()
            staging_folder: Path | None = None
            download_root = destination_root
            use_staging = self._should_use_staging(profile)
            if use_staging:
                staging_folder = self.staging_service.create_staging_folder(profile.id or profile.name)
                download_root = staging_folder
                self._log_staging_details(
                    logger,
                    source_type="ftp",
                    staging_path=staging_folder,
                    destination_path=destination_root,
                )
                if progress:
                    progress("Using local staging for network destination reliability.")

            self._log_destination_root(logger, download_root)
            try:
                self.ensure_local_directory(download_root)
            except Exception as exc:
                self._log_operation_failure(
                    logger,
                    operation="mkdir destination root",
                    target=download_root,
                    exception=exc,
                )
                message = (
                    "FTP Write Failure\n\n"
                    f"Operation:\nmkdir destination root\n\n"
                    f"Target:\n{download_root}\n\n"
                    f"Exception:\n{exc.__class__}\n{exc}"
                )
                if staging_folder is not None:
                    message = self._build_staging_failure_message(message, staging_folder)
                    logger.info("Final Status:\nFAILED")
                    logger.info("Staging Folder Kept:\n%s", staging_folder)
                raise RuntimeError(message) from exc
            remote_root = PurePosixPath(profile.ftp_remote_path or "/")
            self._current_remote_root = remote_root
            self._current_path_sanitizer = PathSanitizerService(
                download_root,
                platform="windows" if self.platform_service.is_windows() else self.platform_service.system_name(),
            )
            self._logged_sanitized_paths = set()
            connection_summary = self._connection_summary(profile)
            logger.info("Starting FTP download: %s (passive=%s)", connection_summary, profile.ftp_passive)
            if progress:
                progress(f"Downloading from FTP {profile.ftp_host}:{remote_root}...")

            try:
                ftp = self._connect(profile)
                try:
                    copied = self._download_tree(
                        ftp,
                        remote_root,
                        download_root,
                        logger,
                        [False],
                    )
                finally:
                    try:
                        ftp.quit()
                    except ftplib.all_errors:
                        ftp.close()

                try:
                    filename_map_path = self._current_path_sanitizer.write_filename_map(download_root)
                except Exception as exc:
                    self._raise_mapping_write_failure(
                        logger,
                        target=download_root / ".heisenberg_filename_map.json",
                        exception=exc,
                    )
                if filename_map_path is not None:
                    logger.info("Filename Map:\n%s", filename_map_path)

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

            message = f"Downloaded {copied} file(s) from FTP."
            if self._current_path_sanitizer is not None and self._current_path_sanitizer.has_sanitized_paths:
                warning_message = "Download completed with filename sanitization for Windows compatibility."
                logger.warning(warning_message)
                message = f"{message} {warning_message}"
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
            self._current_remote_root = None
            self._current_path_sanitizer = None
            self._logged_sanitized_paths = set()
            self._close_logger_handlers(logger)
