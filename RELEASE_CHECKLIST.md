# Release Checklist

- [ ] Tests pass on Windows
- [ ] Tests pass on Linux
- [ ] Smoke check passes
- [ ] UI smoke check passes
- [ ] Compressed MySQL backup writes a `.sql.gz` artifact
- [ ] Backup metadata includes SHA256 and file size
- [ ] Retention only deletes metadata-tracked files
- [ ] Windows PyInstaller build starts
- [ ] Linux PyInstaller build starts
- [ ] README reviewed
- [ ] FIRST_RUN reviewed
- [ ] CHANGELOG updated
- [ ] No real credentials in config
- [ ] `git status` checked
- [ ] Tag `v0.2.0` created only after verification
