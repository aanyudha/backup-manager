# Changelog

## [0.3.0] - Unreleased

### Added

- Internal backup scheduler
- Daily, weekly, and monthly schedule support
- Scheduler state tracking
- Scheduler UI
- Optional auto-start scheduler setting

### Limitations

- Scheduler only runs while the desktop app is open
- Windows Task Scheduler and cron integration are planned for later

## [0.2.0] - Unreleased

### Added

- Native MySQL gzip compression
- SHA256 backup verification metadata
- Backup metadata repository
- Retention policy for file-based backup artifacts

### Changed

- Backup service now runs verification and retention after successful backups

### Limitations

- Folder backup directories are not hashed in v0.2.0
- Folder retention is not applied unless a file artifact is recorded in metadata

## 0.1.0

- Initial MVP release.
- Added MySQL backup profiles and `mysqldump` execution support.
- Added folder backup profiles with local copy, `robocopy`, `rsync`, and SFTP transports.
- Added a PySide6 desktop UI for dashboard, profile management, logs, and settings.
- Added JSON-backed profile and settings storage for the MVP.
