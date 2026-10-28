#!/usr/bin/env bash
# One-time server setup for an Oracle E2.1.Micro running Ubuntu 24.04 Minimal (blueprint §13.13).
# Idempotent: safe to run again. Run as the deploy user (with sudo) from a checkout of the repo:
#   ./deploy/scripts/bootstrap_server.sh
# Step 2 (VCN security list: TCP 80/443 from 0.0.0.0/0) is done in the OCI console.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
deploy_user="$(id -un)"

echo "== 3. host firewall"
"$here/firewall.sh"

echo "== 4. swap (2 GB) and low swappiness"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-moira.conf >/dev/null
sudo sysctl --system >/dev/null

echo "== journald limit"
sudo mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=200M\n' | sudo tee /etc/systemd/journald.conf.d/moira.conf >/dev/null
sudo systemctl restart systemd-journald

echo "== 5. packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3.12 python3.12-venv sqlite3 ffmpeg age rclone git unattended-upgrades jq curl rsync zstd \
  debian-keyring debian-archive-keyring apt-transport-https netfilter-persistent
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
fi
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== sshd: keys only, no root login (§10.5)"
printf 'PasswordAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/99-moira.conf >/dev/null
sudo systemctl reload ssh || sudo systemctl reload sshd

echo "== 6. user and folders"
id moira >/dev/null 2>&1 || sudo useradd --system --home /var/lib/moira --shell /usr/sbin/nologin moira
sudo mkdir -p /opt/moira/releases /var/lib/moira/{memories,sandboxes,templates,tmp,backups/staging,models} /etc/moira
sudo chown -R "$deploy_user":"$deploy_user" /opt/moira
sudo chown -R moira:moira /var/lib/moira
sudo chmod 0700 /var/lib/moira
for f in env duckdns.env caddy.env; do
  [ -f "/etc/moira/$f" ] || sudo install -m 0600 -o root -g root /dev/null "/etc/moira/$f"
done
echo "   fill /etc/moira/env (see .env.example), duckdns.env (DUCKDNS_DOMAIN, DUCKDNS_TOKEN)"
echo "   and caddy.env (MOIRA_HOST) before starting the services"

echo "== 7. embedding model (downloaded once, then HF_HUB_OFFLINE=1)"
if [ ! -d /var/lib/moira/models/hub ]; then
  sudo -u moira env HF_HOME=/var/lib/moira/models "$(command -v uv || echo "$HOME/.local/bin/uv")" \
    run --no-project --with model2vec python -c \
    "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-retrieval-32M')" || \
    echo "   model download failed; retry after the first deploy"
fi

echo "== 8. DuckDNS timer, 9. Caddy, 10. systemd units"
sudo install -m 0644 "$repo/deploy/systemd/duckdns.service" "$repo/deploy/systemd/duckdns.timer" \
  "$repo/deploy/systemd/moira.service" "$repo/deploy/systemd/moira-backup.service" \
  "$repo/deploy/systemd/moira-backup.timer" /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/caddy.service.d
sudo install -m 0644 "$repo/deploy/systemd/caddy-moira.conf" /etc/systemd/system/caddy.service.d/moira.conf
sudo install -m 0644 "$repo/deploy/caddy/Caddyfile" /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo systemctl enable duckdns.timer moira-backup.timer moira.service
if [ -s /etc/moira/duckdns.env ]; then sudo systemctl start duckdns.timer; fi
if [ -s /etc/moira/caddy.env ]; then sudo systemctl restart caddy; fi

echo "== done. Next: make deploy (from the laptop)"
free -m | head -3
