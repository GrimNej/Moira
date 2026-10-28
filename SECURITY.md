# Security

For anyone reviewing Moira's security or reporting a problem.

## Reporting a problem

Please do not open a public issue for a security problem. Use GitHub's private vulnerability reporting on this repository ("Security" tab → "Report a vulnerability"). You will get a reply within 72 hours during the hackathon.

## Threat model summary

The full table is [blueprint §10.1](docs/blueprint/BLUEPRINT.md). It is checked row by row here during the security pass (task T51).

| Threat | Mitigation | Checked |
|---|---|---|
| Strangers spend credits through the public bot | Invite codes; per-user and global caps | ☐ |
| Prompt injection via found content | Only the user's own words can change facts (evidence-substring check) | ☐ |
| SSRF through links | SSRF guard on every hop | ☐ |
| Secrets saved by accident | Masked before storage and before any AI call | ☐ |
| XSS from saved or fetched text | Text nodes only; strict CSP | ☐ |
| CSRF on cookie sessions | `SameSite=Lax` + `X-Moira: 1` header + JSON bodies | ☐ |
| Login link consumed by link previews | Token in the URL fragment, single use, 10 minutes | ☐ |
| Forged Mini App login | `initData` validation; 24 h freshness | ☐ |
| Session theft | Hashed random tokens; `HttpOnly; Secure` | ☐ |
| Malicious uploads | Size limits, magic-byte sniffing, pixel caps, format allowlist | ☐ |
| SQL / FTS injection | Parameterized queries; quoted FTS terms | ☐ |
| Abuse / DoS | Rate limits, body limits, one media job at a time | ☐ |
| Data loss | Encrypted nightly backups; tested restore | ☐ |
| Server compromise | SSH keys only; unprivileged service user; systemd sandboxing | ☐ |
| Leaked tokens in git | gitleaks in pre-commit and CI | ☐ |
| Vulnerable dependencies | Lock files; `pip-audit`, `npm audit`; Dependabot | ☐ |
