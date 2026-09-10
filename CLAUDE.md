# CLAUDE.md — excise-mcp-dashboard

Master rules for coding sessions on this repo. Read this, then `ARCHITECTURE.md`,
`EVALUATION.md`, and the doc for whichever component you are touching
(`DATA_PIPELINE.md`, `MCP_ENGINES.md`, `SECURITY.md`). `ROADMAP.md` has the
milestone checklist and the current position in it.

Status: **blueprint only.** No application code, no `composer create-project`,
no virtualenv, no package installs until the owner approves Phase 4.

## What this project is

An on-premise conversational analytics tool for UP Excise departmental figures
(revenue, dispatches, shop quotas, enforcement). A user asks a question in
plain language; a local LLM turns it into a read-only SQL query against a
PostgreSQL copy of the excise data, runs a short analysis/plot script, and the
web UI shows the chart, the table, and the generated SQL.

It sits alongside the four existing departmental Laravel apps on the office AIO
(`~/Sites/infra-notes/laravel-apps-deploy.md`) and follows their deployment
pattern: Apache vhost on a private port, one named Cloudflare Tunnel, systemd
`--user` units for workers.

## Hard constraints (do not violate)

- **No DeepSeek models.** Any family, any quant, any purpose. The model is
  chosen in `EVALUATION.md` from Llama 3.1, Qwen 2.5, or Gemma 2 only.
- **No unsandboxed code execution.** Every LLM-generated script (Python,
  Octave, anything) runs under the sandbox in `SECURITY.md` — non-root user,
  `bwrap` namespace, no network, writable path limited to one scratch dir,
  wall-clock and memory caps. A script never runs directly on the host.
- **No root or write access to Postgres for the AI path.** The orchestrator
  connects as a dedicated `LOGIN` role with `SELECT` only and
  `default_transaction_read_only = on`. `INSERT`/`UPDATE`/`DELETE`/`DDL` are
  refused by the database engine, not by a string filter in application code.
- **No secrets in `.env` for anything that can live elsewhere.** The
  Laravel↔orchestrator bearer token and the Postgres read-only password are the
  two required secrets; both go in the respective `.env` files with `600`
  perms, never committed. Google service-account JSON is referenced by path,
  never inlined.
- **No new Cloudflare zone.** This box's `cert.pem` only covers `exciseup.in`.
  Use a subdomain of it.
- **Claude has no passwordless sudo here.** Anything under `/etc`, any
  `systemctl` beyond `--user`, any service restart: write the exact commands in
  the relevant doc and stop. Do not work around it with a copy-elsewhere hack.

## Repository layout (planned, Phase 4+)

```
excise-mcp-dashboard/
  web/            Laravel 13 + Livewire 4 app (the split-view UI)
  orchestrator/   Python 3.12 FastAPI service (MCP client, engine router)
  etl/            Python ingestion jobs (Sheets / Drive / Excel / CSV -> Postgres)
  db/             SQL: schema, read-only role grants, seed reference data
  deploy/         Apache vhost, cloudflared config, systemd --user units
  docs/           this set of Markdown files
```

Three deployable units (`web`, `orchestrator`, `etl`) in one repo. Keep them in
one repo while the interfaces are still moving; split later only if a second
consumer appears.

## Laravel conventions (`web/`)

Match the sibling apps — `~/Sites/upexcise-stats-dashboard`,
`~/Sites/UP-excise-mailer`, `~/Sites/excise-budget-tracker` — not generic
Laravel tutorials. Those apps are **Laravel 13 / Livewire 4 / PHP 8.5**, not
the 11/12 + Livewire 3 named in the original brief.

- **Livewire-first for interactive screens** (the chat panel, the chart
  canvas, the query ledger). Plain controllers + Blade for anything static or
  purely CRUD, matching `pdf-markdown-pipeline`'s admin area.
- **Full-page Livewire components** for routed pages; link internal navigation
  with `wire:navigate`. Downloads and cross-app links stay plain.
- **Route-model binding on a slug or ULID, never the numeric id.** Query rows
  in the ledger get a ULID (`conversations`, `messages`, `chart_artifacts`).
- **Clean path segments over query strings**, except where a value must be
  bookmarkable (a shared conversation link).
- **`db:provision` is MariaDB-only** (`subhanraj/laravel-db-provisioner`). This
  app's operational store is its own small MariaDB DB
  (`excise_mcp_dashboard_local`, scoped user = db name, never root) for
  sessions, users, the query ledger, and queued jobs. The excise **data bank**
  is separate — PostgreSQL, provisioned by the SQL scripts in `db/`, never by
  `db:provision`.
- **Auth**: Fortify + emailed-OTP login, magic-link onboarding and reset, copied
  from `~/Sites/upexcise-stats-dashboard`'s `App\Http\Controllers\Auth\*`. This
  is an internal tool — every route except the health check is behind auth, and
  behind Cloudflare Access on top.
- **Middleware**: port `SecurityHeaders` (CSP/HSTS/`X-Frame-Options`/noindex)
  and `LogMutation` (`activity_logs` row per non-GET) from the siblings. Add
  the FastAPI origin and any chart CDN to the CSP allowlist explicitly.
- **Rate limiters** in `AppServiceProvider`: `login`, `two-factor`,
  `password-reset` as in the siblings, plus `ask` (the query-submit endpoint)
  keyed by user id — start at 10/min, tune from the ledger.
- **Queues**: `QUEUE_CONNECTION=database`. Long calls to the orchestrator run in
  a job (`RunExciseQuery`), not in the web worker. `--timeout` on the queue
  worker must exceed the orchestrator's own request timeout — follow the
  `--timeout=1900` reasoning in `laravel-apps-deploy.md`.
- **Tailwind + Alpine**: Tailwind Play CDN and Chart.js / Plotly from jsDelivr,
  same as the siblings. Add every CDN host to the CSP.
- **Styling/UX**: split-view is a two-pane flex layout, chat left, canvas
  right, stacking to one column under `lg`. Streaming stage updates
  (`Querying database -> Running analysis -> Rendering chart -> Complete`) come
  over SSE from a Laravel route that polls the job/orchestrator; fall back to
  `wire:poll` if SSE behind the tunnel misbehaves.

## Python conventions (`orchestrator/`, `etl/`)

No FastAPI or Python-service code exists anywhere in `~/Sites` or `~/Projects`
to copy — this is the first. Set the house style here.

- **Python 3.12** (pyenv `3.12.8` is active on the box). One venv per
  deployable: `orchestrator/.venv`, `etl/.venv`. `requirements.txt` with pinned
  versions and a matching `requirements.lock` (`pip-compile` or `uv pip
  compile`). No Poetry/PDM unless a real need appears.
- **PEP 8**, enforced by `ruff` (lint + format — one tool, replaces
  black/isort/flake8). `ruff check` and `ruff format --check` pass before a
  change is done. Line length 100.
- **Type hints on every function signature and dataclass.** `mypy --strict` on
  `orchestrator/app` and `etl/`; a `# type: ignore[code]` needs a reason
  comment.
- **`async def` for all FastAPI route handlers and any I/O** (DB via `asyncpg`,
  outbound HTTP via `httpx.AsyncClient`, Ollama calls). CPU-bound plot
  execution goes through `asyncio.to_thread` or a subprocess, never inline in
  the event loop.
- **Pydantic v2 models** for every request body, response body, tool-call
  argument set, and config block. Tool outputs the LLM must produce are
  Pydantic models exported to JSON Schema and handed to Ollama as the
  `format` / tool schema — the LLM's structured output is validated against
  them on the way back in, and a validation failure is one retry then a clean
  error, never a raw string passed downstream.
- **Config** via `pydantic-settings` from environment / `.env`; no `os.getenv`
  scattered through the code. One `Settings` object, imported once.
- **Logging**: `structlog` to stdout as JSON lines (systemd's journal
  captures it). One request-id per incoming query, threaded through every log
  line and forwarded to Laravel in the response so a ledger row links to its
  logs. No `print`.
- **Errors**: every externally-triggered failure (bad SQL from the LLM,
  sandbox timeout, engine missing, Ollama down) maps to a typed exception and a
  documented HTTP status with a JSON `{error, request_id, stage}` body. The
  web app renders `stage` in the UI.
- **No broad `except Exception: pass`.** Catch what you can handle; let the rest
  surface to the request-id'd handler.

## Docs, comments, commits

Use the `dev-docs-human` skill (`/dev-docs-human`) for every Markdown file,
code comment, and commit message here — same rule as `~/Sites/infra-notes` and
the sibling apps. State what the code does now; do not narrate how it changed
or frame choices as "X, not Y". Public-facing UI copy (empty states, error
text a non-technical user reads) uses `/general-english`.

Commit messages: imperative subject, body explains why when it is not obvious.
End with the co-author trailer the session is configured for.

## Tests required before a commit

**`web/` (PHPUnit, feature-test-first, model factories):**
- Auth: login, wrong password, wrong/expired OTP, the auth gate, onboarding
  link, password reset — port the sibling `tests/Feature/Auth/*`.
- `ask` flow: a submitted question creates a `conversations` + `messages` +
  `queries` row set; a mocked orchestrator response renders a chart artifact
  and a ledger entry; an orchestrator error renders the failed stage and still
  writes a ledger row.
- Rate limiting on `ask`.
- `SecurityHeaders` present on a sample route; `activity_logs` written on a
  non-GET.
- The SSE/poll stage endpoint returns the stage sequence for a running job.

**`orchestrator/` (pytest, `pytest-asyncio`):**
- Every tool schema round-trips: model -> JSON Schema -> sample LLM payload ->
  Pydantic validation.
- SQL guard: a generated statement containing anything but a single `SELECT`
  / `WITH ... SELECT` is rejected before it reaches the database; a `SELECT`
  that tries to write (`SELECT ... INTO`, a function with a side effect) is
  caught by the read-only transaction in an integration test against a real
  local Postgres.
- Engine router: an explicit `engine` value picks the right adapter; an
  unknown or unavailable engine returns the typed "engine unavailable" error;
  default is `python`.
- Sandbox: a script that sleeps past the wall-clock cap is killed and reported;
  a script that opens a socket fails; a script that writes outside the scratch
  dir fails; a script that allocates past the memory cap is killed.
- Ollama client: a malformed structured output triggers exactly one retry then
  a typed error.

**`etl/` (pytest):**
- Each source adapter (Sheets, Drive, Excel, CSV) parses a fixture file into
  the normalized row shape.
- The loader upserts on each table's natural key — a re-run of the same fixture
  changes no row counts.
- A malformed / short row is quarantined, not inserted, and counted in the run
  summary.

**Cross-cutting:** `ruff`, `ruff format --check`, `mypy --strict` on the Python
trees; `vendor/bin/pint --dirty` on `web/`. All green before commit.

## Negative constraints, restated for grep

- NO DeepSeek.
- NO raw / unsandboxed execution of generated code.
- NO root DB access, NO write DB access, for the AI/orchestrator path.
- NO new dependency where an installed one or a few lines of stdlib do the job.
- NO speculative abstraction — one engine implemented until a second is
  actually needed (`EVALUATION.md` §Right-sizing).
- NO committing `.env`, service-account JSON, `cert.pem`, tunnel credentials.
- NO `composer create-project` / venv / installs before Phase 4 approval.
