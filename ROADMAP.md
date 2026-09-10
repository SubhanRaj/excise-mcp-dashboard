# ROADMAP.md — excise-mcp-dashboard

Phased build. Each milestone is a set of checklist items with a stated "done
when" gate. Nothing here is built yet — this repo is documentation only until
the owner approves Phase 4.

Scope note: Milestones 1, 2, and 4 build the reduced design from
`EVALUATION.md` §Right-sizing (one Python engine, direct read-only `asyncpg`,
explicit engine selection). Milestone 3 adds a second engine behind the same
interface. The MATLAB and Mathematica adapters stay documented and unbuilt
until a concrete requirement and a licence exist.

---

## Milestone 0 — Approval and groundwork (no code)

- [ ] Owner reviews all seven docs and replies `Approved. Proceed to Phase 4.`
- [ ] Owner runs the operator-only prerequisites (Claude has no sudo):
  - [ ] `sudo pg_ctlcluster 18 main start` and `sudo systemctl enable
        postgresql` — the cluster is currently down
  - [ ] `sudo useradd --system --no-create-home --shell /usr/sbin/nologin
        excise-sandbox`
  - [ ] `sudo install -d -o excise-sandbox -g excise-sandbox -m 0700
        /var/tmp/excise-charts`
  - [ ] confirm `bwrap --version` works for a non-root user
- [ ] `ollama pull qwen2.5-coder:7b-instruct-q4_K_M`
- [ ] `ollama pull llama3.1:8b-instruct-q4_K_M`
- [ ] Decide the Cloudflare hostname (`analytics.exciseup.in` unless the owner
      prefers another `*.exciseup.in`)
- [ ] Obtain the Google Cloud service-account JSON, place it outside the repo,
      share the target Sheets/Drive folder with its email as Viewer

**Done when:** approval is given, Postgres is running, both models are pulled,
the sandbox user exists.

---

## Milestone 1 — Data bank + ETL

### Database
- [ ] `web/` scaffold is not required yet; create `db/` with:
  - [ ] `db/schema.sql` — the PostgreSQL schema from `DATA_PIPELINE.md`
        (dimensions, fact tables, shops split, reference tables, `etl` schema)
  - [ ] `db/analytics_views.sql` — the `analytics.*` published-only views
  - [ ] `db/roles.sql` — `excise_owner` / `excise_etl` / `excise_ro` from
        `SECURITY.md` §1
  - [ ] `db/seed_reference.sql` — `zones` / `divisions` / `districts` /
        `financial_years` / `license_categories`, seeded from the sibling
        dashboard's seeders and contact-list JSON
- [ ] `createdb -O excise_owner excise_bank`, apply the four scripts in order
- [ ] Verify: `\dt analytics.*` shows the views; `psql -U excise_ro` can
      `SELECT` from `analytics.revenues` and **cannot** `INSERT` anywhere or
      see `public.*`

### ETL
- [ ] `etl/` package: `config.py` (pydantic-settings), `db.py` (asyncpg or
      psycopg pool on `excise_etl`), `run.py` (`etl sync` CLI), `sources/`
      (`gsheets.py`, `gdrive.py`, `excel.py`, `csv.py`), `maps/` (column maps),
      `loader.py` (upsert on natural key), `quarantine.py`
- [ ] Port the note-row / district-resolution / money-normalization logic from
      `~/Sites/upexcise-stats-dashboard/app/Console/Commands/ImportExciseData.php`
      into `etl/normalize.py`
- [ ] `etl.source_registry` rows for the initial sources; `etl.ingestion_runs`
      + `etl.quarantine` writing on every run
- [ ] Excel adapter loads the NITI submission workbooks from
      `~/mentor_portal_db/UP Excise Data Collection/` and reconciles row
      counts against the sibling's verified figures (75 districts; 900
      rows/series on revenues/sales_volumes/operations; ~79,685 shops /
      242,520 shop-years; 3,524 brands; 5,537 brand prices; 72 duty rates; 60
      policy rows)
- [ ] Google Sheets + Drive adapters pull a live test sheet end to end
- [ ] `deploy/` systemd `--user` timers for the schedules in
      `DATA_PIPELINE.md` §Schedules, with `Persistent=true` and an advisory
      lock
- [ ] `OnFailure=` notifier unit mails the run summary via Resend

### Tests
- [ ] `etl/tests/`: each source adapter parses a fixture to the normalized
      shape; re-running a fixture changes no counts; a malformed row is
      quarantined and counted; district-alias resolution; FY parsing; money
      normalization
- [ ] `ruff`, `ruff format --check`, `mypy --strict` green on `etl/`

**Done when:** `etl sync --source niti_full` populates `excise_bank`, the
counts match the sibling's verified import, `analytics.*` returns only
published rows, and `excise_ro` is provably read-only.

---

## Milestone 2 — Orchestrator (Postgres + Python tool)

- [ ] `orchestrator/` scaffold per `MCP_ENGINES.md` §Module layout; venv,
      pinned `requirements.txt` + `.lock`
- [ ] `config.py` Settings; `auth.py` bearer-token dependency (constant-time)
- [ ] `schemas.py`: `QueryRequest` / `QueryResponse` / `SqlPlan` / `PlotPlan` /
      `Stage` / typed errors
- [ ] `sql/schema_card.py` renders `analytics.*` into a prompt schema
      description (table, columns, dtypes, a one-line note each)
- [ ] `llm/client.py`: Ollama async client, `format=`-constrained structured
      output, one-retry validation loop; `llm/prompts.py` with the system
      prompt, schema card slot, and 6–10 few-shot NL->SQL examples for excise
      questions
- [ ] `sql/guard.py`: `sqlglot` single-read-only-SELECT parser with the full
      reject list from `SECURITY.md` §SQL guard; `LIMIT` injection
- [ ] `sql/runner.py`: `asyncpg` pool on `DATABASE_URL_READONLY`,
      `BEGIN READ ONLY` + `SET LOCAL` timeouts + `ROLLBACK`, row cap
- [ ] `engines/base.py`: `IVisualizationEngine` Protocol, registry, errors
- [ ] `engines/python_engine.py`: script harness (Parquet preamble), output
      collection (`plotly.json` / `png` / `svg` / `pdf`), `is_available()`
- [ ] `sandbox/bwrap.py`: build and run the `bwrap` command from `SECURITY.md`
      §2, rlimits / `systemd-run` cgroup caps, artifact copy-out, scratch
      cleanup; decide `systemd-run` vs scoped sudoers with the owner
- [ ] `pipeline.py`: the six stages, `Stage` events, per-stage timing
- [ ] `main.py`: FastAPI app, lifespan (pool, `httpx` client, `ollama` warmup),
      `/health`, `/query` (chunked stage stream + final JSON),
      `/query/{id}/status`
- [ ] `deploy/`: systemd `--user` unit `excise-orchestrator.service` on
      `127.0.0.1:8085`
- [ ] Manual end-to-end from `curl`: a question -> SQL -> rows -> a
      `chart.png` + `chart.plotly.json` -> a summary

### Tests
- [ ] tool schemas round-trip (model -> JSON Schema -> sample payload ->
      validate)
- [ ] guard rejects non-SELECT, multi-statement, cross-schema, volatile-fn;
      integration test: a write attempt fails against real local Postgres via
      `excise_ro`
- [ ] router: explicit `engine` picks the adapter; unknown/unavailable ->
      typed error; default `python`
- [ ] sandbox: past-wallclock killed; socket open fails; write outside
      `/scratch` fails; past-memory killed
- [ ] Ollama client: malformed structured output -> exactly one retry -> typed
      error
- [ ] `ruff` / `ruff format --check` / `mypy --strict` green on `orchestrator/`

**Done when:** `POST /query` with a bearer token turns an excise question into
a validated read-only SQL run plus a sandboxed Python chart plus a summary,
and every failure path returns a typed error with a stage.

---

## Milestone 3 — Second engine (GNU Octave), optional adapters stubbed

- [ ] Owner runs `sudo apt install octave` (Claude has no sudo)
- [ ] `engines/octave_engine.py`: CSV hand-off, `octave-cli --no-gui --norc`
      under the same sandbox, `print()` to `chart.{png,svg,pdf}`,
      `supported_outputs = {"png","svg","pdf"}`, `is_available()` on
      `octave-cli --version`
- [ ] `sandbox/bwrap.py` gains an Octave profile (ro-bind the octave prefix)
- [ ] Router prompt gains one capability line for `octave`
- [ ] Tests: an `.m` script renders a PNG in the sandbox; an unavailable
      Octave is skipped cleanly; the pipeline falls back to a static chart
      when a no-Plotly-JSON engine is chosen
- [ ] `engines/matlab_engine.py` and `engines/wolfram_engine.py` exist as
      documented stubs raising `EngineUnavailable("not configured")`, guarded
      by `ENABLE_MATLAB` / `ENABLE_WOLFRAM` config flags defaulting off, with
      the integration notes from `MCP_ENGINES.md` in the docstring. No
      dependency added, nothing installed.

**Done when:** the LLM can choose `python` or `octave`, both run in the
sandbox, and the proprietary adapters are inert stubs behind off-by-default
flags.

---

## Milestone 4 — Laravel Livewire UI

- [ ] `web/` scaffold: Laravel 13 + Livewire 4 + Fortify, matching the sibling
      dependency set; `php artisan db:provision` -> `excise_mcp_dashboard_local`
      (MariaDB, scoped user)
- [ ] Port auth from `~/Sites/upexcise-stats-dashboard`: OTP login, magic-link
      onboarding + reset, `tests/Feature/Auth/*`
- [ ] Port middleware: `SecurityHeaders` (extend CSP for the FastAPI origin +
      Plotly/Chart.js CDN), `LogMutation`, `HasPrivilege` / `IsAdmin`
- [ ] Port `VerifyCloudflareAccess` middleware (JWT `aud` check against the
      Access certs) — `SECURITY.md` §Cloudflare Access
- [ ] RBAC trimmed to `Admin` / `Analyst`; `AppServiceProvider` rate limiters
      incl. `ask`
- [ ] Migrations: `conversations` (ULID), `messages`, `queries` (prompt, sql,
      engine, row_count, timings JSON, status, request_id), `chart_artifacts`
      (paths, kind), `query_feedback` (thumbs + note)
- [ ] `RunExciseQuery` job: calls the orchestrator with the bearer token,
      persists the ledger rows and artifacts, records stages; queue worker
      systemd `--user` unit with `--timeout` above the orchestrator's timeout
- [ ] Livewire `Ask` component: split-view layout (chat left, canvas right,
      one column under `lg`); submit -> job -> SSE stage stream
      (`Querying database -> Running analysis -> Rendering chart -> Complete`),
      `wire:poll` fallback
- [ ] Chart canvas: render `chart.plotly.json` interactively (Plotly CDN);
      show the data table (`rows_preview`, paginated); show the generated SQL
      (collapsed, copyable); export buttons for PNG / SVG / PDF (serve the
      artifact files) and CSV / XLSX of the rows (reuse the sibling's
      `ExportService`)
- [ ] Query ledger view: every past query with prompt, SQL, timing, engine,
      status, and the thumbs-up/down + note control; filter by user (Admin
      sees all, Analyst sees own)
- [ ] Admin: user CRUD (ported), ETL `source_registry` editor, a read-only
      view of `etl.ingestion_runs` / `etl.quarantine`
- [ ] `deploy/`: Apache vhost on `127.0.0.1:8084`, `DocumentRoot web/public`;
      operator appends `web/storage` + `web/bootstrap/cache` to the Apache
      `ProtectHome` override `ReadWritePaths=` line (edit in place)

### Tests
- [ ] Auth suite (ported)
- [ ] `ask` flow: submit -> `conversations`/`messages`/`queries` rows; mocked
      orchestrator success -> chart artifact + ledger row; mocked error ->
      failed stage shown + ledger row still written
- [ ] `ask` rate limiting; `SecurityHeaders` present; `activity_logs` on
      non-GET; SSE endpoint returns the stage sequence
- [ ] `VerifyCloudflareAccess` rejects a missing/invalid assertion
- [ ] `vendor/bin/pint --dirty` clean

**Done when:** a signed-in analyst asks a question in the browser, watches the
four stages stream, and gets an interactive chart + table + SQL + summary,
with every query in the ledger and exportable.

---

## Milestone 5 — Perimeter, hardening, end-to-end

- [ ] Operator: `cloudflared tunnel create excise-mcp-dashboard`,
      `route dns --overwrite-dns <uuid> analytics.exciseup.in`,
      `~/.cloudflared/excise-mcp-config.yml`, systemd `--user` tunnel unit
      enabled
- [ ] Cloudflare Zero Trust: self-hosted app on `analytics.exciseup.in`,
      Allow policy (authorized emails / domain + OTP or IdP), default Block,
      automatic `cloudflared` authentication on
- [ ] Confirm the app rejects any request without a valid
      `Cf-Access-Jwt-Assertion` even on the loopback port
- [ ] Sandbox hardening pass: re-verify no network, read-only FS, scratch-only
      writes, all rlimits / cgroup caps; add the scratch sweeper timer;
      finalize `systemd-run` vs scoped sudoers
- [ ] `excise_ro` audit: connect as it and attempt writes, cross-schema reads,
      volatile functions, `COPY`, long scans — all must fail or time out
- [ ] Secrets audit: `.env` perms `600`, nothing sensitive committed,
      `.gitignore` covers `**/.env` / `*.pem` / `*credentials*.json` /
      `**/.venv/` / `web/storage/`; service-account JSON outside the repo
- [ ] Security headers / CSP review against the live site (no silently blocked
      CDN); `X-Robots-Tag: noindex` site-wide
- [ ] Load reality check: several queries queued, confirm one-at-a-time
      execution, model swap behavior, memory ceiling under a plot + Postgres +
      inference at once; confirm behavior under the 3.0 GHz thermal cap
- [ ] Backup: `pg_dump excise_bank` on a timer (data is re-derivable from
      sources but a dump saves a re-import); `web/` DB in the existing MariaDB
      backup routine
- [ ] End-to-end test script: 15–20 representative excise questions (revenue
      trends, district comparisons, dispatch volumes, enforcement counts, duty
      rates, shop quotas) run through the browser; record SQL correctness,
      chart correctness, latency; file the failures
- [ ] `DEPLOY.md` written from the actual steps taken (follow the sibling
      `DEPLOY.md` shape)
- [ ] Update `CLAUDE.md` "Build status" and this file

**Done when:** `https://analytics.exciseup.in` is reachable only through
Cloudflare Access, every enforcement layer is verified by trying to break it,
the representative question set passes, and the deploy runbook is written.

---

## Backlog (not scheduled)

- MATLAB engine — needs a MATLAB install + licence that permits multi-user
  deployment + the Go toolchain, and a named toolbox requirement
- Mathematica engine — needs Wolfram Engine/licence and a symbolic /
  high-precision requirement
- `crystaldba/postgres-mcp` mounted as a real MCP server — only if an external
  MCP client (Claude Desktop, an IDE) becomes a second consumer of the data
  bank
- Tailscale access to `excise_bank` for DBeaver — follow
  `infra-notes/postgres-tailscale-remote-access.md`, named read-only role only
- Result caching keyed on normalized SQL + the ETL run id, if repeat questions
  show up in the ledger
- Scheduled/"saved" questions that re-run on a timer and post a chart
