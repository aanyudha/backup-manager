# First Run Guide

## Requirements

- Python 3.12 or newer
- `pip`
- A writable local checkout of the repository
- For MySQL backups: `mysqldump` installed or available via a configured path
- Optional transport tools:
  - Windows: `robocopy` is built in on supported systems
  - Linux: `rsync` for faster folder syncs

## Windows First Run

```powershell
cd C:\backup-manager
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/smoke_check.py
python app.py
```

## Linux First Run

```bash
cd ~/backup-manager
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/smoke_check.py
python app.py
```

## How To Create a MySQL Profile

1. Open the `MySQL Profiles` tab.
2. Fill in the profile name, host, port, username, password, and destination folder.
3. Optionally set a custom `mysqldump` path if it is not available on `PATH`.
4. Choose `all`, `single`, or `multiple` for database mode.
5. Use `Test Connection` to validate the credentials.
6. Use `Load Database List` to fetch selectable databases.
7. Click `Save Profile`.

## How To Create a Folder Profile

1. Open the `Folder Profiles` tab.
2. Enter the profile name, source path, and destination path.
3. Choose `auto` unless you need a specific engine.
4. Choose a mode:
   - `copy_new_changed`
   - `sync_without_delete`
   - `mirror_with_delete`
5. Fill SFTP fields only when using an SFTP-based profile.
6. Click `Validate`, then `Save Profile`.

## How To Run a Backup

1. Save the profile first.
2. Go to `Dashboard`, `MySQL Profiles`, or `Folder Profiles`.
3. Choose the profile and click `Run Selected` or `Run Backup`.
4. Watch live output in the dashboard status panel.

## Where Logs Are Stored

- Daily app logs: `logs/app_YYYYMMDD.log`
- Backup logs: `logs/{safe_profile_name}_{YYYYMMDD_HHMMSS}.log`

## Known MVP Limitations

- Scheduler is not active yet.
- Restore is not implemented yet.
- Cloud backup is not implemented yet.
- Encryption is not implemented yet.
- Passwords are stored in JSON for the MVP and must be protected.
- Users should not commit `config/profiles.json` and `config/settings.json`.
- SFTP `mirror_with_delete` is not supported in the MVP.

