"""Common backup engine interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.models.profile import Profile
from app.models.result import BackupResult

ProgressCallback = Callable[[str], None]


class BaseBackupEngine(ABC):
    """Abstract interface for backup execution engines."""

    @abstractmethod
    def run(self, profile: Profile, progress: ProgressCallback | None = None) -> BackupResult:
        """Execute a backup for the given profile."""

