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
2. Fill in the profile name, host, port, username, and password.
3. Choose `Destination Type`:
   - `Local Folder`
   - `Network/Mounted Folder`
4. Enter the destination folder.
5. Network destination examples:
   - Windows UNC: `\\server\share\backup`
   - Windows mapped drive: `Z:\backup`
   - Linux mounted share: `/mnt/backup`
   - Linux mounted share: `/media/nas/backup`
6. For Windows UNC destinations, you can optionally open `Windows Network Login` and enter:
   - Username
   - Password
   - Domain
   - `Remember Session` if you want the SMB session kept after the run
7. Use a UNC path such as `\\192.168.23.6\Backup\1.55\folder` when you need Windows network login support.
8. Do not use slash-style paths such as `//192.168.23.6/Backup/1.55/folder`.
9. Explorer access does not always mean a background Python process or service has the same SMB session.
10. Optionally set a custom `mysqldump` path if it is not available on `PATH`, or leave it blank to auto-detect `mysqldump` from `PATH`.
11. Choose `all`, `single`, or `multiple` for database mode.
12. Optionally enable `Compress SQL backup as .sql.gz` for streamed gzip output.
13. Optionally enable `Retention` and set `Retention Days` to a value greater than `0`.
14. Optionally enable `Enable Schedule`.
15. Choose `Schedule Runner`:
   - `Internal App Scheduler` if the app should run the backup while it is open.
   - `External OS Scheduler` if Windows Task Scheduler or Linux cron should run the backup.
   - `Background Service Scheduler` if `--scheduler-service` should run the backup without opening the GUI.
16. Choose `manual`, `daily`, `weekly`, or `monthly`, and fill the matching schedule fields.
17. Optionally leave `Run if missed` enabled so a missed daily, weekly, or monthly run still starts later that same day while the app is open.
18. Use `Test Connection` to validate the credentials.
19. Use `Connect/Test Network Share` or `Test Destination` if you configured a UNC destination.
20. Use `Load Database List` to fetch selectable databases.
21. On older NAS/SMB devices, a successful MySQL dump can still show a post-backup verification warning if the share briefly rejects read or stat calls after the file is written. In that case, confirm the file in Explorer or with `Test Destination`.
22. Click `Save Profile`.

## How To Create a Folder Profile

1. Open the `Folder Profiles` tab.
2. Enter the profile name.
3. Choose `Source Type`:
   - `Local Folder`
   - `FTP Remote Folder`
   - `SFTP Remote Folder`
   - `Rsync Remote/Path`
4. Choose `Destination Type`:
   - `Local Folder`
   - `Network/Mounted Folder`
5. For `Local Folder` source:
   - Use `Source Folder`.
   - Use `Browse Source` if you want to pick a local folder.
6. For `FTP Remote Folder` source:
   - Fill the FTP connection fields.
   - Set `FTP Source Folder`.
   - Use `Browse FTP Folder` to pick the remote source folder.
7. For `SFTP Remote Folder` source:
   - Fill the SFTP connection fields.
   - Set `SFTP Source Folder`.
   - Use `Browse SFTP Folder` to pick the remote source folder.
8. For `Rsync Remote/Path` source:
   - Use `Source Path`.
   - You can use local paths or remote syntax such as `user@host:/path`.
9. Enter the destination folder.
10. Network destination examples:
   - Windows UNC: `\\server\share\backup`
   - Windows mapped drive: `Z:\backup`
   - Linux mounted share: `/mnt/backup`
   - Linux mounted share: `/media/nas/backup`
11. For Windows UNC destinations, you can optionally open `Windows Network Login` and enter:
   - Username
   - Password
   - Domain
   - `Remember Session` if you want the SMB session kept after the run
12. Use a UNC path such as `\\192.168.23.6\Backup\1.55\folder` when you need Windows network login support.
13. Do not use slash-style paths such as `//192.168.23.6/Backup/1.55/folder`.
14. Explorer access does not always mean a background Python process or service has the same SMB session.
15. For scheduled or service backups, prefer UNC paths and configured credentials because mapped drives may not exist in that session.
16. Choose `auto` unless you need a specific engine.
17. Choose a mode:
   - `copy_new_changed`
   - `sync_without_delete`
   - `mirror_with_delete`
18. Optionally enable `Retention` and set `Retention Days` to a value greater than `0`.
19. Optionally enable `Enable Schedule`.
20. Choose `Schedule Runner`:
   - `Internal App Scheduler` if the app should run the backup while it is open.
   - `External OS Scheduler` if Windows Task Scheduler or Linux cron should run the backup.
   - `Background Service Scheduler` if `--scheduler-service` should run the backup without opening the GUI.
21. Choose the schedule type, and fill the matching time, weekday, or day-of-month fields.
22. For FTP in this MVP:
   - FTP is plain FTP.
   - Use SFTP for encrypted transfer.
   - Remote FTP destination upload is not supported.
   - Remote FTP sources copy to local or network-mounted destination folders only.
   - Set `FTP Source Folder` to the remote source folder.
   - Use `Browse FTP Folder` to pick the remote source folder.
   - Use `copy_new_changed` or `sync_without_delete`.
   - Do not use `mirror_with_delete`.
23. For SFTP in this MVP:
   - Remote SFTP destination upload is not supported.
   - Remote SFTP sources copy to local or network-mounted destination folders only.
   - Set `SFTP Source Folder` to the remote source folder.
   - Use `Browse SFTP Folder` to pick the remote source folder.
24. Prefer SFTP over FTP when the server supports it.
25. Use `Connect/Test Network Share` or `Test Destination` if you configured a UNC destination.
26. Click `Validate`, then `Save Profile`.

## How To Run a Backup

1. Save the profile first.
2. Go to `Dashboard`, `MySQL Profiles`, or `Folder Profiles`.
3. Choose the profile and click `Run Selected` or `Run Backup`.
4. Watch live output in the dashboard status panel.

## How To Schedule a Backup

1. Open either the `MySQL Profiles` or `Folder Profiles` tab.
2. Edit or create a profile.
3. Enable `Enable Schedule`.
4. Choose `Schedule Runner`:
   - `Internal App Scheduler` keeps scheduling inside the app.
   - `External OS Scheduler` is for exported Windows Task Scheduler or Linux cron jobs.
   - `Background Service Scheduler` is for `--scheduler-service` mode.
5. Choose one of these schedule types:
   - `manual` keeps the profile out of automatic runs.
   - `daily` uses the `Time` field.
   - `weekly` uses `Time` plus one or more weekday checkboxes.
   - `monthly` uses `Time` plus `Day of Month`.
6. Leave `Run if missed` enabled if you want the app to catch up later that same day after the scheduled minute has passed.
7. Save the profile.
8. Use only one runner mode for a scheduled profile. Do not keep the same profile on both the internal scheduler and an OS scheduler.

## How To Start and Stop the Scheduler

1. Open the `Scheduler` tab.
2. Use `Refresh` to reload last-run and next-run information.
3. Use `Run Due Now` to perform an immediate due-profile check.
4. Use `Start Scheduler` to begin the internal-app background loop.
5. Use `Stop Scheduler` to end the background loop.
6. If you want it to start automatically on launch, open `Settings` and enable `Auto-start scheduler when app opens`.

## How To Export an External Schedule

1. Save a profile with `Enable Schedule` turned on, `Schedule Runner` set to `External OS Scheduler`, and a non-`manual` schedule type.
2. Open the `Scheduler` tab and select that profile in the table.
3. Click `Export External Schedule`.
4. Review the generated register command and the separate run-now command.
5. The export registers an operating system schedule. It does not run the backup immediately.
6. If you change the profile schedule later, export again so the OS scheduler matches the profile.
7. Use `Copy` or `Save` if you want reusable files in `exports/scheduler/`.
8. Remember that export is review-only in `v0.3.1`; the app does not install tasks for you.

## How To Export Service Mode Helpers

1. Open the `Settings` tab.
2. Optionally enable `Run as Service / Background Scheduler Mode`.
3. Set each service-owned profile `Schedule Runner` to `Background Service Scheduler`.
4. Click `Export Windows Service Task` to generate review-only Task Scheduler helper files in `exports/service/`.
5. Click `Export Linux systemd Service` to generate a review-only systemd unit and install script in `exports/service/`.
6. Review the generated files before running any privileged OS commands.
7. The app does not run `schtasks`, `systemctl`, or any install script automatically.

Windows manual install:

1. Export the Windows command.
2. Open Command Prompt or PowerShell with the permissions you want the task to use.
3. Review the command carefully, then run it manually.

Linux manual install:

1. Export the Linux cron line.
2. Review the paths and adapt them for the target Linux machine if needed.
3. Open `crontab -e` on that machine.
4. Paste the reviewed line and save.

## How To Export into `.exe` on Windows

```powershell
cd C:\backup-manager
.venv\Scripts\activate
python -m PyInstaller --noconfirm --windowed --name HeisenbergBackupManager app.py
```

- The built executable is written to `dist\HeisenbergBackupManager\HeisenbergBackupManager.exe`.
- In frozen mode, exported run commands use:
  - `"C:\path\HeisenbergBackupManager.exe" --run-profile-id PROFILE_ID`
- If you rebuild the `.exe` in a different path, export external schedules again so the saved OS command points to the current executable.

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
- On older NAS/SMB devices, post-backup verification may be skipped with a warning if the network briefly rejects read or stat access right after a successful write.

## Known MVP Limitations

- Internal scheduler only runs while the desktop app is open.
- Scheduler export does not auto-install Windows Task Scheduler entries.
- Scheduler export does not auto-edit `crontab`.
- Service helper export does not auto-install Windows Task Scheduler startup entries.
- Service helper export does not auto-install Linux systemd units.
- Cloud backup is not implemented yet.
- Encryption is not implemented yet.
- Passwords are stored in JSON for the MVP and must be protected.
- Users should not commit `config/profiles.json` and `config/settings.json`.
- FTP `mirror_with_delete` is not supported in the MVP.
- SFTP `mirror_with_delete` is not supported in the MVP.
- FTP/SFTP remote destination upload is not supported in the MVP.
- Full SMB transport is not implemented in the MVP.
- Network mount automation is not implemented in the MVP.
- Restore has no point-in-time recovery.
- Restore has no incremental restore.
- Restore has no database diff support.
- Folder restore has no versioning and does not mirror-delete destination content.
