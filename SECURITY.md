# SECURITY.md — database, sandbox, perimeter

Three enforcement layers, each independent of the others:

1. PostgreSQL refuses any write or DDL on the AI path (engine-level, not
   string filtering).
2. Every LLM-generated script runs in a `bwrap` namespace as a non-root user
   with no network, a read-only root filesystem, one writable scratch dir, and
   hard time and memory caps.
3. The web app is reachable only through a Cloudflare Tunnel, behind Cloudflare
   Access, with the app's own OTP auth on top.

## 1. PostgreSQL read-only role

The data bank is `excise_bank` on the local cluster (`18/main`, port 5432,
`127.0.0.1`). Three roles:

| Role | Rights | Used by |
|---|---|---|
| `excise_owner` | owns the schema; `CREATE`/`ALTER` | migrations only, run by the operator |
| `excise_etl` | `INSERT`/`UPDATE`/`DELETE` on data tables + `etl.*`; no DDL | `etl/` cron jobs |
| `excise_ro` | `SELECT` on `analytics.*` only; `default_transaction_read_only = on` | the orchestrator (the AI path) |

### Provisioning script (`db/roles.sql`)

Run once by the operator as a superuser (`psql -U postgres -d excise_bank -f
db/roles.sql`). `db:provision` is MariaDB-only and is not used here.

```sql
-- Owner (schema DDL only; not a login used by any service at runtime)
CREATE ROLE excise_owner LOGIN PASSWORD :'owner_pw';
ALTER DATABASE excise_bank OWNER TO excise_owner;

-- ETL writer: data tables, kb.*, and etl bookkeeping
CREATE ROLE excise_etl LOGIN PASSWORD :'etl_pw';
GRANT CONNECT ON DATABASE excise_bank TO excise_etl;
GRANT USAGE ON SCHEMA public, kb, etl TO excise_etl;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public, kb, etl TO excise_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public, kb, etl TO excise_etl;
ALTER DEFAULT PRIVILEGES FOR ROLE excise_owner IN SCHEMA public, kb, etl
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO excise_etl;
-- no CREATE: excise_etl cannot add or drop tables

-- Read-only AI role: analytics views + the knowledge base, nothing else
CREATE ROLE excise_ro LOGIN PASSWORD :'ro_pw';
GRANT CONNECT ON DATABASE excise_bank TO excise_ro;
GRANT USAGE ON SCHEMA analytics, kb TO excise_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics, kb TO excise_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE excise_owner IN SCHEMA analytics, kb
    GRANT SELECT ON TABLES TO excise_ro;

-- excise_ro must not see base data or write anywhere
REVOKE ALL ON SCHEMA public, etl FROM excise_ro;
REVOKE CREATE ON SCHEMA public, kb, analytics FROM PUBLIC;   -- no ad-hoc object creation by anyone
REVOKE ALL ON DATABASE excise_bank FROM PUBLIC;

-- Force read-only at the session level, belt to the transaction's braces
ALTER ROLE excise_ro SET default_transaction_read_only = on;
ALTER ROLE excise_ro SET statement_timeout = '10s';
ALTER ROLE excise_ro SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE excise_ro SET lock_timeout = '2s';
ALTER ROLE excise_ro SET search_path = analytics, kb;
```

`kb.*` is `SELECT`-only to `excise_ro` exactly like `analytics.*`. Retrieval
(FTS or `pgvector`) is a read; the model cannot write to the knowledge base.
Ingestion writes as `excise_etl` only. The retrieval query always adds
`WHERE d.withdrawn_at IS NULL`.

### Why each layer

- `GRANT SELECT` only on `analytics.*` — even a bug in the SQL guard cannot
  reach a statement the role has no privilege for. `INSERT`/`UPDATE`/`DELETE`/
  `TRUNCATE`/`COPY ... TO`/`CREATE`/`ALTER`/`DROP` all fail with a permission
  error before any row changes.
- `default_transaction_read_only = on` on the role — any write is refused even
  on a table where `SELECT` implies nothing, and even inside a function.
- The orchestrator additionally wraps every query in `BEGIN READ ONLY; SET
  LOCAL statement_timeout = '10s'; ...; ROLLBACK` (`MCP_ENGINES.md`
  §run_sql) — a third redundant guard and a hard cap on runaway scans.
- `analytics.*` are views that already filter `deleted_at IS NULL AND
  published_at IS NOT NULL` and never expose the base tables — the LLM cannot
  query unpublished or soft-deleted rows because it is not granted them and
  does not know they exist (`DATA_PIPELINE.md` §Row visibility).
- `search_path = analytics` and `REVOKE ... FROM PUBLIC` mean an unqualified
  name resolves only inside `analytics`; `public` and `etl` are invisible.

### SQL guard in the orchestrator (`sql/guard.py`)

Defense in depth, not the primary control. Parse with `sqlglot`; reject unless:

- exactly one statement (no `;`-separated batch, no trailing `;` with a second
  statement);
- the root is `SELECT` or `WITH ... SELECT`;
- no node of type INSERT/UPDATE/DELETE/MERGE/CREATE/ALTER/DROP/TRUNCATE/
  GRANT/REVOKE/COPY/CALL/DO/SET/VACUUM/ANALYZE;
- every table reference is in schema `analytics` (or unqualified, which
  `search_path` pins to `analytics`);
- no call to a volatile / side-effecting function
  (`pg_read_file`, `pg_sleep`, `lo_*`, `dblink*`, `pg_stat_file`, `nextval`,
  `setval`, anything in `pg_catalog` write helpers);
- a `LIMIT` is present — inject `LIMIT :row_limit` if the LLM omitted it.

A rejection returns the reason to the planner for exactly one re-plan, then a
typed `SQL rejected` error to the user. This applies to model-authored SQL from
both `/query` and the chat's `run_sql_query` tool. `search_knowledge` does not
run model-authored SQL at all — it is a fixed parametrised query
(`websearch_to_tsquery` / a vector search) with the user text bound as a
parameter, so there is no SQL-injection surface there.

### Knowledge base — read paths

The knowledge base pulls from another app on the same box. Both reads are
read-only and least-privilege:

- **`pdf_markdown_pipeline_local` (MariaDB)** — a dedicated user
  `excise_mcp_kb_ro` with `SELECT` on that database only, no other schema, no
  write. Created by the operator (`OPERATOR_SETUP.md` §Knowledge base). The
  sync reads `documents` joined to `sections`/`rule_sets`/`departments`,
  filtered to `visibility='public' AND status='verified' AND deleted_at IS
  NULL`. A non-public or non-verified document is never read.
- **Markdown files** — `~/Sites/pdf-markdown-pipeline/storage/app/public/`,
  group-read for the ETL user. The sync only opens paths taken from a matched
  `documents.markdown_path`; it never lists the tree or follows a path with
  `..` in it.
- **Admin `.md` uploads** — validated in `web/` before they are staged:
  extension is `.md`, size `<= 2 MB`, content decodes as UTF-8, the filename
  is replaced with a generated ULID (the original is kept only as a display
  label), no path separators reach disk. Stored on a dedicated `kb-uploads`
  disk that is on the Apache `ReadWritePaths` list. The ETL reads that disk;
  `web/` never writes `kb.*`.
- **Withdrawn content** — a document that loses public/verified status
  upstream, or an upload an admin withdraws, gets `kb.documents.withdrawn_at`
  set. Retrieval filters it out; the row and its chunks stay for audit and
  are purged on a slow schedule, not immediately.

### Network

`postgresql.conf` keeps `listen_addresses = 'localhost'` for this project. If
DBeaver-over-Tailscale access to `excise_bank` is ever wanted, follow
`~/Sites/infra-notes/postgres-tailscale-remote-access.md` exactly — bind the
Tailscale IP, scope the `ufw` rule to `tailscale0`, add a `pg_hba.conf` line
for a **named read-only role only**, never `all`/`admin` over the tailnet.

## 2. Code-execution sandbox

The primitive on this box is **bubblewrap (`bwrap` 0.11.1)**, already
installed. `firejail` is not installed and is not needed. Containers
(Docker/Podman) are also absent and not required.

### Execution user

A dedicated login-less user, created once by the operator (give the command,
do not work around the lack of sudo):

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin excise-sandbox
sudo install -d -o excise-sandbox -g excise-sandbox -m 0700 /var/tmp/excise-charts
```

The orchestrator runs as its own service user (`excise-orch`) and must be able
to `setuid` to `excise-sandbox` for the child. Simplest without granting the
orchestrator broad privilege: a tiny setuid-root helper is avoided — instead
run the sandbox child via `systemd-run --uid=excise-sandbox --pipe
--collect --property=...` (user manager) or give `excise-orch` a single
`sudo` rule scoped to exactly `/usr/bin/bwrap` for `excise-sandbox`
(`/etc/sudoers.d/excise-sandbox`, added with `visudo`, drafted below for the
operator). Decide at Milestone 5; `systemd-run` is preferred because it needs
no sudoers entry.

### `bwrap` invocation (`sandbox/bwrap.py`)

Per render, a fresh scratch dir `/var/tmp/excise-charts/<run-ulid>/` is created
(owned `excise-sandbox`, `0700`), the Parquet result and the script written
into it, then:

```
timeout --signal=KILL 15 \
bwrap \
  --unshare-all \                # new user/pid/net/ipc/uts/cgroup/mount ns
  --die-with-parent \
  --new-session \
  --clearenv \
  --setenv PATH /usr/bin:/bin \
  --setenv HOME /scratch \
  --setenv MPLBACKEND Agg \
  --setenv MPLCONFIGDIR /scratch/.mpl \
  --setenv TMPDIR /scratch/tmp \
  --ro-bind /usr /usr \
  --ro-bind /bin /bin \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --ro-bind /etc/alternatives /etc/alternatives \
  --ro-bind /opt/excise-orch/venv /opt/excise-orch/venv \   # the engine venv, read-only
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --bind /var/tmp/excise-charts/<run-ulid> /scratch \       # the ONLY writable path
  --chdir /scratch \
  --cap-drop ALL \
  --                                        \
  /opt/excise-orch/venv/bin/python /scratch/chart.py
```

- `--unshare-all` includes `--unshare-net` — **no network**. No loopback, no
  DNS, no sockets. A script that tries to `urlopen` or connect gets an
  immediate error.
- Root filesystem is read-only bind mounts of `/usr` `/bin` `/lib*` only.
  `/scratch` is the sole writable path; a write anywhere else fails with
  `EROFS`.
- `--clearenv` + explicit `--setenv` — no host environment, no secrets, no
  `DATABASE_URL`, no bearer token reachable from inside.
- `--cap-drop ALL`, `--unshare-user` (via `--unshare-all`) — the process is
  unprivileged and cannot regain privilege.
- `--die-with-parent` — if the orchestrator worker dies, the sandbox child
  dies with it.

### Resource limits

Applied to the child before `exec` (via `resource.setrlimit` in a
`preexec_fn`, or `systemd-run --property=`):

| Limit | Value | Guards against |
|---|---|---|
| `timeout --signal=KILL 15` (wall clock) | 15 s | infinite loops, `while True` |
| `RLIMIT_CPU` | 12 s soft / 15 s hard | CPU-bound spin |
| `RLIMIT_AS` (address space) | 1024 MB | memory exhaustion |
| `RLIMIT_FSIZE` | 64 MB | filling the disk with one huge file |
| `RLIMIT_NOFILE` | 64 | fd exhaustion |
| `RLIMIT_NPROC` | 16 | fork bombs (also capped by the pid namespace) |
| `MemoryMax=` (if `systemd-run`) | 1200 M | OOM-kill the whole unit, not the host |

`systemd-run --scope --property=MemoryMax=1200M
--property=TasksMax=16 --property=CPUQuota=100%` is the cleaner way to apply
the cgroup limits and is preferred over `preexec_fn` rlimits where available.

### What the script can and cannot do

Can: read `/scratch/data.parquet`, use `pandas`/`numpy`/`scipy`/`matplotlib`/
`seaborn`/`plotly`/`kaleido`, write `chart.{png,svg,pdf,plotly.json}` into
`/scratch`, print to stdout (last 4 KB is captured).

Cannot: open a socket, resolve a hostname, read anything under `/home`,
`/etc` (beyond `/etc/alternatives`), `/root`, `/var` (beyond its own scratch),
write outside `/scratch`, spawn more than 16 procs, run longer than 15 s, use
more than ~1 GB, `import` a package not in the pinned venv, escalate
privilege, or see the orchestrator's environment.

### After the render

The orchestrator copies the declared outputs out of `/scratch` to the Laravel
`local` disk (the `chart_artifacts` path), then removes the scratch dir. A
sweeper (systemd timer) deletes any `/var/tmp/excise-charts/*` older than 1 h
in case a crash left one behind.

### `/etc/sudoers.d/excise-sandbox` (draft, operator applies with `visudo`)

Only needed if the `systemd-run` route is not used:

```
excise-orch ALL=(excise-sandbox) NOPASSWD: /usr/bin/bwrap *
```

Scoped to one command, one target user. Add with `sudo visudo -f
/etc/sudoers.d/excise-sandbox` — never `tee` a sudoers file
(`~/Sites/infra-notes/cpu-thermal-and-apache-procfs.md` records why).

## 3. Perimeter — Cloudflare Tunnel and Access

Follows `~/Sites/infra-notes/laravel-apps-deploy.md`. This is the first app on
the account to add Cloudflare Access.

### Tunnel

The account's `~/.cloudflared/cert.pem` covers the `exciseup.in` zone only.
Hostname: **`analytics.exciseup.in`**.

```bash
cloudflared tunnel create excise-mcp-dashboard
# note the UUID it prints; a <uuid>.json credentials file lands in ~/.cloudflared/
cloudflared tunnel route dns --overwrite-dns <uuid> analytics.exciseup.in
```

Use `--overwrite-dns` and route by UUID, not by name — the route-by-name
gotcha in `laravel-apps-deploy.md` pointed a CNAME at the wrong tunnel once.

`~/.cloudflared/excise-mcp-config.yml`:

```yaml
tunnel: <uuid>
credentials-file: /home/subhan/.cloudflared/<uuid>.json

ingress:
  - hostname: analytics.exciseup.in
    service: http://127.0.0.1:8084
  - service: http_status:404
```

systemd `--user` unit `~/.config/systemd/user/excise-mcp-dashboard-tunnel.service`
running `cloudflared tunnel --config
~/.cloudflared/excise-mcp-config.yml run`, `WantedBy=default.target`, enabled
via the existing `loginctl enable-linger subhan`.

Apache vhost on `127.0.0.1:8084` (bind loopback explicitly, do not rely on
`ufw` alone — `laravel-apps-deploy.md` §"make the bind match the intent"),
`DocumentRoot .../web/public`, and append
`/home/subhan/Sites/excise-mcp-dashboard/web/storage` and
`.../web/bootstrap/cache` to the shared
`/etc/systemd/system/apache2.service.d/override.conf` `ReadWritePaths=` line —
**edit in place, never overwrite** (that file has been clobbered before). Then
`sudo systemctl daemon-reload && sudo systemctl restart apache2`. Give the
operator these commands; Claude has no sudo.

### Cloudflare Access (Zero Trust)

In the Cloudflare Zero Trust dashboard for the account:

1. **Add an application** — Self-hosted, `analytics.exciseup.in`, whole
   hostname (`*` path).
2. **Policy — Allow**: match on `Emails ending in @<the department domain>`
   and/or an explicit email list of the authorized analysts, plus require a
   login method (One-time PIN to email is enough for an internal tool; add
   Google as an IdP if the department has Workspace).
3. **Policy — everything else: Block** (default deny).
4. **Session duration**: 24 h.
5. **Service token** for the orchestrator health check is not needed — `/health`
   is loopback-only and never passes through Cloudflare.
6. Turn on **"Enable automatic cloudflared authentication"** so the tunnel
   only accepts requests carrying a valid Access JWT (`Cf-Access-Jwt-Assertion`).
7. In the Laravel app, verify the `Cf-Access-Jwt-Assertion` header on every
   request (middleware `VerifyCloudflareAccess`): fetch the account's Access
   public keys from
   `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs` (cache 1 h),
   validate the JWT `aud` against the application's AUD tag. A request without
   a valid assertion is rejected even if it somehow reached Apache. This makes
   Access a hard gate, not just an edge redirect.

### App-level auth behind Access

The OTP-login + magic-link stack from `~/Sites/upexcise-stats-dashboard` still
runs — Access proves "an authorized person", the app login proves "this
person, with this role". Roles: `Admin` (manage users, see all ledgers,
manage ETL source registry) and `Analyst` (ask questions, see own ledger,
export). RBAC copied and trimmed from the sibling.

### Headers, logging, rate limits

- Port `SecurityHeaders` middleware: CSP allowing Tailwind Play CDN, jsDelivr
  (Chart.js / Plotly, the chat's `marked` + highlighter), Google Fonts, and
  `connect-src 'self'` for the SSE endpoints; HSTS; `X-Frame-Options: DENY`;
  `X-Content-Type-Options: nosniff`; `Referrer-Policy: same-origin`;
  `X-Robots-Tag: noindex` on the whole site (this is not a public dashboard).
- Port `LogMutation` — an `activity_logs` row for every non-GET authenticated
  request, including every `ask`, every chat message, every knowledge upload,
  and every Google connect/disconnect.
- Rate limiters in `AppServiceProvider`: `login`, `two-factor`,
  `password-reset` from the sibling; `ask` and `chat` keyed by user id, start
  10/min.
- The orchestrator refuses any `/query` or `/chat` call whose bearer token
  does not match `ORCH_BEARER_TOKEN` (constant-time compare), logs the
  request-id, and never logs the token or the DB password.
- Chat rendering: assistant Markdown is rendered client-side with output
  sanitised (no raw HTML passthrough); a fenced code block is display-only,
  never executed in the browser. Retrieved knowledge snippets are shown as
  quoted text with the source link, not rendered as live Markdown from an
  untrusted document.

## 4. Google OAuth

`web/` connects a user's Google account so the ETL can read that person's
Drive, Sheets, and Docs. This is additive — the service-account path stays for
server-owned content.

### Consent screen and scopes

- Scopes, all read-only and the minimum needed:
  `.../auth/drive.readonly`, `.../auth/spreadsheets.readonly`,
  `.../auth/documents.readonly`.
- `drive.readonly` is a **restricted** scope. In a Google Cloud project with
  the consent screen set to **Internal** (the department's Google Workspace),
  restricted scopes work for users in that Workspace with no Google
  verification. If the consent screen is **External**, `drive.readonly`
  triggers Google's app-verification and a CASA security assessment before
  more than 100 users can connect. Prefer **Internal** — `OPERATOR_SETUP.md`
  §Google Cloud has the setup and this decision point. If Internal is not
  possible, either accept the External test-user cap (100 users, no
  verification) or narrow to `drive.file` (only files the user explicitly
  picks) to avoid the restricted-scope process.
- Request `access_type=offline` and `prompt=consent` so Google returns a
  refresh token on first connect.

### Token handling

- `laravel/socialite` (Google provider) runs the flow. The callback stores one
  `google_connections` row per user: `user_id`, `google_sub` (the stable
  account id), `email`, `scopes`, `refresh_token` (**`Crypt`-encrypted**,
  Laravel `APP_KEY`), `access_token` + `expires_at` (short-lived, may be left
  null and re-minted on demand), `created_at`, `last_used_at`,
  `revoked_at`.
- The refresh token is written once, read only by the token-refresh code, and
  never returned in any HTTP response or Livewire payload. Log lines about a
  connection use `google_connections.id` and the masked email, never a token.
- The ETL gets a fresh access token by reading the encrypted refresh token
  over loopback: either `web/` exposes an internal `GET
  /internal/google-token/{connection}` (bearer-auth, `127.0.0.1` only) that
  returns a short-lived access token, or the ETL holds `client_id` /
  `client_secret` in `etl/.env` and refreshes directly with `google-auth`
  against the stored refresh token. Pick one at Milestone 1; the internal
  endpoint keeps the client secret in one place (`web/`).
- **Disconnect**: the user (or an admin) hits disconnect → `web/` calls
  Google's token-revoke endpoint, then sets `revoked_at` and clears the
  encrypted token. Any `source_registry` row bound to that connection is
  disabled and flagged on the "Connected sources" screen.
- **Scope of trust**: a connected token can read everything in that user's
  Drive within the granted scopes. Only connect accounts that are supposed to
  feed the data bank, register specific folders / sheets / docs rather than
  "all of Drive", and review connections periodically. The `drive.file`
  fallback above removes the broad-read concern entirely if it becomes one.

### `VerifyCloudflareAccess` and the OAuth routes

The Socialite redirect and callback routes are behind Cloudflare Access and
the app login like everything else — a stranger cannot reach
`/google/connect`. The Google `redirect_uri` is
`https://analytics.exciseup.in/google/callback`, registered in the Cloud
project; it only resolves through the tunnel.

### Secrets

| Secret | Location | Perms |
|---|---|---|
| `web/.env` `APP_KEY`, MariaDB creds, Resend key, `ORCH_BEARER_TOKEN`, `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | `web/.env` | `600`, not committed |
| `orchestrator/.env` `ORCH_BEARER_TOKEN`, `DATABASE_URL_READONLY` | `orchestrator/.env` | `600`, not committed |
| `etl/.env` `DATABASE_URL_ETL`, `GOOGLE_APPLICATION_CREDENTIALS` path, KB MariaDB creds, (optionally `GOOGLE_CLIENT_ID`/`SECRET` if the ETL refreshes tokens directly) | `etl/.env` | `600`, not committed |
| Postgres role passwords | set once via `db/roles.sql` with `psql -v`, then only in `orchestrator/.env` / `etl/.env` | — |
| Google service-account JSON | a path outside the repo, referenced by `GOOGLE_APPLICATION_CREDENTIALS` | `600`, owned by the ETL user |
| Google OAuth **refresh tokens** (per user) | `google_connections.refresh_token`, `Crypt`-encrypted with `APP_KEY`, in `web/`'s MariaDB | DB row, never in a file, never logged |
| KB MariaDB read-only user (`excise_mcp_kb_ro`) password | `etl/.env` | `600` |
| Tunnel credentials, `cert.pem` | `~/.cloudflared/` | as-is, gitignored by not being in the repo |

`.gitignore` covers `**/.env`, `**/*.env` (keeping `*.env.example`), `*.pem`,
`*credentials*.json`, `*service-account*.json`, `web/storage/`, `**/.venv/`,
`**/__pycache__/`; `/var/tmp` and the KB Markdown tree are outside the repo.

## Incident-response quick reference

- **LLM produced a destructive statement**: it cannot execute — `excise_ro`
  has no write privilege and the transaction is `READ ONLY`. The guard logs
  it; review the prompt that produced it.
- **A script tried to exfiltrate data**: no network in the sandbox — the
  connection fails. `stdout_tail` and the violation log show the attempt.
- **Runaway query**: `statement_timeout = 10s` cancels it; the pool connection
  is returned; the user sees `query timeout`.
- **Sandbox won't die**: `timeout --signal=KILL` and `--die-with-parent`; the
  sweeper timer cleans scratch. If a child survives (should not), the
  `excise-sandbox` user has no login and owns nothing but scratch.
- **Tunnel down**: `systemctl --user status excise-mcp-dashboard-tunnel`;
  restart it; the app is simply unreachable meanwhile — no data exposure.
- **Suspected bearer-token leak**: rotate `ORCH_BEARER_TOKEN` in both `.env`
  files, restart both services.
- **Suspected Google token compromise**: disconnect the affected
  `google_connections` row (revokes at Google, clears the encrypted token),
  disable its `source_registry` sources, rotate `GOOGLE_CLIENT_SECRET` in the
  Cloud console and `web/.env` if the client secret itself may be exposed.
- **A withdrawn document still shows in chat citations**: check the retrieval
  query applies `withdrawn_at IS NULL`; run `etl sync --source pdf_pipeline_docs`
  to re-sync withdrawal state.
- **Model wrote to `kb.*` or `analytics.*`**: not possible — `excise_ro` has
  `SELECT` only and the session is `READ ONLY`. Treat any such report as a
  role-misconfiguration bug and re-run `db/roles.sql` verification.
