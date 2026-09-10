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

## §Data bank (Milestone 1)

**Create the database and apply the SQL scripts** (they are written in `db/`
by the Milestone 1 work — run this after they exist):

```bash
cd ~/Sites/excise-mcp-dashboard/db
sudo -u postgres createdb excise_bank

# roles first — you will be prompted for three passwords via -v
sudo -u postgres psql -d excise_bank \
  -v owner_pw="'CHANGE_ME_owner'" \
  -v etl_pw="'CHANGE_ME_etl'" \
  -v ro_pw="'CHANGE_ME_ro'" \
  -f roles.sql

sudo -u postgres psql -d excise_bank -f schema.sql
sudo -u postgres psql -d excise_bank -f analytics_views.sql
sudo -u postgres psql -d excise_bank -f kb_indexes.sql       # Milestone 3
sudo -u postgres psql -d excise_bank -f seed_reference.sql
```

Put the three passwords into the app env files (not into git):
`orchestrator/.env` gets `ro_pw` (as `DATABASE_URL_READONLY`), `etl/.env` gets
`etl_pw` (as `DATABASE_URL_ETL`). `owner_pw` is only used for migrations.

Verify the read-only role is actually read-only:

```bash
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "select count(*) from analytics.revenues;"          # works
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "create table x(i int);"                            # ERROR: permission denied
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "insert into kb.documents(origin,origin_ref,title,content_sha256) values('x','x','x','x');"
                                                       # ERROR: permission denied / read-only transaction
PGPASSWORD='CHANGE_ME_ro' psql -h 127.0.0.1 -U excise_ro -d excise_bank -c \
  "select * from public.revenues;"                    # ERROR: permission denied for schema public
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

Put `CHANGE_ME_kb_ro` in `etl/.env`. Also give the ETL user group read on the
pipeline's Markdown tree:

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

---

## §Google Cloud (Milestone 1, only if the Google connect feature is in scope)

In <https://console.cloud.google.com>:

1. **Create a project** — e.g. `excise-mcp-dashboard`.
2. **OAuth consent screen** — App type:
   - **Internal** if the department has a Google Workspace and the analysts
     are in it. This is the recommended choice — the restricted
     `drive.readonly` scope then needs no Google verification or CASA
     assessment.
   - **External** only if Internal is impossible. Then either keep under 100
     test users (no verification) or budget for Google's app-verification +
     CASA security assessment before wider rollout. Alternative: request only
     `drive.file` (user-picked files) instead of `drive.readonly` — not a
     restricted scope.
3. **Enable APIs** — Google Drive API, Google Sheets API, Google Docs API.
4. **Credentials -> Create credentials -> OAuth client ID** — Application type
   "Web application":
   - Authorized redirect URI: `https://analytics.exciseup.in/google/callback`
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

Verify: from `web/` (once Milestone 1's minimal Socialite wiring exists),
visit `/google/connect`, complete consent, and confirm a `google_connections`
row is written with an encrypted `refresh_token`.

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

Put `CHANGE_ME_web_db` into `web/.env` as `DB_PASSWORD` (perms `600`, not
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

## §Apache vhost (Milestone 5)

`web/` deploys behind Apache on `127.0.0.1:8084`, same pattern as the four
sibling apps (`~/Sites/infra-notes/laravel-apps-deploy.md`).

```bash
sudo tee /etc/apache2/sites-available/excise-mcp-dashboard.conf >/dev/null <<'EOF'
<VirtualHost 127.0.0.1:8084>
    ServerName analytics.exciseup.in
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
`laravel-apps-deploy.md`):

```bash
sudo nano /etc/systemd/system/apache2.service.d/override.conf
# on the existing ReadWritePaths= line, append (space-separated):
#   /home/subhan/Sites/excise-mcp-dashboard/web/storage
#   /home/subhan/Sites/excise-mcp-dashboard/web/bootstrap/cache
#   /home/subhan/Sites/excise-mcp-dashboard/web/storage/app/kb-uploads

sudo systemctl daemon-reload
sudo apache2ctl configtest
sudo systemctl restart apache2
```

Verify:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8084/        # 200 or a redirect to /login
systemctl show apache2.service -p ReadWritePaths | tr ' ' '\n' | grep excise-mcp
```

---

## §Cloudflare Tunnel (Milestone 6)

Run as your user (the account cert in `~/.cloudflared/cert.pem` covers
`exciseup.in`):

```bash
cloudflared tunnel create excise-mcp-dashboard
# note the UUID it prints; ~/.cloudflared/<uuid>.json is written

cloudflared tunnel route dns --overwrite-dns <uuid> analytics.exciseup.in

cat > ~/.cloudflared/excise-mcp-config.yml <<EOF
tunnel: <uuid>
credentials-file: /home/subhan/.cloudflared/<uuid>.json

ingress:
  - hostname: analytics.exciseup.in
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
curl -s -o /dev/null -w '%{http_code}\n' https://analytics.exciseup.in/    # 302 to /login (the app's own auth)
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
