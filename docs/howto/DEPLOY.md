# Deploy

For the developer: how to set up the server and deploy (blueprint §13.13). Agents run `make deploy` only when asked.

## One-time server setup

1. **Instance.** In the OCI console create a VM.Standard.E2.1.Micro with **Canonical Ubuntu 24.04 Minimal** (x86_64), default boot volume, SSH key only.
2. **Network.** In the VCN security list (or an NSG) add ingress TCP 80 and 443 from `0.0.0.0/0` (UDP 443 is optional, for HTTP/3).
3. **Clone and bootstrap.** On the server:

   ```bash
   git clone https://github.com/GrimNej/Moira.git ~/moira && cd ~/moira
   ./deploy/scripts/bootstrap_server.sh
   ```

   The script is idempotent. It opens ports 80/443 in the host firewall (`firewall.sh`), adds 2 GB swap with `vm.swappiness=10`, limits journald to 200 MB, installs the packages, Caddy and uv, turns off SSH passwords and root login, creates the `moira` user and the folders of §5.7, downloads the embedding model once, and installs the systemd units and the Caddyfile.
4. **Secrets** (all `root:root`, mode `0600`):
   - `/etc/moira/env`: every variable from `.env.example` with real values, `APP_ENV=prod`, `DATA_DIR=/var/lib/moira`, `HF_HUB_OFFLINE=1`.
   - `/etc/moira/duckdns.env`: `DUCKDNS_DOMAIN=<name>` and `DUCKDNS_TOKEN=<token>`.
   - `/etc/moira/caddy.env`: `MOIRA_HOST=<name>.duckdns.org`.
5. **Start** DuckDNS and Caddy: `sudo systemctl start duckdns.timer && sudo systemctl restart caddy`. Check `journalctl -u caddy` for the Let's Encrypt certificate (Appendix J18). If DuckDNS is down, use `<public-ip>.sslip.io` as `MOIRA_HOST`.

## Deploying

From the laptop, on a clean `main` whose CI is green:

```bash
MOIRA_SSH=ubuntu@<host> MOIRA_HOST=<name>.duckdns.org make deploy
```

`deploy/scripts/deploy.sh`:

1. Refuses a dirty tree or a commit whose `ci` workflow is not `success`.
2. Builds the web app locally (Node never runs on the server).
3. Uploads `backend/` (no `.venv`, no tests), `web/dist/` and the deploy scripts to `/opt/moira/releases/<sha>/`, with a `VERSION` file holding `git describe`.
4. On the server: `uv sync --frozen --no-dev` on the system Python 3.12, runs migrations (each database is snapshotted first), switches `/opt/moira/current`, restarts `moira`.
5. Smoke test: `/api/health` must return the new version within 30 s, then `deploy/scripts/smoke.sh` (one save and one question on a smoke-test sandbox) when it exists.
6. Keeps the last 3 releases and prints a line for the DEVLOG.

## Rollback

If the smoke test fails, the script switches `current` back to the previous release and restarts the service by itself. To roll back by hand:

```bash
ssh ubuntu@<host>
ls -1t /opt/moira/releases            # newest first
ln -sfn /opt/moira/releases/<sha> /opt/moira/current.new && mv -T /opt/moira/current.new /opt/moira/current
sudo systemctl restart moira
```

Migrations are forward-only and additive during the hackathon, so an older release runs on a newer schema.
