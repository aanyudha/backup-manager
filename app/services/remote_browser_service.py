"""Remote directory listing helpers for FTP and SFTP profile browsing."""

from __future__ import annotations

import ftplib
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import PurePosixPath

import paramiko


@dataclass(frozen=True, slots=True)
class RemoteDirectoryEntry:
    """One remote directory row for the browser dialog."""

    name: str
    path: str


class RemoteBrowserService:
    """List remote directories without persisting credentials anywhere new."""

    @staticmethod
    def _normalize_remote_path(remote_path: str | None) -> str:
        cleaned = (remote_path or "/").strip() or "/"
        if not cleaned.startswith("/"):
            cleaned = f"/{cleaned}"
        return str(PurePosixPath(cleaned))

    @staticmethod
    def _child_path(parent: str, child_name: str) -> str:
        root = PurePosixPath(parent)
        return str(root / child_name)

    def list_ftp_directories(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        remote_path: str | None = None,
        passive_mode: bool = True,
    ) -> list[RemoteDirectoryEntry]:
        """Return the child directories for one FTP remote path."""
        if not host.strip() or port <= 0 or not username.strip() or not password:
            raise RuntimeError("Fill FTP connection fields before browsing.")

        normalized_path = self._normalize_remote_path(remote_path)
        ftp = ftplib.FTP()
        ftp.connect(host.strip(), port, timeout=15)
        ftp.login(username.strip(), password)
        ftp.set_pasv(passive_mode)
        try:
            return self._list_ftp_directories(ftp, normalized_path)
        finally:
            with suppress(ftplib.all_errors):
                ftp.quit()
            with suppress(ftplib.all_errors):
                ftp.close()

    def _list_ftp_directories(
        self,
        ftp: ftplib.FTP,
        remote_path: str,
    ) -> list[RemoteDirectoryEntry]:
        """Return child directories for one FTP folder."""
        try:
            directories = [
                RemoteDirectoryEntry(name=name, path=self._child_path(remote_path, name))
                for name, facts in ftp.mlsd(remote_path)
                if name not in {".", ".."} and facts.get("type") == "dir"
            ]
        except (AttributeError, ftplib.error_perm):
            directories = self._list_ftp_directories_fallback(ftp, remote_path)
        return sorted(directories, key=lambda entry: entry.name.lower())

    def _list_ftp_directories_fallback(
        self,
        ftp: ftplib.FTP,
        remote_path: str,
    ) -> list[RemoteDirectoryEntry]:
        """Return child directories for one FTP folder when MLSD is unavailable."""
        try:
            names = ftp.nlst(remote_path)
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                return []
            raise

        current = ftp.pwd()
        directories: list[RemoteDirectoryEntry] = []
        for raw_name in names:
            child_name = PurePosixPath(raw_name).name
            if child_name in {".", ".."}:
                continue
            child_path = self._child_path(remote_path, child_name)
            try:
                ftp.cwd(child_path)
            except ftplib.error_perm:
                continue
            ftp.cwd(current)
            directories.append(RemoteDirectoryEntry(name=child_name, path=child_path))
        return directories

    def list_sftp_directories(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        private_key_path: str | None = None,
        remote_path: str | None = None,
    ) -> list[RemoteDirectoryEntry]:
        """Return the child directories for one SFTP remote path."""
        if (
            not host.strip()
            or port <= 0
            or not username.strip()
            or (not password and not private_key_path)
        ):
            raise RuntimeError("Fill SFTP connection fields before browsing.")

        normalized_path = self._normalize_remote_path(remote_path)
        transport = paramiko.Transport((host.strip(), port))
        if private_key_path:
            key = paramiko.RSAKey.from_private_key_file(private_key_path.strip())
            transport.connect(username=username.strip(), pkey=key)
        else:
            transport.connect(username=username.strip(), password=password or "")
        client = paramiko.SFTPClient.from_transport(transport)
        try:
            directories = [
                RemoteDirectoryEntry(
                    name=entry.filename,
                    path=self._child_path(normalized_path, entry.filename),
                )
                for entry in client.listdir_attr(normalized_path)
                if stat.S_ISDIR(entry.st_mode)
            ]
            return sorted(directories, key=lambda entry: entry.name.lower())
        finally:
            with suppress(Exception):
                client.close()
            with suppress(Exception):
                transport.close()
