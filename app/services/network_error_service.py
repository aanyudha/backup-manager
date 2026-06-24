"""Helpers for recognizing transient Windows network destination errors."""

from __future__ import annotations

from pathlib import Path

from app.services.path_validation_service import PathValidationService

NETWORK_TRANSIENT_WINERRORS = {53, 59, 64, 121}


def is_network_destination(path: str | Path | None, destination_type: str | None = None) -> bool:
    """Return whether a path should be treated as a network destination."""
    if destination_type == "network":
        return True
    if path is None:
        return False
    return PathValidationService.is_unc_path(str(path).strip())


def is_network_transient_error(
    exc: BaseException,
    path: str | Path | None = None,
    *,
    destination_type: str | None = None,
) -> bool:
    """Return whether an exception matches a transient Windows network failure."""
    if not isinstance(exc, OSError):
        return False
    if not is_network_destination(path, destination_type):
        return False

    winerror = getattr(exc, "winerror", None)
    errno = getattr(exc, "errno", None)
    return winerror in NETWORK_TRANSIENT_WINERRORS or errno in NETWORK_TRANSIENT_WINERRORS
