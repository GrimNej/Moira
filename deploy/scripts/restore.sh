#!/usr/bin/env bash
# Restore decrypted databases on the server (blueprint §13.14, docs/howto/RESTORE.md).
# Before running: on the laptop, rclone copy → age -d -i key.txt → tar -x, then
#   scp -r system.db memories/ <server>:/var/lib/moira/restore/
# Then on the server: sudo /opt/moira/current/deploy/scripts/restore.sh
set -euo pipefail

data=/var/lib/moira
incoming="$data/restore"
aside="$data/before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
[ -f "$incoming/system.db" ] || { echo "no $incoming/system.db: copy the restored files first"; exit 1; }

echo "== 1. integrity check of the restored files"
for db in "$incoming/system.db" "$incoming"/memories/*.db; do
  [ -f "$db" ] || continue
  result="$(sqlite3 "$db" 'PRAGMA integrity_check;')"
  [ "$result" = ok ] || { echo "integrity_check failed: $db"; exit 1; }
done

echo "== 2. stop the app and move the current files aside to $aside"
systemctl stop moira
mkdir -p "$aside"
for item in system.db system.db-wal system.db-shm memories; do
  [ -e "$data/$item" ] && mv "$data/$item" "$aside/"
done

echo "== 3. move the restored files in"
mv "$incoming/system.db" "$data/system.db"
mkdir -p "$data/memories"
if compgen -G "$incoming/memories/*.db" > /dev/null; then
  mv "$incoming"/memories/*.db "$data/memories/"
fi
chown -R moira:moira "$data/system.db" "$data/memories"

echo "== 4. migrate and start"
sudo -u moira bash -c 'cd /opt/moira/current/backend && set -a && . /etc/moira/env && set +a && /opt/moira/current/backend/.venv/bin/python -m moira.db.migrate --all'
systemctl start moira

echo "== 5. smoke test"
for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/api/health > /dev/null; then
    echo "restored. The previous files are in $aside (delete them once you are sure)."
    exit 0
  fi
  sleep 1
done
echo "the app did not come back: the previous files are in $aside"; exit 1
