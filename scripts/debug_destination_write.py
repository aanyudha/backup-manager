"""Probe one destination path and print a detailed write diagnostic."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.path_validation_service import PathValidationService


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python scripts/debug_destination_write.py "\\\\server\\share\\folder"')
        return 2

    destination = sys.argv[1]
    print(f"Raw Argument: {destination}")
    print(f"Repr Argument: {destination!r}")

    success, report = PathValidationService.ensure_destination_writable(destination, destination_type="script")
    print(report)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
