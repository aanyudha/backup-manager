"""Tests for README and first-run transport guidance."""

from __future__ import annotations

from pathlib import Path


def test_docs_describe_plain_ftp_and_remote_browse_flow() -> None:
    """Docs should describe plain FTP, SFTP, and remote-folder browsing consistently."""
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    first_run = (repo_root / "FIRST_RUN.md").read_text(encoding="utf-8")
    combined = f"{readme}\n{first_run}"

    assert "FTP is plain FTP" in combined
    assert "Use SFTP for encrypted transfer" in combined
    assert "Browse FTP Folder" in combined
    assert "Browse SFTP Folder" in combined
    assert "FTPS" not in combined


def test_docs_describe_windows_network_share_login_guidance() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    first_run = (repo_root / "FIRST_RUN.md").read_text(encoding="utf-8")
    combined = f"{readme}\n{first_run}"

    assert "Windows Network Login" in combined
    assert r"\\192.168.23.6\Backup\1.55\folder" in combined
    assert "Explorer access does not always mean a background Python process or service has the same SMB session." in combined
    assert "mapped drives may not exist in that session" in combined
