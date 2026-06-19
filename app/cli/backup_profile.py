"""CLI argument parsing for backup profile execution."""

from __future__ import annotations

import argparse


def build_cli_parser() -> argparse.ArgumentParser:
    """Create the application CLI parser."""
    parser = argparse.ArgumentParser(description="Heisenberg Backup Manager")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run-profile-id", dest="run_profile_id", help="Run one backup profile by id.")
    group.add_argument("--run-profile-name", dest="run_profile_name", help="Run one backup profile by name.")
    return parser


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the app."""
    return build_cli_parser().parse_args(argv)
