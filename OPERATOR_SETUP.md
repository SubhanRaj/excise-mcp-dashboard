# OPERATOR_SETUP.md — steps only the owner can run

Everything here needs `sudo`, a package install, or a change in an external
console (Google Cloud, Cloudflare DNS/Tunnel). Claude has no passwordless sudo
on this box and does not touch `/etc`, `systemctl` beyond `--user`, or service
restarts — so these are collected for you to run, grouped by the milestone in
`ROADMAP.md` that needs them. Each block says where to run it and how to check
it worked.

Box facts this file assumes (from `EVALUATION.md`): Ubuntu, PostgreSQL 18
installed (cluster `18/main`, currently **down**), MariaDB on 3306, Ollama on
`127.0.0.1:11434` with no models, `bwrap` 0.11.1 present, `cloudflared`
present with the `exciseup.in` zone cert, ports 8080–8083 taken.

---

## §0 — Groundwork (Milestone 0)

**Start PostgreSQL and enable it at boot.**

```bash
sudo pg_ctlcluster 18 main start
sudo systemctl enable postgresql
```

Verify:

```bash
pg_lsclusters                 # 18  main  5432  online  ...
sudo -u postgres psql -c "select version();"
```

**Create the sandbox execution user and its scratch directory.**

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin excise-sandbox
sudo install -d -o excise-sandbox -g excise-sandbox -m 0700 /var/tmp/excise-charts
```

Verify:

```bash
id excise-sandbox
ls -ld /var/tmp/excise-charts        # drwx------ excise-sandbox excise-sandbox
```

**Confirm `bwrap` runs unprivileged** (some hardened kernels restrict user
namespaces):

```bash
bwrap --unshare-all --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib \
      --ro-bind /lib64 /lib64 --proc /proc --dev /dev --tmpfs /tmp \
      -- /bin/echo sandbox-ok
```

Expect `sandbox-ok`. If it fails with a namespace error, run:

```bash
sudo sysctl kernel.unprivileged_userns_clone=1
# persist:
echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/00-userns.conf
```

---

## §Models (Milestone 0)

Run as your normal user (Ollama is already running):

```bash
ollama pull qwen2.5-coder:7b-instruct-q4_K_M
ollama pull llama3.1:8b-instruct-q4_K_M
```

Verify:

```bash
ollama list                          # both models listed
ollama ps                            # empty until first use; should show 100% CPU when loaded
```

Optional, for the Milestone 6 model bake-off — pull Gemma to include it in the
picker and the comparison (`EVALUATION.md` §2 Published benchmarks):

```bash
ollama pull gemma2:9b-instruct-q4_K_M     # ~5.8 GB; 8K context
# gemma3:12b needs more RAM — check headroom first
```

Embedding model — **only pull this at Milestone 6 if the retrieval quality
check says FTS is missing sections** (`EVALUATION.md` §2b):

```bash
ollama pull nomic-embed-text         # or: ollama pull bge-m3   (multilingual, larger)
```

---

## §Ollama runtime settings (Milestone 0, applied late)

`EVALUATION.md` §2 Runtime settings calls for three env vars on the Ollama
service that were never actually applied — found because a model left loaded
after a Milestone 2 orchestrator test was still sitting at ~5 GB resident
several minutes later instead of unloading after the documented 30s:

```bash
sudo sed -i '/^Environment="PATH=/a\
Environment="OLLAMA_KEEP_ALIVE=30s"\
Environment="OLLAMA_NUM_PARALLEL=1"\
Environment="OLLAMA_MAX_LOADED_MODELS=1"' /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Verify:

```bash
systemctl show ollama.service -p Environment
# Environment=PATH=... OLLAMA_KEEP_ALIVE=30s OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1
ollama list                                   # both models still there
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b-instruct-q4_K_M","prompt":"hi","stream":false}' >/dev/null
ollama ps                                     # UNTIL should read ~30 seconds from now, not ~5 minutes
```

---

## §Data bank (Milestone 1)

**Create the database and apply the SQL scripts** (they are written in `db/`
by the Milestone 1 work — run this after they exist):

```bash
cd ~/Sites/excise-mcp-dashboard/db
sudo -u postgres createdb excise_bank

# roles first — pass the three RAW passwords via -v, no surrounding quotes:
# roles.sql's :'owner_pw' already quotes them as SQL string literals, so a
# value like "'CHANGE_ME_owner'" here double-quotes it and the literal quote
# characters end up baked into the password (hit this once for real).
sudo -u postgres psql -d excise_bank \
  -v owner_pw="CHANGE_ME_owner" \
  -v etl_pw="CHANGE_ME_etl" \
  -v ro_pw="CHANGE_ME_ro" \
  -f roles.sql

sudo -u postgres psql -d excise_bank -f schema.sql
sudo -u postgres psql -d excise_bank -f analytics_views.sql
sudo -u postgres psql -d excise_bank -f seed_reference.sql
sudo -u postgres psql -d excise_bank -f kb_indexes.sql
```

`roles.sql` creates the three roles, reassigns `excise_bank` and its schemas to
`excise_owner`, and sets the read-only role's session guards. `schema.sql`,
`analytics_views.sql`, and `seed_reference.sql` each `SET ROLE excise_owner` so
every table and view is owned by `excise_owner` and the read-only / ETL grants
apply automatically.

Put the three passwords into the app env files (not into git):
`orchestrator/.env` gets `ro_pw` (as `DATABASE_URL_READONLY`), `etl/.env` gets
`etl_pw` (as `DATABASE_URL_ETL`). `owner_pw` is only used for migrations.

Verify the read-only role is actually read-only:

```bash
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "select count(*) from analytics.districts;"         # works (75 after seeding)
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "create table x(i int);"                            # ERROR: permission denied for schema public
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "insert into kb.documents(origin,origin_ref,title,content_sha256) values('x','x','x','x');"
                                                       # ERROR: cannot execute INSERT in a read-only transaction
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "select * from public.revenues;"                    # ERROR: permission denied for table revenues
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "select * from etl.ingestion_runs;"                 # ERROR: permission denied for schema etl
```

**Create the read-only MariaDB user for the pdf-markdown-pipeline sync**
(Milestone 3 needs this; the pipeline's DB is `pdf_markdown_pipeline_local`):

```bash
sudo mariadb <<'SQL'
CREATE USER 'excise_mcp_kb_ro'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME_kb_ro';
GRANT SELECT ON pdf_markdown_pipeline_local.* TO 'excise_mcp_kb_ro'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
```

Put `CHANGE_ME_kb_ro` in `etl/.env` as `KB_RO_MYSQL_PASSWORD` (`etl/.env.example`
has the full set of `KB_RO_MYSQL_*` vars). Also give the ETL user group read on
the pipeline's Markdown tree:

```bash
# the ETL runs as your user for now; if it later runs as its own user, add that
# user to a group that can read:
ls -ld ~/Sites/pdf-markdown-pipeline/storage/app/public
# should be readable by your user already; no change needed if the ETL runs as you
```

Verify:

```bash
mariadb -h127.0.0.1 -u excise_mcp_kb_ro -p'CHANGE_ME_kb_ro' \
  -e "SELECT visibility,status,COUNT(*) FROM pdf_markdown_pipeline_local.documents GROUP BY 1,2;"
```

**Register the pdf-markdown-pipeline sync as a source** (`excise_etl` already
has `kb.*` write access from `roles.sql`):

```bash
PGPASSWORD='CHANGE_ME_etl' psql -h 127.0.0.1 -U excise_etl -d excise_bank <<'SQL'
INSERT INTO etl.source_registry (name, source, source_ref, target_table, schedule, enabled)
VALUES ('pdf_pipeline_docs', 'pdf_pipeline', 'pdf_markdown_pipeline_local', 'kb', '0 3 * * *', true)
ON CONFLICT (name) DO NOTHING;
SQL
```

Then `etl/.venv/bin/python -m etl sync --source pdf_pipeline_docs` (`etl/README.md`
§Knowledge base has the module notes).

---

## §ETL package (Milestone 1)

```bash
cd ~/Sites/excise-mcp-dashboard/etl
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env
# fill in DATABASE_URL_ETL with the etl_pw set in db/roles.sql
```

Verify:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy .
.venv/bin/pytest
```

---

## §Google Cloud (Milestone 1, only if the Google connect feature is in scope)

**Google Cloud Console, not Firebase.** Everything below —
the project, the OAuth consent screen, enabling Drive/Sheets/Docs, the OAuth
client — is Google Cloud Console (<https://console.cloud.google.com>), the
same console Google API access always goes through. Firebase is a different
product layer on top of a GCP project (Firestore, Firebase Auth, Hosting,
Cloud Functions, push notifications) — this app uses none of it: its own
Fortify + email-OTP auth is already the login, and its data stores are
Postgres and MariaDB, not Firestore. A Firebase project would just be a
second console pointed at the same underlying GCP project for no benefit.
Skip Firebase entirely and work in Cloud Console.

In <https://console.cloud.google.com>:

1. **Create a project** — e.g. `excise-mcp-dashboard`.
2. **OAuth consent screen** — App type. This is the one real decision here,
   and it depends on one fact only the department knows: **do the analysts'
   Google accounts belong to a Google Workspace the department controls?**
   - **Internal** — only selectable if yes. The consent screen is then only
     ever shown to accounts inside that Workspace, and Google's verification
     process does not apply to Internal apps at all, regardless of scope.
     This is the recommended choice: no verification queue, no assessment,
     no review lag, and it stays true as more analysts are added — this is
     the only path with no scaling cost.
   - **External** — the only option if the analysts use ordinary consumer
     Gmail accounts or a Workspace the department doesn't administer. Google
     tiers OAuth scopes by sensitivity, and the tier decides what External
     requires:
     - `documents.readonly` and `spreadsheets.readonly` are **sensitive**
       scopes — Google's standard app-verification review (ownership proof,
       a demo video, a privacy policy URL) applies once past 100 test users.
     - `drive.readonly` is a **restricted** scope — verification *plus* a
       CASA (Cloud Application Security Assessment) security review, which
       is slower and (past the free self-assessment tier) can cost real
       money. Check Google's current CASA tiers/pricing before committing to
       this scope under External.
     - Under 100 users in "Testing" publish status needs no verification at
       all — every analyst must be added as a test user by email, and Google
       shows an "unverified app" warning on first consent. Workable for a
       small pilot group, not a real ceiling to build on.
     - **`drive.file` instead of `drive.readonly`** avoids the restricted
       tier entirely — the trade-off is UX, not security: the analyst picks
       each file via Google's file picker rather than the app browsing their
       whole Drive. Worth it under External if Drive access (not just
       Sheets/Docs) is actually needed.
3. **Enable APIs** — Google Drive API, Google Sheets API, Google Docs API.
4. **Credentials -> Create credentials -> OAuth client ID** — Application type
   "Web application":
   - Authorized redirect URI: `https://visualizer.exciseup.in/google/callback`
     (add `http://localhost:8000/google/callback` too if you preview `web/`
     over `artisan serve` per `laravel-dev-preview-tailscale.md`).
   - Copy the **Client ID** and **Client secret** into `web/.env` as
     `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
5. **Scopes** — add `.../auth/drive.readonly`,
   `.../auth/spreadsheets.readonly`, `.../auth/documents.readonly`.
6. **(Optional) Service account** — for server-owned sheets that do not belong
   to a person. Create it, download the JSON key, store it **outside the
   repo** (e.g. `~/.config/excise-mcp/google-sa.json`, `chmod 600`), point
   `GOOGLE_APPLICATION_CREDENTIALS` in `etl/.env` at it, and share the target
   sheets with the service-account email as Viewer.

Verify: the Connected sources screen's `/google/connect` and `/google/callback`
routes are built (Milestone 5's Phase 4, `web/plan/webui.md` §15 decision 5,
superseding this section's original "Milestone 1" placement) but need this
section's `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` filled in before they can
run. Once done, sign in as an Admin, visit Admin -> Connected sources ->
Connect, complete consent, and confirm a `google_connections` row is written
with an encrypted `refresh_token`.

---

## §orchestrator package (Milestone 2)

```bash
cd ~/Sites/excise-mcp-dashboard/orchestrator
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env
# fill in DATABASE_URL_READONLY with the ro_pw set in db/roles.sql (§Data bank)
# and a real ORCH_BEARER_TOKEN — also put the same token in web/.env's ORCHESTRATOR_TOKEN
```

Verify:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
```

---

## §Sandbox execution route (Milestone 2)

The orchestrator (running as your user, or a dedicated `excise-orch` user)
needs to launch the plot sandbox as `excise-sandbox`. Pick one:

**Preferred — `systemd-run` (no sudoers entry):**

```bash
# check the user manager can run transient units with resource limits:
systemd-run --user --scope --property=MemoryMax=1200M --property=TasksMax=16 \
  -- /bin/echo systemd-run-ok
```

If that works, the orchestrator uses `systemd-run --uid=excise-sandbox ...`.
For `--uid=` to work you may need:

```bash
sudo loginctl enable-linger excise-sandbox
```

**Fallback — a single scoped sudoers rule:**

```bash
sudo visudo -f /etc/sudoers.d/excise-sandbox
# add exactly this line (one command, one target user):
#   excise-orch ALL=(excise-sandbox) NOPASSWD: /usr/bin/bwrap *
```

Never `tee`/hand-edit a sudoers file — `visudo` validates before saving
(`~/Sites/infra-notes/cpu-thermal-and-apache-procfs.md` records why).

---

## §Chart rendering (Milestone 2, optional)

Static chart export (PNG/SVG/PDF) runs through a persistent, isolated
browser the orchestrator starts once at boot (`engines/static_render.py`,
`SECURITY.md` §Static image export). It already works against the box's
existing Google Chrome — no action needed. Installing open-source Chromium
instead is optional and preferred:

```bash
sudo apt install chromium-browser
```

The orchestrator looks for `chromium`/`chromium-browser` on `PATH` first and
only falls back to Chrome if neither is installed; no config change or
restart-order dependency either way — just install it and restart
`excise-orchestrator.service` (`systemctl --user restart
excise-orchestrator.service`) to pick it up. Either browser gets a fresh,
private profile per launch (never the operator's own Chrome profile or
signed-in account — `SECURITY.md` has the detail).

---

## §Octave (Milestone 4)

```bash
sudo apt update
sudo apt install -y octave
```

Verify:

```bash
octave-cli --version
octave-cli --no-gui --norc --eval "disp('octave-ok')"
```

---

## §pgvector (Milestone 6, only if the retrieval quality check calls for it)

```bash
sudo apt install -y postgresql-18-pgvector
sudo -u postgres psql -d excise_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Then the Milestone 3 code path takes over: `ALTER TABLE kb.chunks ALTER COLUMN
embedding TYPE vector(768) ...`, create the HNSW index, backfill with
`etl sync --source kb_embeddings`, set `KB_EMBEDDINGS_ENABLED=true` in
`orchestrator/.env` and `etl/.env`.

Verify:

```bash
sudo -u postgres psql -d excise_bank -c "\dx"          # 'vector' listed
```

---

## §web/ skeleton (Milestone 5)

**Create the operational MariaDB database and its scoped user.** `web/` uses
MariaDB only — `excise_mcp_dashboard_local`, user name = database name, never
root (the fleet `db:provision` convention). The database keeps the
`excise_mcp_dashboard` slug even though the product name is "Excise Data
Visualization".

`php artisan db:provision` is the normal path, but it needs a privileged MySQL
account (this box's `root` is `unix_socket`-auth, so it needs `sudo`), and it
derives the database name from `APP_NAME` — which here would give
`excise_data_visualization_local`, the wrong slug. So provision by hand:

```bash
sudo mariadb <<'SQL'
CREATE DATABASE IF NOT EXISTS excise_mcp_dashboard_local
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'excise_mcp_dashboard_local'@'127.0.0.1'
  IDENTIFIED BY 'CHANGE_ME_web_db';
GRANT ALL PRIVILEGES ON excise_mcp_dashboard_local.*
  TO 'excise_mcp_dashboard_local'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
```

Put `CHANGE_ME_web_db` into `web/.env` as `DB_PASSWORD` (perms `664`, not
`600` — Apache/`www-data` needs group-read via the `subhan` group to serve
this app at all, same as every sibling Laravel app's live `.env`; not
committed). `DB_DATABASE` and `DB_USERNAME` are already
`excise_mcp_dashboard_local` in `.env.example`. Then run the migrations as your
user:

```bash
cd ~/Sites/excise-mcp-dashboard/web
php artisan migrate
```

Verify:

```bash
mariadb -h127.0.0.1 -u excise_mcp_dashboard_local -p'CHANGE_ME_web_db' \
  -e "SHOW TABLES FROM excise_mcp_dashboard_local;"    # migrations, users, sessions, cache, jobs
curl -s http://127.0.0.1:8084/health                   # {"app":"Excise Data Visualization","status":"ok"}
```

---

## §web/ queue worker (Milestone 5, Phase 1)

`RunExciseQuery` (the Ask flow's one-shot `/query` job) runs on `QUEUE_CONNECTION=database`
— nothing processes it until this worker is running. No `sudo` needed, `--user` units only:

```bash
cp ~/Sites/excise-mcp-dashboard/deploy/excise-mcp-dashboard-queue.service \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now excise-mcp-dashboard-queue.service
```

Verify: `systemctl --user status excise-mcp-dashboard-queue.service` shows `active (running)`;
submitting a question on `/ask` moves a `queries` row from `pending` through `running` to
`complete` within a few seconds (watch it with `php artisan tinker` or the MariaDB CLI).

---

## §Apache vhost (Milestone 5)

`web/` deploys behind Apache on `127.0.0.1:8084`, same pattern as the four
sibling apps (`~/Sites/infra-notes/laravel-apps-deploy.md`). `deploy/root-setup.sh`
does the whole thing (vhost, `Listen` line, `a2ensite`, the `ReadWritePaths`
append, reload, and a local + tunnel curl check) and is idempotent — safe to
re-run after moving the app or changing the vhost:

```bash
sudo bash ~/Sites/excise-mcp-dashboard/deploy/root-setup.sh
```

To do it by hand instead:

```bash
sudo tee /etc/apache2/sites-available/excise-mcp-dashboard.conf >/dev/null <<'EOF'
<VirtualHost 127.0.0.1:8084>
    ServerName visualizer.exciseup.in
    DocumentRoot /home/subhan/Sites/excise-mcp-dashboard/web/public

    <Directory /home/subhan/Sites/excise-mcp-dashboard/web/public>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog  ${APACHE_LOG_DIR}/excise-mcp-dashboard-error.log
    CustomLog ${APACHE_LOG_DIR}/excise-mcp-dashboard-access.log combined
</VirtualHost>
EOF

# add the listen port (ports.conf currently has bare Listen 8080..8083)
grep -q '^Listen 127.0.0.1:8084' /etc/apache2/ports.conf || \
  echo 'Listen 127.0.0.1:8084' | sudo tee -a /etc/apache2/ports.conf

sudo a2ensite excise-mcp-dashboard
```

**Append this app's writable paths to the shared ProtectHome override —
EDIT THE LINE IN PLACE, do not overwrite the file** (it holds every sibling
app's paths; a full overwrite has broken a live site before —
`laravel-apps-deploy.md`). This `sed` targets only the `ReadWritePaths=`
line and is a no-op if this app's paths are already there, so it's safe to
re-run:

```bash
sudo sed -i \
  '/^ReadWritePaths=/{/excise-mcp-dashboard/!s#$# /home/subhan/Sites/excise-mcp-dashboard/web/storage /home/subhan/Sites/excise-mcp-dashboard/web/bootstrap/cache /home/subhan/Sites/excise-mcp-dashboard/web/storage/app/kb-uploads#}' \
  /etc/systemd/system/apache2.service.d/override.conf

sudo systemctl daemon-reload
sudo apache2ctl configtest
sudo systemctl restart apache2
```

If `storage/framework/views/*.php` has compiled views from an `artisan`
command run as your own user, Apache (`www-data`) can 500 on
`touch(): Utime failed: Operation not permitted` trying to bump one it
doesn't own (`laravel-apps-deploy.md`'s Blade view-cache gotcha, hit setting
up this exact vhost) — run `cd web && php artisan view:clear` once to fix it,
and again after any future `git pull`/branch switch on the live checkout.

Verify:

```bash
curl -s http://127.0.0.1:8084/health                                   # {"app":"Excise Data Visualization","status":"ok"}
systemctl show apache2.service -p ReadWritePaths | tr ' ' '\n' | grep excise-mcp
```

(`/` itself 404s until Milestone 5 adds a route there — the skeleton only
defines `/health` plus Fortify's own routes.)

---

## §Cloudflare Tunnel (Milestone 6)

Run as your user (the account cert in `~/.cloudflared/cert.pem` covers
`exciseup.in`):

```bash
cloudflared tunnel create excise-mcp-dashboard
# note the UUID it prints; ~/.cloudflared/<uuid>.json is written

cloudflared tunnel route dns --overwrite-dns <uuid> visualizer.exciseup.in

cat > ~/.cloudflared/excise-mcp-config.yml <<EOF
tunnel: <uuid>
credentials-file: /home/subhan/.cloudflared/<uuid>.json

ingress:
  - hostname: visualizer.exciseup.in
    service: http://127.0.0.1:8084
  - service: http_status:404
EOF

mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/excise-mcp-dashboard-tunnel.service <<EOF
[Unit]
Description=cloudflared tunnel for excise-mcp-dashboard
After=network-online.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/subhan/.cloudflared/excise-mcp-config.yml run
Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now excise-mcp-dashboard-tunnel.service
```

Route by UUID with `--overwrite-dns` — routing by name has pointed a CNAME at
the wrong tunnel before (`laravel-apps-deploy.md`).

Verify:

```bash
systemctl --user status excise-mcp-dashboard-tunnel
curl -s -o /dev/null -w '%{http_code}\n' https://visualizer.exciseup.in/    # 302 to /login (the app's own auth)
```

The site is public on the subdomain; the app's Fortify email-OTP login is the
only gate, the same as the other four apps. No Cloudflare Access step.

---

## §After each deploy (Milestone 5+)

Same as the sibling apps — `git pull` on the live checkout is the deploy step:

```bash
cd ~/Sites/excise-mcp-dashboard/web
git pull
composer install --no-dev --optimize-autoloader
php artisan migrate --force
php artisan view:clear        # always — CLI-user vs www-data view-cache ownership 500s
php artisan config:cache
php artisan route:cache
systemctl --user restart excise-mcp-dashboard-queue     # if the queue worker unit exists
```

Restart the Python services after their code changes:

```bash
systemctl --user restart excise-orchestrator
# ETL runs on timers; to force one:  cd ~/Sites/excise-mcp-dashboard/etl && .venv/bin/python -m etl sync --all
```

---

## Quick index

| Need | Section | Milestone |
|---|---|---|
| Start Postgres, sandbox user | §0 | 0 |
| Pull LLM models | §Models | 0 |
| Create `excise_bank`, roles, KB MariaDB user | §Data bank | 1 |
| Google project / OAuth client / service account | §Google Cloud | 1 |
| Sandbox launch route (`systemd-run` or sudoers) | §Sandbox | 2 |
| `apt install octave` | §Octave | 4 |
| `apt install postgresql-18-pgvector` | §pgvector | 6 (conditional) |
| Create `excise_mcp_dashboard_local` MariaDB DB + user | §web/ skeleton | 5 |
| Apache vhost + `ReadWritePaths` | §Apache | 5 |
| `cloudflared tunnel` + systemd unit | §Tunnel | 6 |
