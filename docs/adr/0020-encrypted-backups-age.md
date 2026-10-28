# 0020. Encrypted nightly backups to OCI Object Storage with `age`

Date: 2026-10-28
Status: Accepted

## Context

Oracle may reclaim idle Always Free instances, and a memory is meant to last a lifetime.

## Decision

Nightly at 02:30 NPT, snapshot every database with the SQLite backup API, check integrity, compress with zstd, encrypt with `age` to a public key, and upload with rclone to OCI Object Storage (14 daily and 8 weekly copies). The private key lives only on the owner's laptop and an offline copy. A restore drill must finish in under 30 minutes.

## Consequences

- Easier: Data survives losing the server; the server cannot read its own backups.
- Harder: Losing the private key loses the backups.

Blueprint: §13.14.
