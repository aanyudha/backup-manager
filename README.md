# Heisenberg Backup Manager

Heisenberg Backup Manager is an open-source desktop application for creating reusable backup profiles for MySQL databases and folders. The MVP targets Windows and Linux with a PySide6 interface and modular Python services that keep backup logic outside the UI layer.

## Features

- Cross-platform desktop UI built with PySide6
- JSON-backed profile and settings storage for an easy MVP workflow
- MySQL backup profiles with connection testing and database discovery
- Folder backup profiles with automatic engine selection
- MySQL restore support for `.sql` and `.sql.gz` files
- Folder restore support with overwrite-existing behavior
- Local copy, `robocopy`, `rsync`, and SFTP transport support
- Background backup execution with UI-safe worker threads
- Profile-level logs and daily application logs
- Restore history with per-run and daily restore logs
- Test coverage for core repository, platform, and transport behavior

## Supported OS

- Windows 10 / 11
- Windows Server
- Ubuntu
- Debian
- Linux Mint

## Quick Start

Windows:

```bash
cd C:\backup-manager
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Linux:

```bash
cd ~/backup-manager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Local Development

- Runtime settings live in `config/settings.json`.
- Backup profiles live in `config/profiles.json`.
- Safe starter examples are provided in `config/settings.example.json` and `config/profiles.example.json`.
- Do not commit real local config or credential-bearing profile files.

## Smoke Check

Run the lightweight CLI smoke check before opening the UI:

```bash
python scripts/smoke_check.py
```

## Tests

```bash
python -m pytest -q
```

## Restore

- Open the `Restore` tab to access MySQL and folder restore tools.
- MySQL restore supports `.sql` and `.sql.gz` sources and runs through the `mysql` client.
- The `Database` field is the target database that the SQL file will be restored into.
- Enable `Create database if missing` to create that target database before the restore starts.
- If the MySQL client path is left blank, the app searches `PATH`.
- MySQL restore validates the source file, connection settings, target database name, and `mysql` client availability before it starts.
- Folder restore copies files recursively into the destination and overwrites existing files without deleting extra destination data.
- Folder restore creates a missing destination folder during validation if it can do so safely.
- Restore is destructive: MySQL restore may overwrite existing database objects, and folder restore overwrites matching destination files.
- Folder restore does not delete destination-only files.
- Every restore asks for a target-specific confirmation before it starts.

## Restore Logs

- Daily restore logs: `logs/restore_YYYYMMDD.log`
- Per-run restore logs: `logs/restore_YYYYMMDD_HHMMSS.log`
- Restore history is stored in `config/restore_history.json`

## Packaging

Windows:

```bash
python -m PyInstaller --noconfirm --windowed --name HeisenbergBackupManager app.py
```

Linux:

```bash
python -m PyInstaller --noconfirm --name heisenberg-backup-manager app.py
```

- `dist/` output is ignored by git.
- `build/` and `*.spec` are ignored by git.
- Local config files may be created during development or packaging checks.
- Do not commit real `config/profiles.json` or `config/settings.json` files.

## Windows Notes

- `robocopy` is used automatically for local or UNC folder backups when it is available.
- UNC paths are supported by the folder backup engine.
- You can optionally set a custom `mysqldump` path in the profile or in settings.

## Linux Notes

- `rsync` is preferred for automatic folder backups when it is installed.
- If `rsync` is not installed, the app falls back to the built-in local copy transport.
- `robocopy` is never offered on Linux.

## MySQL Backup Notes

- `mysqldump` commands are built with list arguments for safe subprocess execution.
- The app supports backing up all databases, a single database, or multiple databases.
- MySQL passwords are masked in logs and UI output.
- The MVP keeps the `compress` field for future support, but gzip compression is not enabled yet.

## MySQL Restore Notes

- Restore commands are built with list arguments and stdin redirection through `subprocess`, not through a shell.
- MySQL passwords are never written to logs in plaintext.
- Fatal restore output such as `Access denied`, `Unknown database`, and connection failures is treated as a failed restore.
- `.sql.gz` files are decompressed to a temporary SQL file before the restore runs.
- Empty database names are rejected, and database names containing backticks are not allowed.
- If `Create database if missing` is disabled, restore fails fast when the target database does not exist.

## Folder Backup Notes

- `copy_new_changed` copies only new or updated files.
- `sync_without_delete` keeps destination-only files intact.
- `mirror_with_delete` deletes destination-only files for supported transports.
- The local copy transport uses `pathlib`, `os.walk`, and `shutil.copy2`.

## Folder Restore Notes

- The MVP restore mode is overwrite-only.
- Missing destination folders are created automatically.
- Existing files are overwritten, but no files or folders are deleted automatically.
- Validation checks that the destination can be created and written before restore starts.

## SFTP Notes

- MVP support covers remote source to local destination downloads.
- New and changed files are downloaded recursively.
- `mirror_with_delete` is intentionally unsupported for SFTP in the MVP.

## Rsync Notes

- Local and remote rsync syntax is supported.
- Extra rsync arguments can be added per profile.
- The app returns a clear validation error when `rsync` is not installed.

## Security Warning

For the MVP, passwords may be stored in `config/profiles.json`. This is convenient for local testing but not secure for sensitive environments.

- Passwords are masked in logs and command previews.
- Password handling is isolated in the backup and connection services.
- Future work should move credentials to OS keyring or encrypted storage.
- Do not commit `config/profiles.json` or `config/settings.json`.

## Restore MVP Limitations

- No point-in-time recovery
- No incremental restore
- No database diff
- No folder versioning

## License

MIT License.

## Contributing

Contributions are welcome. Please open an issue or pull request with a clear description, keep the architecture modular, add or update tests when behavior changes, and avoid mixing UI logic with backup execution code.
