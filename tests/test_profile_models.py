"""Tests for profile model backward compatibility helpers."""

from __future__ import annotations

from app.models.profile import FolderBackupProfile, MySQLBackupProfile, parse_profile


def test_old_folder_profile_with_ftp_host_infers_source_type_ftp() -> None:
    profile = parse_profile(
        {
            "type": "folder",
            "name": "FTP Source",
            "source": "",
            "destination": "C:/backups",
            "engine": "auto",
            "ftp_host": "ftp.example.com",
            "ftp_username": "backup",
            "ftp_remote_path": "/exports",
        }
    )

    assert isinstance(profile, FolderBackupProfile)
    assert profile.source_type == "ftp"


def test_old_folder_profile_with_sftp_host_infers_source_type_sftp() -> None:
    profile = parse_profile(
        {
            "type": "folder",
            "name": "SFTP Source",
            "source": "",
            "destination": "C:/backups",
            "engine": "auto",
            "sftp_host": "sftp.example.com",
            "sftp_username": "backup",
            "sftp_remote_path": "/exports",
        }
    )

    assert isinstance(profile, FolderBackupProfile)
    assert profile.source_type == "sftp"


def test_old_folder_profile_with_plain_source_infers_source_type_local() -> None:
    profile = parse_profile(
        {
            "type": "folder",
            "name": "Documents",
            "source": "C:/Users/backup/Documents",
            "destination": "C:/backups",
            "engine": "auto",
        }
    )

    assert isinstance(profile, FolderBackupProfile)
    assert profile.source_type == "local"


def test_old_mysql_profile_without_destination_type_defaults_local() -> None:
    profile = parse_profile(
        {
            "type": "mysql",
            "name": "Primary DB",
            "host": "127.0.0.1",
            "username": "root",
            "destination": "C:/backups",
        }
    )

    assert isinstance(profile, MySQLBackupProfile)
    assert profile.destination_type == "local"


def test_unc_destination_can_infer_network_type() -> None:
    profile = parse_profile(
        {
            "type": "folder",
            "name": "UNC Backup",
            "source": "C:/Users/backup/Documents",
            "destination": r"\\server\share\backup",
            "engine": "auto",
        }
    )

    assert isinstance(profile, FolderBackupProfile)
    assert profile.destination_type == "network"
