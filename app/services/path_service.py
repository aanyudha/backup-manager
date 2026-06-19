"""Resolve runtime paths for source and frozen application modes."""

from __future__ import annotations

import sys
from pathlib import Path


class PathService:
    """Return stable application, config, and log paths."""

    def __init__(
        self,
        *,
        source_root: Path | None = None,
        working_dir: Path | None = None,
        executable_path: Path | None = None,
    ) -> None:
        self._source_root = source_root or Path(__file__).resolve().parents[2]
        self._working_dir = working_dir or Path.cwd()
        self._executable_path = executable_path or Path(sys.executable)

    def is_frozen(self) -> bool:
        """True when running from a PyInstaller-frozen executable."""
        return bool(getattr(sys, "frozen", False))

    def app_root(self) -> Path:
        """Return the source root or executable directory."""
        if self.is_frozen():
            return self._executable_path.resolve().parent
        return self._source_root

    def writable_root(self) -> Path:
        """Return where local runtime data should be written."""
        if self.is_frozen():
            return self._working_dir.resolve()
        return self.app_root()

    def config_dir(self) -> Path:
        """Return the writable config directory."""
        return self.writable_root() / "config"

    def logs_dir(self) -> Path:
        """Return the writable logs directory."""
        return self.writable_root() / "logs"
