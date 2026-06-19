# First Run Guide

## Requirements

- Python 3.12 or newer
- `pip`
- A writable local checkout of the repository
- For MySQL backups: `mysqldump` installed or available via a configured path
- For MySQL restores: `mysql` installed or available on `PATH`
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
5. Optionally enable `Compress SQL backup as .sql.gz` for streamed gzip output.
6. Optionally enable `Retention` and set `Retention Days` to a value greater than `0`.
7. Optionally enable `Enable Schedule`, choose `manual`, `daily`, `weekly`, or `monthly`, and fill the matching schedule fields.
8. Optionally leave `Run if missed` enabled so a missed daily, weekly, or monthly run still starts later that same day while the app is open.
9. Use `Test Connection` to validate the credentials.
10. Use `Load Database List` to fetch selectable databases.
11. Click `Save Profile`.

## How To Create a Folder Profile

1. Open the `Folder Profiles` tab.
2. Enter the profile name, source path, and destination path.
3. Choose `auto` unless you need a specific engine.
4. Choose a mode:
   - `copy_new_changed`
   - `sync_without_delete`
   - `mirror_with_delete`
5. Optionally enable `Retention` and set `Retention Days` to a value greater than `0`.
6. Optionally enable `Enable Schedule`, choose the schedule type, and fill the matching time, weekday, or day-of-month fields.
7. Fill SFTP fields only when using an SFTP-based profile.
8. Click `Validate`, then `Save Profile`.

## How To Run a Backup

1. Save the profile first.
2. Go to `Dashboard`, `MySQL Profiles`, or `Folder Profiles`.
3. Choose the profile and click `Run Selected` or `Run Backup`.
4. Watch live output in the dashboard status panel.

## How To Schedule a Backup

1. Open either the `MySQL Profiles` or `Folder Profiles` tab.
2. Edit or create a profile.
3. Enable `Enable Schedule`.
4. Choose one of these schedule types:
   - `manual` keeps the profile out of automatic runs.
   - `daily` uses the `Time` field.
   - `weekly` uses `Time` plus one or more weekday checkboxes.
   - `monthly` uses `Time` plus `Day of Month`.
5. Leave `Run if missed` enabled if you want the app to catch up later that same day after the scheduled minute has passed.
6. Save the profile.

## How To Start and Stop the Scheduler

1. Open the `Scheduler` tab.
2. Use `Refresh` to reload last-run and next-run information.
3. Use `Run Due Now` to perform an immediate due-profile check.
4. Use `Start Scheduler` to begin the internal background loop.
5. Use `Stop Scheduler` to end the background loop.
6. If you want it to start automatically on launch, open `Settings` and enable `Auto-start scheduler when app opens`.

## How To Run a Restore

1. Open the `Restore` tab.
2. For MySQL restore:
   - Enter the SQL file path.
   - Enter the target database, host, port, username, and password.
   - The target database field is required and is where the SQL file will be restored.
   - Optionally enter a custom `mysql` client path.
   - Optionally enable `Create database if missing` if the target database may not exist yet.
   - Use `Validate` to check the SQL file, MySQL client, connection, and target database behavior before restore.
   - Use `Test Connection` if you only want to verify credentials and connectivity.
   - Click `Run Restore`.
3. For folder restore:
   - Enter the backup source folder.
   - Enter the restore destination folder.
   - Click `Validate`, then `Run Restore`.
4. Confirm the prompt carefully:
   - MySQL restore warns that it may overwrite existing database objects in the selected target database.
   - Folder restore warns that matching destination files may be overwritten and that destination-only files will not be deleted.
5. Watch progress in the restore status panel and review entries in `Restore History`.

## Where Logs Are Stored

- Daily app logs: `logs/app_YYYYMMDD.log`
- Backup logs: `logs/{safe_profile_name}_{YYYYMMDD_HHMMSS}.log`
- Daily restore logs: `logs/restore_YYYYMMDD.log`
- Per-run restore logs: `logs/restore_YYYYMMDD_HHMMSS.log`
- Daily scheduler logs: `logs/scheduler_YYYYMMDD.log`

## Where Backup Verification Is Stored

- Metadata file: `config/backup_metadata.json`
- SHA256 appears in the metadata file for successful file-based backups.
- SHA256 and file size are also appended to the backup run log and live output.

## Known MVP Limitations

- Scheduler only runs while the desktop app is open.
- Scheduler does not integrate with Windows Task Scheduler yet.
- Scheduler does not integrate with cron or systemd yet.
- Cloud backup is not implemented yet.
- Encryption is not implemented yet.
- Passwords are stored in JSON for the MVP and must be protected.
- Users should not commit `config/profiles.json` and `config/settings.json`.
- SFTP `mirror_with_delete` is not supported in the MVP.
- Restore has no point-in-time recovery.
- Restore has no incremental restore.
- Restore has no database diff support.
- Folder restore has no versioning and does not mirror-delete destination content.
