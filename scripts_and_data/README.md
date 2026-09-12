# scripts_and_data/

Local operator scripts and data for this box — one-off setup and maintenance
scripts, database dumps, source workbooks, anything holding PII or a secret.

Nothing here is committed except this file. `.gitignore` has
`/scripts_and_data/*` with `!/scripts_and_data/README.md`. Same convention as
`~/Projects/pac-recovery-portal` and `~/Projects/excise-revenue-recovery-portal`.

Put new operator scripts here, not in the repo root. `deploy/` is a separate
thing — committed deployment config (Apache vhost, cloudflared, systemd units)
that arrives at Milestone 5.

## Contents

- `bootstrap-infra.sh` — brings up the on-box infrastructure that needs root:
  the PostgreSQL service, the `excise-sandbox` user, the `bwrap` namespace
  check, the empty `excise_bank` database, and the MariaDB database and users
  for `web/` and the KB sync. Run it as your normal user; it calls `sudo`
  itself. Re-runnable — every step checks before it acts. It does not pull
  Ollama models or touch pgvector, Octave, the vhost, or the tunnel; those are
  later milestones (see `OPERATOR_SETUP.md`).
