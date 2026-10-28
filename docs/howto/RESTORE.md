# Restore

For the developer: how to restore from a backup or rebuild from nothing (blueprint §13.14).

## What is backed up

`system.db` and every `memories/*.db`, every night at 02:30 NPT (`moira-backup.timer` →
`deploy/scripts/backup.sh` → `python -m moira.backup.backup`). Each file is snapshotted with
the SQLite online backup API, checked with `PRAGMA integrity_check`, then
`tar | zstd -19 | age -r $BACKUP_AGE_RECIPIENT` and copied with rclone to
`$BACKUP_RCLONE_REMOTE/daily/` (and `weekly/` on Sundays). Retention: 14 daily, 8 weekly.

Not backed up: `templates/demo.db` (rebuilt by `make demo-template`) and sandboxes (temporary).

The digest shows the last backup; a failed backup messages the owner at once. The result of
each run is in `/var/lib/moira/backups/last.json` and `system.db` `meta.last_backup_at`.

The private age key lives only on the owner's laptop and one offline copy. Without it the
backups cannot be read, by anyone.

## Restore a backup

1. On the laptop, fetch and decrypt the backup you want:

   ```sh
   rclone lsf oci:moira-backups/daily/
   rclone copy oci:moira-backups/daily/moira-YYYY-MM-DD.tar.zst.age .
   mkdir restore && age -d -i ~/moira-backup-key.txt moira-YYYY-MM-DD.tar.zst.age | zstd -d | tar -x -C restore
   ```

2. Copy the databases to the server:

   ```sh
   ssh ubuntu@<host> 'sudo mkdir -p /var/lib/moira/restore && sudo chown $(whoami) /var/lib/moira/restore'
   scp -r restore/system.db restore/memories ubuntu@<host>:/var/lib/moira/restore/
   ```

3. On the server: `sudo /opt/moira/current/deploy/scripts/restore.sh`. It checks integrity,
   stops the app, moves the current files aside (`/var/lib/moira/before-restore-<time>`),
   moves the restored files in, migrates, starts and smoke-tests.

Restoring brings back anything forgotten after that backup was taken. Tell affected users, or
forget those items again.

## Rebuild from nothing

New micro instance → `bootstrap_server.sh` → `make deploy` → restore (above) → point DuckDNS at
the new IP. `deploy/scripts/restore_drill.sh` does all of it against a second instance and
prints how long it took. Target: under 30 minutes.

## Restore drill results

| Date | Where | Backup used | Time | Notes |
|---|---|---|---|---|
| _not yet run_ | | | | Needs the server and a second free instance (developer) |
