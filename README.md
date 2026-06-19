# Heisenberg Backup Manager

Heisenberg Backup Manager is an open-source desktop application for creating reusable backup profiles for MySQL databases and folders. The MVP targets Windows and Linux with a PySide6 interface and modular Python services that keep backup logic outside the UI layer.

## Features

- Cross-platform desktop UI built with PySide6
- JSON-backed profile and settings storage for an easy MVP workflow
- MySQL backup profiles with connection testing and database discovery
- Folder backup profiles with automatic engine selection
- Local copy, `robocopy`, `rsync`, and SFTP transport support
- Background backup execution with UI-safe worker threads
- Profile-level logs and daily application logs
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

## Build With PyInstaller

Windows:

```bash
pyinstaller --noconfirm --windowed --name HeisenbergBackupManager app.py
```

Linux:

```bash
pyinstaller --noconfirm --name heisenberg-backup-manager app.py
```

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

## Folder Backup Notes

- `copy_new_changed` copies only new or updated files.
- `sync_without_delete` keeps destination-only files intact.
- `mirror_with_delete` deletes destination-only files for supported transports.
- The local copy transport uses `pathlib`, `os.walk`, and `shutil.copy2`.

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

## License

MIT License.

## Contributing

Contributions are welcome. Please open an issue or pull request with a clear description, keep the architecture modular, add or update tests when behavior changes, and avoid mixing UI logic with backup execution code.

