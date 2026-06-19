"""Service entrypoint for command-line backup profile execution."""

from __future__ import annotations

from typing import TextIO

from app.services.backup_service import BackupService
from app.models.result import BackupResult


class CliBackupService:
    """Resolve and run backup profiles without booting the desktop UI."""

    def __init__(self, backup_service: BackupService) -> None:
        self.backup_service = backup_service

    def execute(
        self,
        *,
        profile_id: str | None = None,
        profile_name: str | None = None,
        stdout: TextIO,
    ) -> int:
        """Run one profile and return a process exit code."""
        try:
            if profile_id:
                result = self.backup_service.run_profile(profile_id)
            elif profile_name:
                result = self.backup_service.run_profile(self._resolve_profile_id_by_name(profile_name))
            else:
                print("No profile selector was provided.", file=stdout)
                return 2
        except Exception as exc:
            print(str(exc), file=stdout)
            return 1

        print(self._format_summary(result), file=stdout)
        return 0 if result.success else 1

    def _resolve_profile_id_by_name(self, profile_name: str) -> str:
        """Look up one profile id by its display name."""
        target = profile_name.strip().casefold()
        if not target:
            raise ValueError("Profile name is required.")

        matches = [
            profile
            for profile in self.backup_service.list_profiles()
            if profile.name.strip().casefold() == target
        ]
        if not matches:
            raise KeyError(f"Profile named '{profile_name}' not found.")
        if len(matches) > 1:
            raise ValueError(f"Multiple profiles named '{profile_name}' were found. Use --run-profile-id instead.")
        return matches[0].id

    @staticmethod
    def _format_summary(result: BackupResult) -> str:
        """Render a compact backup summary for stdout."""
        status = "SUCCESS" if result.success else "FAILED"
        exit_code = result.exit_code if result.exit_code is not None else "n/a"
        return (
            f"[{status}] profile='{result.profile_name}' "
            f"type={result.backup_type} exit_code={exit_code} message={result.message}"
        )
