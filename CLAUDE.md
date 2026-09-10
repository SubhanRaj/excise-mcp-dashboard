# CLAUDE.md — excise-mcp-dashboard

Master rules for coding sessions on this repo. Read this, then `ARCHITECTURE.md`,
`EVALUATION.md`, and the doc for whichever component you are touching
(`DATA_PIPELINE.md`, `MCP_ENGINES.md`, `SECURITY.md`). `ROADMAP.md` has the
milestone checklist and the current position in it.

Status: **Phase 4 approved; build underway.** Milestone 0 (groundwork) and the
database half of Milestone 1 are done — the `web/` Laravel skeleton is in
review (PR #1), the on-box infra is provisioned, and `db/` holds the
PostgreSQL data bank (schema, `analytics.*` views, roles, reference seed). Work
follows the `ROADMAP.md` milestone order. Still no dependency install —
`composer create-project`, a venv, `pip`/`npm` add — outside what the current
milestone's `OPERATOR_SETUP.md` section sanctions.

## What this project is

An on-premise conversational analytics tool for UP Excise departmental figures
(revenue, dispatches, shop quotas, enforcement). A user asks a question in
plain language; a local LLM turns it into a read-only SQL query against a
PostgreSQL copy of the excise data, runs a short analysis/plot script, and the
web UI shows the chart, the table, and the generated SQL.

Two more capabilities sit on the same LLM and UI:

- **A knowledge base.** The model can pull up UP Excise acts, rules,
  regulations, and policies — the verified Markdown already published in
  `~/Sites/pdf-markdown-pipeline` (`docsrepo.exciseup.in`, public + verified
  documents only) — and admins can upload further `.md` files (rule notes,
  circulars). Questions that are about the law rather than the numbers are
  answered from this corpus; questions that need both get both. See
  `DATA_PIPELINE.md` §Knowledge base and `MCP_ENGINES.md` §Chat and retrieval.
- **A general chat window**, OpenWebUI-style: streaming conversation with the
  local model, conversation history, markdown/code rendering. The model calls
  tools from inside the chat — `search_knowledge`, `run_sql_query`,
  `make_chart` — so the same data-lake and knowledge access is available
  conversationally, not only through the one-shot analytical form. Built
  natively in Livewire against the orchestrator's streaming endpoint; no
  Docker, no embedded OpenWebUI (`EVALUATION.md` §Chat integration).

It sits alongside the four existing departmental Laravel apps on the office AIO
(`~/Sites/infra-notes/laravel-apps-deploy.md`) and follows their deployment
pattern: Apache vhost on a private port, one named Cloudflare Tunnel, systemd
`--user` units for workers.

## Hard constraints (do not violate)

- **No DeepSeek models.** Any family, any quant, any purpose. The model is
  chosen in `EVALUATION.md` from Llama 3.1, Qwen 2.5, or Gemma 2 only. The
  embedding model is also local (Ollama), also not DeepSeek.
- **No unsandboxed code execution.** Every LLM-generated script (Python,
  Octave, anything) runs under the sandbox in `SECURITY.md` — non-root user,
  `bwrap` namespace, no network, writable path limited to one scratch dir,
  wall-clock and memory caps. A script never runs directly on the host.
- **No root or write access to Postgres for the AI path.** The orchestrator
  connects as a dedicated `LOGIN` role with `SELECT` only and
  `default_transaction_read_only = on`. `INSERT`/`UPDATE`/`DELETE`/`DDL` are
  refused by the database engine, not by a string filter in application code.
  This holds whether the SQL comes from the one-shot form or from a tool call
  inside the chat — same read-only role, same guard, same sandbox.
- **The knowledge base is read-only to the AI path too.** `kb.*` is granted
  `SELECT` to the read-only role. Ingestion (pdf-markdown-pipeline sync,
  admin `.md` uploads) writes through the ETL role only. The model retrieves
  from `kb.*`; it never writes to it.
- **No document or query leaves the box.** Retrieval, embedding, inference,
  and plotting are all local. The only outbound network is the Cloudflare
  Tunnel (serving the UI) and, when a user has connected Google, the Google
  Drive/Sheets/Docs API for ingestion — nothing else.
- **Google OAuth tokens are encrypted at rest and never logged.** Refresh
  tokens are stored `Crypt`-encrypted per user; access tokens are short-lived
  and in-memory. A disconnect deletes the stored token. See `SECURITY.md`
  §Google OAuth.
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

## Repository layout

`web/` and `db/` exist; `orchestrator/`, `etl/`, `deploy/`, and
`OPERATOR_SETUP.md`'s later sections arrive with their milestones.

```
excise-mcp-dashboard/
  web/            Laravel 13 + Livewire 4 app (analytical form + chat window + admin)
  orchestrator/   Python 3.12 FastAPI service (MCP client, tool loop, engine router,
                  SQL + knowledge retrieval + streaming chat)
  etl/            Python ingestion jobs:
                    - Sheets / Drive / Docs / Excel / CSV -> Postgres data tables
                    - pdf-markdown-pipeline verified docs + admin .md uploads -> kb.*
  db/             SQL: schema (data + kb), read-only role grants, seed reference data
  deploy/         Apache vhost, cloudflared config, systemd --user units + timers
  docs/           this set of Markdown files
  OPERATOR_SETUP.md   every sudo / install / Google-console step, copy-pasteable
```

Three deployable units (`web`, `orchestrator`, `etl`) in one repo. Keep them in
one repo while the interfaces are still moving; split later only if a second
consumer appears.

## Decisions (why the build looks like this)

- **Chat window: native Livewire.** OpenWebUI is a separate Svelte app with
  its own database and needs Docker (absent). What is wanted is its UX —
  streaming, history, markdown/code rendering, a model picker — which Livewire
  + Alpine + an SSE stream from the orchestrator cover. All LLM logic (chat
  loop, tool calls, retrieval, SQL) stays in the Python orchestrator; `web/`
  renders and streams. If the LLM logic ever moves to PHP, `prism-php/prism`
  is the package to use, replacing the Python orchestrator rather than running
  beside it. Running OpenWebUI itself in Docker against the orchestrator's
  OpenAI-compatible endpoint stays a documented backlog option.
- **Retrieval: Postgres full-text search first, `pgvector` as the documented
  upgrade.** The policy/acts corpus is small (a few hundred verified docs).
  Built-in `tsvector` + `websearch_to_tsquery` needs no extension and no
  embedding model. Add `pgvector` + a local embedding model only if FTS recall
  proves weak on real questions — the `kb.chunks` table carries a nullable
  `embedding` column from day one so the switch is additive. `EVALUATION.md`
  §Retrieval.
- **Google access: OAuth (user-delegated) alongside the service account.** The
  service account covers server-owned sheets. OAuth via `laravel/socialite`
  lets an analyst connect their own Drive / Sheets / Docs. Both feed the same
  ETL adapters. `DATA_PIPELINE.md` §Google sources, `SECURITY.md` §Google OAuth.
- **Knowledge base lives in the Postgres data bank (`kb` schema), not in
  `web/`'s MariaDB.** The orchestrator already has a read-only Postgres
  connection; retrieval is one more `SELECT`. Keeps all model-facing data in
  one place behind one read-only role.
- **Multiple models, one orchestrator, no agent framework.** The build already
  runs more than one local model: `qwen2.5-coder:7b` plans and writes SQL and
  plot scripts, `llama3.1:8b` converses and summarises, and the
  `config/models.php` registry lets an admin add Gemma or another allowed tag
  and pick it per request. That is the multi-model need met — a config
  registry, a per-task default, and a validated picker. A multi-agent
  framework (CrewAI, AutoGen, Semantic Kernel, LangGraph) is declined: it adds
  a heavy dependency with default outbound telemetry against the no-egress
  rule, assumes cheap parallel API fan-out that one local Ollama with
  `OLLAMA_MAX_LOADED_MODELS=1` cannot give, and replaces a bounded, logged
  tool loop with an unbounded delegation graph over the same guard and sandbox
  surface. If a decompose-run-synthesise "research" mode is ever needed, it is
  a sequential loop inside the existing orchestrator with a step cap, reusing
  the one Ollama client and the existing tools. `EVALUATION.md` §Right-sizing
  item 13, `MCP_ENGINES.md` §Structured-output loop.

## Laravel conventions (`web/`)

Match the sibling apps — `~/Sites/upexcise-stats-dashboard`,
`~/Sites/UP-excise-mailer`, `~/Sites/excise-budget-tracker` — not generic
Laravel tutorials. Those apps are **Laravel 13 / Livewire 4 / PHP 8.5**, not
the 11/12 + Livewire 3 named in the original brief.

- **Livewire for every screen**, CRUD and admin included — the sibling apps
  (`upexcise-stats-dashboard`, `UP-excise-mailer`, `excise-budget-tracker`) are
  built on Livewire end to end. Full-page Livewire components back every routed
  page, and internal navigation goes through `wire:navigate` so moving between
  pages is an AJAX swap with no full reload.
- **Plain controllers** stay for the routes with nothing to render as a live
  component: the `/health` check, the Fortify email-OTP auth flow (ported from
  `upexcise-stats-dashboard`), file and report downloads, the Google OAuth
  redirect and callback, and cross-app links.
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
  from `~/Sites/upexcise-stats-dashboard`'s `App\Http\Controllers\Auth\*`. The
  site is served on a subdomain of `exciseup.in` through a named Cloudflare
  Tunnel, the same as the sibling apps — no Cloudflare Access. The app's own
  email-OTP login is the access gate: every route except the health check is
  behind `auth`, an unauthenticated request lands on `/login`.
- **Middleware**: port `SecurityHeaders` (CSP/HSTS/`X-Frame-Options`/noindex)
  and `LogMutation` (`activity_logs` row per non-GET) from the siblings. Add
  the FastAPI origin and every CDN this app uses to the CSP allowlist
  explicitly — Chart.js / Plotly, `marked` + highlighter, `cleave.js`, `dexie`,
  all from jsDelivr.
- **Data stores**: MariaDB (`excise_mcp_dashboard_local`, `db:provision`) is
  the operational store — sessions, users, `activity_logs`, the query ledger,
  chat history, `saved_analyses` / `analysis_runs` / `reports`, `kb_uploads`,
  `google_connections`, the `database`-driver queue. PostgreSQL is the data
  bank only. `web/` never connects to Postgres directly; the orchestrator does,
  read-only.
- **Audit**: every state change and AI action is recorded — `activity_logs`
  (auth events + every non-GET), the `queries` / `analysis_runs` ledger with
  `request_id`, export events, Google connect/disconnect, kb upload/withdraw,
  `etl.ingestion_runs`. Tokens, passwords, and full row sets are never logged.
  `SECURITY.md` §5.
- **Formatting**: store UTC; render every user-facing time in IST
  (`Asia/Kolkata`) via `Carbon::macro('ist')` ported from
  `~/Sites/upexcise-stats-dashboard`. Money shows `₹` with `en-IN` grouping and
  a rupees / thousands / lakh / crore switcher; counts render plain, no
  decimals. Money inputs reuse the sibling Cleave.js `currency-input`
  component (`excise-budget-tracker`).
- **Rate limiters** in `AppServiceProvider`: `login`, `two-factor`,
  `password-reset` as in the siblings, plus `ask` (the one-shot query endpoint)
  and `chat` (per message) keyed by user id — start at 10/min, tune from the
  ledger.
- **Chat UI**: a full-page Livewire `Chat` component. Conversation list in a
  left rail, the active thread in the main pane, an Alpine-driven SSE reader
  appending assistant token deltas. Markdown + fenced code render client-side
  (`marked` + a highlighter from jsDelivr, on the CSP allowlist). Tool calls
  the model makes (`run_sql_query`, `search_knowledge`, `make_chart`) render
  as inline cards — the SQL, the retrieved snippets with links to
  `docsrepo.exciseup.in`, the chart. History persists in `conversations` /
  `messages` / `message_tool_calls`. No streaming LLM logic in PHP — `web/`
  reads the orchestrator's `/chat` SSE and relays it.
- **Model picker**: a `config/models.php` registry (`key`, `label`, `role`,
  Ollama tag), mirroring `~/Sites/pdf-markdown-pipeline`'s `config/ocr.php` and
  its "Run OCR" dropdown. The chat composer shows a dropdown of the registry
  entries the orchestrator `/health` reports as pulled; the choice is sent as
  `model` on the `/chat` call and re-validated there. The one-shot form carries
  the same override in an advanced control next to `engine`. Default follows
  the task (coder model for SQL/plot, chat model for conversation); a
  mid-conversation switch costs a model reload
  (`OLLAMA_MAX_LOADED_MODELS=1`) and the UI says so. `EVALUATION.md` §2.
- **Google connect**: `laravel/socialite` + the Google provider with the
  Drive/Sheets/Docs read-only scopes and `access_type=offline` +
  `prompt=consent` for a refresh token. A `google_connections` row per user,
  refresh token `Crypt`-encrypted. An admin "Connected sources" screen lists
  Drive folders / Sheets / Docs to register as ETL sources. `SECURITY.md`
  §Google OAuth.
- **Knowledge**: an admin "Knowledge base" screen — upload `.md` files
  (validated: extension, `<= 2 MB`, filename sanitised, no path segments),
  browse the ingested corpus (pipeline docs + uploads), withdraw an upload.
  Uploads land on a dedicated disk the ETL reads; the screen does not write
  `kb.*` directly.
- **Queues**: `QUEUE_CONNECTION=database` on MariaDB, like the siblings. Long
  calls to the orchestrator run in a job (`RunExciseQuery`, `RefreshAnalysis`,
  report exports), not in the web worker. `--timeout` on the queue worker must
  exceed the orchestrator's own request timeout — follow the `--timeout=1900`
  reasoning in `laravel-apps-deploy.md`. Redis is the documented upgrade if the
  `jobs` table shows contention (`EVALUATION.md` §Right-sizing 10); Kafka /
  Temporal / Airflow are out of scope.
- **Offline (Milestone 7)**: no offline generation — the ask -> SQL -> sandbox
  path needs the server. A Dexie (IndexedDB) read cache keyed on `etl_epoch`,
  ported from the sibling shops-table pattern, holds the conversation list,
  recent messages, and an opened saved analysis / report for offline reading,
  with a "last synced" marker; a question typed offline queues and sends on
  reconnect.
- **Output store**: the data bank (Postgres) is raw data only; charts, tables,
  summaries, and the generated SQL are app artifacts, never written back to
  Postgres. Small and structured -> MariaDB: the chart spec (Plotly JSON in a
  `chart_artifacts.spec` column), `rows_preview`, the SQL, the summary, every
  `saved_analyses` / `reports` row. Large blobs -> the `local` disk: the
  rendered PNG / SVG / PDF and the report exports, with a pointer row. A run's
  files sweep after `ARTIFACT_TTL_DAYS` unless a `saved_analyses` row pins it. A saved analysis
  carries a `recipe` to re-run; each refresh (manual / scheduled / ETL-fired)
  adds an `analysis_runs` row — that history is the trend, shown with the
  sibling `Sparkline`. `reports` order saved analyses + Markdown blocks into a
  presentation. Export a chart (PNG/SVG/PDF/`plotly.json`), a result
  (CSV/XLSX via the sibling `ExportService`), or a report (dompdf PDF / XLSX /
  ZIP bundle, stamped with the ETL vintage). `DATA_PIPELINE.md` §Output store.
- **Tailwind + Alpine**: Tailwind Play CDN and Chart.js / Plotly from jsDelivr,
  same as the siblings. Add every CDN host to the CSP. Chart.js line colours
  follow `design-guidelines.md` §Charts (single series `#4a2bc2`, multi-series
  `#4a2bc2, #c47d00, #0f766e, #b91c1c, #1d4ed8, #7c3aed`).
- **Design system**: follow
  `~/Sites/upexcise-stats-dashboard/docs/design-guidelines.md` — the UX4G
  `govviolet` (`#4a2bc2`) / `govsaffron` palette, Inter, the `@apply` component
  classes and anti-flash theme script from its `head.blade.php`, and the
  Tabler-icon admin shell (`components/layout.blade.php` + `sidebar.blade.php`).
  This is an internal tool: keep the GIGW accessibility baseline (skip link,
  landmarks, one `h1`, `:focus-visible` outline, explicit empty states); leave
  out the sitemap / SEO / JSON-LD surface and the policy-page footer.
- **Customization panel**: a floating control (FAB) that opens a Display panel,
  combining the sibling's reader prefs with `~/Projects/chinese-intel-pipeline`'s
  `CustomizationPanel.tsx` set — theme (system / light / dark), font family
  (small curated catalogue, Inter default, loaded on demand from Google Fonts),
  text size, line spacing, content width, table density (comfortable / compact),
  accent colour (govviolet default + a sanctioned few), high contrast, and a
  "reduce motion" / streaming toggle for the chat. Applied via `data-*`
  attributes + one CSS var, `localStorage` + a cookie for the anti-flash script,
  and mirrored to `users.ui_prefs` (JSON) so it follows the login. A Reset
  button. `EVALUATION.md` §4.
- **Livewire write authorization**: route middleware gates a component's
  mount, but a `wire:click` / `wire:submit` that reaches `livewire/update`
  does not re-run route middleware. Every write method on an admin component
  (knowledge upload, Google connect/disconnect, user CRUD, source-registry
  edits) re-checks the privilege with `abort_unless(...)`, matching the sibling
  dashboard's publish and milestone gates. `SECURITY.md` §3.
- **Branding and chrome**: the brand kit is in `assets/brand/` — the State
  Emblem of Uttar Pradesh (`up-gov-emblem.svg` + the white PNG), the favicons,
  and the app icons. Move it into `web/public/` at Milestone 5. Port the GIGW
  / UX4G chrome from `~/Sites/upexcise-stats-dashboard`'s public layout: the
  "Government of Uttar Pradesh" identity strip, the A- / A / A+ text-size and
  high-contrast toggles (cookie-persisted, no library), the skip-to-main link,
  and the footer policy links. Regenerate the icons and the Open Graph card
  with that repo's `scripts/make-brand-assets.php`. The Department of Excise
  mark renders beside the emblem when
  `web/public/assets/img/excise-logo.{svg,png,webp}` is present.
  `EVALUATION.md` §4.
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
- **Streaming** (`/chat`): FastAPI `StreamingResponse` yielding SSE events
  (`token`, `tool_call`, `tool_result`, `done`, `error`). Generation is
  cancellable — a client disconnect aborts the Ollama call and any in-flight
  tool.
- **Tool loop**: the chat agent loop lives in `orchestrator/app/chat/`. Tools
  are the same primitives the one-shot pipeline uses (`sql/`, `kb/`,
  `engines/`) — no parallel implementation. Hard cap on tool calls per turn
  (default 4); exceeding it ends the turn with a typed error.
- **Retrieval** (`orchestrator/app/kb/`): FTS query builder over `kb.chunks`
  by default; a `pgvector` code path guarded by `KB_EMBEDDINGS_ENABLED`,
  embeddings via the local Ollama embed model. Retrieval never calls out of
  the box.
- **Embeddings** (when enabled): one pinned Ollama embed model
  (`nomic-embed-text` or `bge-m3`), batched, run in `etl/` at ingestion time
  and in the orchestrator at query time. Dimensions pinned in config and in
  the `kb.chunks.embedding` column type.
- **Google API** (`etl/`): `google-api-python-client` + `google-auth`.
  Auth mode per source — `service_account` (key file path from env) or
  `oauth` (client id/secret + a per-connection refresh token read from the
  operational DB). `google-auth` handles access-token refresh; a
  refresh failure raises a typed "reconnect needed" error, never a silent
  skip.

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
- Chat flow: a message streams assistant tokens from a mocked orchestrator;
  a tool call in the stream (`run_sql_query`, `search_knowledge`,
  `make_chart`) is persisted and rendered; conversation history loads and
  resumes.
- Model picker: the dropdown lists only registry models the mocked `/health`
  reports pulled; a chosen model rides on the `/chat` call as `model`; a value
  outside the registry is refused.
- Rate limiting on `ask` and on chat message submit.
- Knowledge upload: a `.md` file uploads, is validated (extension, size, no
  path traversal), lands on the ingestion disk, and creates a pending
  `kb_uploads` row; a non-`.md` or oversize file is rejected.
- Google OAuth: the connect redirect carries the right scopes; the callback
  stores an encrypted token and a `google_connections` row; disconnect
  deletes it; a token is never written to logs or returned in a response.
- `SecurityHeaders` present on a sample route; `activity_logs` written on a
  non-GET; an unauthenticated request to a protected route redirects to
  `/login`.
- Customization panel: a changed preference persists across reload (cookie +
  `users.ui_prefs`) and Reset restores defaults; timestamps render in IST.
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
- Model selection: a `model` in `OLLAMA_ALLOWED_MODELS` is used for that
  request; one outside the set is rejected before any Ollama call; the chat
  picker never changes which model plans `run_sql_query`.
- Retrieval: a question retrieves the expected `kb.chunks` rows by FTS rank;
  an empty corpus returns no context and the answer path says so rather than
  hallucinating; with `pgvector` enabled, vector and FTS results merge and
  de-duplicate.
- Chat tool loop: a chat turn that needs data emits a `run_sql_query` tool
  call routed through the same guard + read-only run + sandbox; a law question
  emits `search_knowledge`; a mixed question emits both; the loop terminates
  at a max tool-call count with a typed error.
- Streaming: `/chat` yields SSE token deltas and tool-call events in order;
  a client disconnect cancels the in-flight generation.

**`etl/` (pytest):**
- Each source adapter (Sheets, Drive, Docs, Excel, CSV) parses a fixture file
  into the normalized row shape.
- The loader upserts on each table's natural key — a re-run of the same fixture
  changes no row counts.
- A malformed / short row is quarantined, not inserted, and counted in the run
  summary.
- Google adapter auth mode: `service_account` and `oauth` both resolve to a
  working client against a mocked API; an expired access token refreshes from
  the stored refresh token; a revoked token surfaces a clear "reconnect
  needed" error.
- Knowledge ingestion: a fixture mirroring `pdf_markdown_pipeline_local.documents`
  (visibility `public`, status `verified`) plus its Markdown file produces
  `kb.documents` + chunked `kb.chunks` rows with correct metadata and source
  URL; a non-public or non-verified row is skipped; a re-run changes no
  counts; a removed upstream doc is marked withdrawn, not deleted.

**Cross-cutting:** `ruff`, `ruff format --check`, `mypy --strict` on the Python
trees; `vendor/bin/pint --dirty` on `web/`. All green before commit.

## Negative constraints, restated for grep

- NO DeepSeek (chat model or embedding model).
- NO raw / unsandboxed execution of generated code, including SQL/plot tool
  calls made from inside the chat.
- NO root DB access, NO write DB access, for the AI/orchestrator path —
  `analytics.*` and `kb.*` are `SELECT`-only to the read-only role.
- NO writes to `kb.*` except through the ETL role (sync + admin uploads).
- NO embedded OpenWebUI, NO Docker for the chat — native Livewire + the
  orchestrator stream (`EVALUATION.md` §Chat integration).
- NO `pgvector` / embedding model until FTS recall is shown insufficient
  (`EVALUATION.md` §Retrieval).
- NO Google OAuth token in a log line, a response body, or the repo.
- NO document, prompt, embedding, or query sent anywhere but the local Ollama
  and (ingestion only) the Google API.
- NO new dependency where an installed one or a few lines of stdlib do the job.
- NO speculative abstraction — one engine implemented until a second is
  actually needed (`EVALUATION.md` §Right-sizing).
- NO multi-agent framework (CrewAI / AutoGen / Semantic Kernel / LangGraph /
  …). The chat loop is a bounded in-orchestrator tool loop (cap 4 calls/turn);
  multi-*model* routing is the config registry + per-task default, not a
  framework (`EVALUATION.md` §Right-sizing item 13, `MCP_ENGINES.md`
  §Structured-output loop).
- NO committing `.env`, service-account JSON, OAuth client secret, `cert.pem`,
  tunnel credentials.
- NO dependency install (`composer create-project`, venv, `pip` / `npm` add)
  outside what the current milestone's `OPERATOR_SETUP.md` section sanctions.
