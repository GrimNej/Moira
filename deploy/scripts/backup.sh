#!/usr/bin/env bash
# Nightly encrypted backup (blueprint §13.14). Run by moira-backup.timer at 02:30 NPT as the
# moira user, in a separate short-lived process so the app is never disturbed.
set -euo pipefail
cd /opt/moira/current/backend
exec /opt/moira/current/backend/.venv/bin/python -m moira.backup.backup
