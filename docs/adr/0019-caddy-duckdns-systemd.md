# 0019. Caddy + DuckDNS + systemd; no containers on the micro VM

Date: 2026-10-28
Status: Accepted

## Context

The micro VM has 1 GB RAM. Containers add memory and complexity. The project has no domain budget.

## Decision

Run Caddy 2 for automatic HTTPS, static files and the reverse proxy; DuckDNS for a free hostname (sslip.io as fallback); systemd for the app, with sandboxing and memory limits. Deploy by rsyncing releases into `/opt/moira/releases/<sha>` and switching a symlink, with a smoke test and rollback.

## Consequences

- Easier: Minimal RAM, simple operations, free HTTPS.
- Harder: Server setup is a script, not an image.

Blueprint: §13.13.
