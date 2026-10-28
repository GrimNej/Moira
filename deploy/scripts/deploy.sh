#!/usr/bin/env bash
# Deploy the current commit to the server (blueprint §13.13 "Deploying"). Run from the laptop:
#   MOIRA_SSH=ubuntu@<host> MOIRA_HOST=<name>.duckdns.org make deploy
# Refuses a dirty tree or a commit whose CI is not green. Rolls back if the smoke test fails.
set -euo pipefail

: "${MOIRA_SSH:?set MOIRA_SSH=user@host}"
: "${MOIRA_HOST:?set MOIRA_HOST=<name>.duckdns.org}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo"

echo "== 1. clean tree and green CI"
if [ -n "$(git status --porcelain)" ]; then
  echo "refusing: the working tree is dirty"; exit 1
fi
sha="$(git rev-parse HEAD)"
short="$(git rev-parse --short HEAD)"
if [ "${MOIRA_SKIP_CI_CHECK:-0}" != 1 ]; then
  conclusion="$(gh run list --commit "$sha" --workflow ci --json conclusion -q '.[0].conclusion' 2>/dev/null || true)"
  if [ "$conclusion" != success ]; then
    echo "refusing: CI on $short is '${conclusion:-missing}', not success"; exit 1
  fi
fi
version="$(git describe --tags --always)"

echo "== 2. build the web app locally (never Node on the server)"
(cd web && npm ci --silent && npm run build --silent)

echo "== 3. upload release $short ($version)"
release="/opt/moira/releases/$sha"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/web" "$stage/deploy"
rsync -a --exclude .venv --exclude tests --exclude '__pycache__' --exclude '.mypy_cache' \
  --exclude '.pytest_cache' --exclude '.ruff_cache' --exclude .env backend "$stage/"
rsync -a web/dist "$stage/web/"
rsync -a deploy/scripts "$stage/deploy/"
echo "$version" > "$stage/backend/VERSION"
ssh "$MOIRA_SSH" "mkdir -p '$release'"
rsync -az --delete "$stage/" "$MOIRA_SSH:$release/"

echo "== 4. install, migrate, switch, restart"
previous="$(ssh "$MOIRA_SSH" "readlink -f /opt/moira/current || true")"
ssh "$MOIRA_SSH" bash -s -- "$release" <<'REMOTE'
set -euo pipefail
release="$1"
uv="$(command -v uv || echo "$HOME/.local/bin/uv")"
cd "$release/backend"
"$uv" sync --frozen --no-dev --python /usr/bin/python3.12 -q
# Migrations snapshot each database before changing it (moira.db.migrate).
sudo bash -c "set -a; . /etc/moira/env; set +a; exec sudo -E -u moira \
  '$release/backend/.venv/bin/python' -m moira.db.migrate --all"
ln -sfn "$release" /opt/moira/current.new
mv -T /opt/moira/current.new /opt/moira/current
sudo systemctl restart moira
REMOTE

echo "== 5. smoke test"
ok=0
for _ in $(seq 1 30); do
  got="$(curl -fsS --max-time 3 "https://$MOIRA_HOST/api/health" | jq -r .version 2>/dev/null || true)"
  if [ "$got" = "$version" ]; then ok=1; break; fi
  sleep 1
done
if [ "$ok" = 1 ] && [ -x deploy/scripts/smoke.sh ]; then
  deploy/scripts/smoke.sh "https://$MOIRA_HOST" || ok=0
fi

if [ "$ok" != 1 ]; then
  echo "== smoke test failed: rolling back to ${previous:-nothing}"
  if [ -n "$previous" ]; then
    ssh "$MOIRA_SSH" "ln -sfn '$previous' /opt/moira/current.new && mv -T /opt/moira/current.new /opt/moira/current && sudo systemctl restart moira"
  fi
  exit 1
fi

echo "== 6. keep the last 3 releases"
ssh "$MOIRA_SSH" "cd /opt/moira/releases && ls -1t | tail -n +4 | xargs -r rm -rf"

echo "deployed $version to https://$MOIRA_HOST"
echo "- $(TZ=Asia/Kathmandu date '+%Y-%m-%d %H:%M') NPT: deployed $version ($short), smoke test passed" \
  >> "$repo/.deploy-log"
echo "Add the line above to today's DEVLOG entry."
