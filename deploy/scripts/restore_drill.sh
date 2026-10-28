#!/usr/bin/env bash
# Restore drill (blueprint §13.14): rebuild on a fresh instance from the newest backup, timed.
# Run from the laptop with a second, empty instance:
#   MOIRA_SSH=ubuntu@<drill-host> MOIRA_HOST=<drill-name>.duckdns.org \
#   AGE_KEY=~/moira-backup-key.txt RCLONE_REMOTE=oci:moira-backups deploy/scripts/restore_drill.sh
# Target: under 30 minutes. Record the result in docs/howto/RESTORE.md and DEVLOG.md.
set -euo pipefail
: "${MOIRA_SSH:?}" "${MOIRA_HOST:?}" "${AGE_KEY:?}" "${RCLONE_REMOTE:?}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
start=$(date +%s)
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "== 1. bootstrap the fresh instance"
scp "$repo/deploy/scripts/bootstrap_server.sh" "$MOIRA_SSH:/tmp/"
ssh "$MOIRA_SSH" "sudo bash /tmp/bootstrap_server.sh"

echo "== 2. deploy the current release"
(cd "$repo" && MOIRA_SSH="$MOIRA_SSH" MOIRA_HOST="$MOIRA_HOST" ./deploy/scripts/deploy.sh)

echo "== 3. fetch and decrypt the newest backup"
latest="$(rclone lsf "$RCLONE_REMOTE/daily/" | sort | tail -1)"
rclone copy "$RCLONE_REMOTE/daily/$latest" "$work/"
age -d -i "$AGE_KEY" "$work/$latest" | zstd -d | tar -x -C "$work"

echo "== 4. copy and restore"
ssh "$MOIRA_SSH" "sudo mkdir -p /var/lib/moira/restore && sudo chown \$(whoami) /var/lib/moira/restore"
scp -r "$work/system.db" "$work/memories" "$MOIRA_SSH:/var/lib/moira/restore/"
ssh "$MOIRA_SSH" "sudo /opt/moira/current/deploy/scripts/restore.sh"

echo "== 5. check from outside"
curl -fsS "https://$MOIRA_HOST/api/health"
mins=$(( ($(date +%s) - start + 59) / 60 ))
echo
echo "restore drill finished in ${mins} min (target < 30). Backup used: $latest"
