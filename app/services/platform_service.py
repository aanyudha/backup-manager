"""Platform-specific helpers."""

from __future__ import annotations

import platform
import shutil


class PlatformService:
    """Encapsulate platform detection and command availability checks."""

    def system_name(self) -> str:
        """Return the current platform.system() value."""
        return platform.system()

    def is_windows(self) -> bool:
        """True when running on Windows."""
        return self.system_name().lower() == "windows"

    def is_linux(self) -> bool:
        """True when running on Linux."""
        return self.system_name().lower() == "linux"

    def command_exists(self, command: str) -> bool:
        """Check whether a command is available on PATH."""
        return shutil.which(command) is not None

    def get_available_engines(self) -> list[str]:
        """List transport engines available on the current host."""
        engines = ["local_copy"]
        if self.is_windows() and self.command_exists("robocopy"):
            engines.append("robocopy")
        if self.command_exists("rsync"):
            engines.append("rsync")
        engines.append("sftp")
        engines.append("ftp")
        return engines

    def compatibility_warnings(self) -> list[str]:
        """Return UI-friendly compatibility warnings."""
        warnings: list[str] = []
        if not self.is_windows():
            warnings.append("Robocopy is available only on Windows.")
        if not self.command_exists("rsync"):
            warnings.append("rsync is not installed; auto mode may fall back to local copy.")
        return warnings
