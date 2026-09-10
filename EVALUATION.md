# EVALUATION.md — hardware audit, model choice, reuse inventory

Phase 1 findings. Everything here is read from the live box (2026-09-10) and
from `~/Sites/infra-notes`, `~/Sites/*`, `~/Projects/*`.

## 1. Hardware and resource audit

`~/Sites/infra-notes` has no single `infra-notes` file — it is a directory of
notes. The machine facts come from that directory plus direct inspection.

### CPU

| | |
|---|---|
| Model | Intel Core i7-13700 (Raptor Lake, non-K) |
| Topology | 16 cores / 24 threads — 8 P-cores (HT) + 8 E-cores |
| Hardware max clock | 5.20 GHz / 5.10 GHz P-cores, 4.10 GHz E-cores (per-core, from `cpu-thermal-and-apache-procfs.md`) |
| Current cap | **3.00 GHz**, all cores — `cpu-thermal-cap.service`, a `oneshot` systemd unit set at boot for fans-only thermal safety in a room with no AC |
| Full-speed override | `sudo cpupower frequency-set -u 5.20GHz` (live, does not survive reboot; the 3.0 GHz floor comes back on every boot) |

The thermal cap matters for planning: unattended/overnight runs execute at
~59% of peak clock. LLM inference and any heavy plot script are roughly half as
fast during capped hours. The box also runs OCR batches (`pdf-markdown-pipeline`)
that already pin cores; this project's compute competes with those.

### Memory

| | |
|---|---|
| RAM | 30 GiB (`MemTotal` 31,544,060 kB) |
| Swap | 8 GiB |
| In use at audit | 18 GiB used, 11–18 GiB available depending on cache reclaim |
| Steady-state resident load | desktop session + Apache serving 4 Laravel apps + MariaDB + Ollama runtime ≈ 13–18 GiB |

**Usable headroom for this project: about 10–12 GiB**, and that has to cover
the Ollama model, its KV cache, the sandboxed plot process, `asyncpg`
connections, and PostgreSQL's own working set (PostgreSQL 18 is installed but
its cluster is currently **down** — starting it and loading the excise data
adds a few hundred MB of shared buffers plus page cache).

### GPU

| | |
|---|---|
| GPU | Intel UHD Graphics 770 (integrated, Raptor Lake-S GT1) |
| Discrete GPU | none |
| CUDA / ROCm | none — `nvidia-smi` absent |

**All Ollama inference is CPU-only** (llama.cpp AVX2 / AVX-512 path on the
i7-13700). This is the single biggest constraint on model choice and on
expected concurrency.

### Disk

937 GB root volume (`/dev/nvme0n1p2`), 711 GB free. Not a constraint. A full
excise data bank is well under 5 GB; model weights are 5–9 GB each.

### Storage of the existing dumps

`~/mentor_portal_db` holds ~30 GB of `pg_dump` output from the legacy UP Excise
DB (per `ubuntu-dev-desktop-provisioning.md` and
`postgres-tailscale-remote-access.md`). That is the raw material an ETL backfill
can draw from in addition to the NITI workbooks.

## 2. Ollama model recommendation

Constraints: no DeepSeek; CPU-only; ~10–12 GiB budget shared with compute;
must produce reliable JSON / tool-call output for MCP; the core generation
tasks are **SQL from a schema** and **short Matplotlib/Plotly scripts**.

### Sizing math (Q4_K_M, llama.cpp, `num_ctx` 8192)

| Model | Weights | + KV @ 8k | Resident | Verdict on this box |
|---|---|---|---|---|
| Qwen 2.5 Coder 7B | ~4.7 GB | ~1.5 GB | ~6–7 GB | **Fits with margin** |
| Llama 3.1 8B | ~4.9 GB | ~1.5 GB | ~6–7 GB | Fits with margin |
| Gemma 2 9B | ~5.8 GB | ~1.6 GB | ~7–8 GB | Fits, tighter |
| Qwen 2.5 Coder 14B | ~9 GB | ~2.5 GB | ~11–12 GB | Too tight — will swap under concurrent Postgres + plot load |
| Qwen 2.5 32B / Llama 3.1 70B | 20–40 GB | — | — | Not possible |

### Recommendation

- **Primary: `qwen2.5-coder:7b-instruct` (Q4_K_M).** Best structured-output and
  code generation per parameter in the sub-8B open-weight field; coder-tuned,
  which is exactly the SQL + plot-script workload; 32k native context (run it
  at 8k to save RAM, raise only if schema + few-shot examples overflow);
  strong function-calling / JSON-mode adherence in Ollama. ~6–7 GB resident
  leaves room for compute.
- **Fallback / generalist: `llama3.1:8b-instruct` (Q4_K_M).** Use for the
  conversational chat turns, the summary of results, and as a second opinion
  if Qwen's SQL is malformed twice. Comparable footprint. Both Qwen and Llama
  3.1 support Ollama tool-calling, which the chat loop needs.
- Keep both pulled; the orchestrator selects per task (SQL/plot -> Qwen,
  chat/narration -> Llama). Neither is DeepSeek-derived.
- **Embedding model (only if `KB_EMBEDDINGS_ENABLED`)**:
  `nomic-embed-text` (768-dim, ~275 MB) or `bge-m3` (1024-dim, ~600 MB,
  better on mixed English/Hindi). Adds its footprint on top of whichever LLM
  is loaded; at ~300–600 MB it fits, but see §Retrieval for why it stays off
  until FTS is shown to be the bottleneck.

### Runtime settings

- `OLLAMA_KEEP_ALIVE=30s` — unload the model between queries so the RAM returns
  to the sandboxed plot process and PostgreSQL. Low concurrency makes the
  reload cost acceptable.
- `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1` — serialize. The box
  cannot run two 7B decodes plus a plot process plus Postgres at once.
- Expect **5–15 tokens/s** decode CPU-only at 3.0 GHz cap, ~10–25 tok/s
  uncapped. A typical query (SQL + a short script + a one-paragraph summary)
  is 15–45 s wall-clock. This is fine for a handful of internal analysts; it
  is not a many-concurrent-user service. The web layer must queue requests,
  not fan them out.
- No GPU flags. Confirm `ollama ps` shows `100% CPU`.

### JSON reliability approach

Do not trust free-form model output. Every tool call and the final answer are
Pydantic v2 models -> JSON Schema -> passed to Ollama as the enforced `format`.
On a parse/validation failure: one retry with the validator error appended to
the prompt, then a typed error to the user. `MCP_ENGINES.md` §Structured output
has the loop.

### RAM budget with the chat scope added

The chat window does not add a resident cost on top of the one-shot pipeline —
it uses the same two models. The only new resident item is the embedding
model, and only if embeddings are turned on:

| Loaded set | Resident | Fits in ~10–12 GiB headroom |
|---|---|---|
| One 7–8B model (swapped per task), `MAX_LOADED_MODELS=1` | ~6–7 GB | yes, with margin |
| + `nomic-embed-text` when embeddings on | ~6.5–7.5 GB | yes |
| Two 7–8B models pinned (`MAX_LOADED_MODELS=2`, no swap) | ~12–13 GB | tight — only if swap latency in chat proves annoying, and accept less room for a concurrent plot + Postgres |

Keep `MAX_LOADED_MODELS=1`. The chat's coder<->chat model swap between a tool
call and the reply costs a reload; at this concurrency that is acceptable.

## 2b. Retrieval: FTS first, `pgvector` as the documented upgrade

The knowledge corpus (pdf-markdown-pipeline verified docs + admin uploads) is
small — a few hundred documents, a few thousand chunks. Two options:

| | Postgres FTS (`tsvector`) | `pgvector` + embeddings |
|---|---|---|
| New dependency | none — built into PG 18 | `postgresql-18-pgvector` (apt, root) + an Ollama embed model |
| RAM cost | zero | ~300–600 MB resident when the embed model is loaded |
| Ingestion cost | negligible (generated column) | embed every chunk (CPU, ~seconds per doc) |
| Query cost | one GIN index scan | embed the query + HNSW scan |
| Recall on legal text | good for keyword / citation lookups ("section 12", "MGQ", a rule number); weaker on paraphrase | better on "what does the policy say about minimum quotas" style paraphrase |
| Bilingual (English/Hindi) | `'simple'` config, no stemming — works for both, exact-ish | depends on the embed model; `bge-m3` is multilingual, `nomic-embed-text` is English-first |

**Recommendation: ship FTS.** `kb.chunks` carries a nullable `embedding`
column from the first migration, so enabling `pgvector` later is: install the
extension, `ALTER COLUMN ... TYPE vector(N)`, backfill embeddings in an `etl`
run, flip `KB_EMBEDDINGS_ENABLED`. No schema rework. Turn it on only if real
questions show FTS missing relevant sections — measure against the
representative question set in `ROADMAP.md` Milestone 6.

## 2c. Chat integration: native Livewire

The ask is an OpenWebUI-style chat window. Options weighed:

| Approach | What it costs | Verdict |
|---|---|---|
| **Embed OpenWebUI** (Docker) behind a second subdomain, point its OpenAI endpoint at the orchestrator | `apt install docker` (absent), a second web app with its own SQLite/Postgres and its own auth/users to reconcile with the app login, a second tunnel, container updates | Rejected — a whole parallel app and Docker for a UI we can build |
| **Native Livewire chat** against the orchestrator's `/chat` SSE stream | one more Livewire component + an Alpine SSE reader + `marked`/highlighter from the CDN already on the CSP | **Chosen** — reuses the auth, the layout system, the ledger, the deploy path |
| **Move LLM logic into PHP** with `prism-php/prism` (Ollama support, streaming, tool calls) | a capable package, but it duplicates the orchestrator's tool loop in a second language and splits the "who talks to Ollama" responsibility | Not now — noted as the path if the orchestrator is ever dropped |

The orchestrator already is the MCP client and owns the SQL guard, the
sandbox, and retrieval. Keeping the chat loop there means one implementation
of each tool. `web/` renders and streams.

If OpenWebUI itself is wanted later (its model management, its prompt
library), the integration is documented as a backlog item: run it in Docker,
add it as a second Access-protected subdomain, and point its "OpenAI API"
base URL at an OpenAI-compatible shim on the orchestrator (`/v1/chat/completions`
wrapping the same tool loop). Not on the critical path.

## 3. Tooling and protocol verification

### Present on the box

| Tool | Version | Notes |
|---|---|---|
| PostgreSQL | 18.6 (client + server) | cluster `18/main` on 5432, **status: down** — start before Milestone 1 |
| Python | 3.12.8 (pyenv, `system` also available) | |
| PHP | 8.5.4 | |
| Composer | 2.9.5 | |
| Node | 24.20.0 | |
| cloudflared | 2026.7.1 | already running 4 named tunnels |
| git | 2.53.0 | `user.name` Subhan Raj, gh credential helper configured |
| Ollama | installed, listening on `127.0.0.1:11434` | **no models pulled** (`ollama list` empty) |
| bubblewrap (`bwrap`) | 0.11.1 | the sandbox primitive — see `SECURITY.md` |

### Absent (needed only for optional/proprietary engines)

`octave` / `octave-cli`, `wolframscript` / Wolfram Engine, `matlab`, `firejail`,
Go toolchain, Docker / Podman, `nvidia-smi`.

`firejail` is not installed and needs `apt` (root). `bwrap` **is** installed and
covers the same need — `SECURITY.md` specifies the sandbox on `bwrap`, not
firejail, so no install is required for the core sandbox.

### MATLAB MCP server (`github.com/matlab/matlab-mcp-server`)

- **Go binary**, prebuilt releases for Linux / macOS / Windows, or build from
  source with the Go toolchain (absent here).
- Requires **MATLAB R2021a or later installed and on `PATH`**, plus a **valid
  MATLAB license**. The repo's license terms state an MCP server "must not be
  shared by multiple users" — directly at odds with putting it behind a
  multi-user dashboard.
- Transport is **stdio MCP**, not a network daemon. The `--matlab-session-mode`
  flag (`new` / `auto` / `existing`) controls whether it spawns a fresh MATLAB,
  attaches to a shared one (`shareMATLABSession()` in MATLAB, after
  `./matlab-mcp-server --setup-matlab`), or only attaches. It drives a MATLAB
  process; it is not a headless compute microservice.
- **Verdict: not available and not appropriate on this box now.** No MATLAB
  install, no license, no Go toolchain, and the single-user license term
  conflicts with the deployment. Deferred in `ROADMAP.md` behind a config flag;
  do not build against it in early milestones.

### PostgreSQL MCP server

- The original `@modelcontextprotocol/server-postgres` reference implementation
  is **archived**. It offered transaction-level read-only enforcement and
  schema introspection over stdio.
- The maintained option is **`crystaldba/postgres-mcp`** ("Postgres MCP Pro"):
  `--access-mode=restricted` gives read-only + safety limits, plus `EXPLAIN`
  / index-advisor tools. Runs over stdio or SSE.
- Standard config in either case: a **dedicated read-only role** as the
  connection identity (`SELECT` only, `default_transaction_read_only = on`),
  connection string in the server's own env, never the app's.
- **Recommendation (see §Right-sizing below): skip the MCP server between our
  orchestrator and our own database.** MCP earns its place when an external
  client (Claude Desktop, an IDE) needs the tool. Here the orchestrator is the
  only consumer, in-process, in the same repo. Give it a direct `asyncpg` pool
  bound to the read-only role with a `SET default_transaction_read_only = on`
  and a statement timeout. Keep the door open to mounting `crystaldba/postgres-mcp`
  later if a second consumer appears — the query-building code should not care
  which it is.

### Cloudflare

- `~/.cloudflared/cert.pem` is scoped to the **`exciseup.in`** zone only.
  `upexcise.in` is not on this account (documented failure in
  `laravel-apps-deploy.md`). Use `analytics.exciseup.in` or
  `excise-mcp.exciseup.in`.
- Tunnel pattern is established: one named tunnel per app, per-app config file
  in `~/.cloudflared/`, `credentials-file` pointing at the UUID JSON, one
  ingress rule to `http://127.0.0.1:PORT`, `http_status:404` catch-all, a
  systemd `--user` unit to run it. `SECURITY.md` §Perimeter has this project's
  values.
- Perimeter matches the four existing apps: a named tunnel to a private Apache
  port and the app's own Fortify email-OTP login as the gate. No Cloudflare
  Access / Zero Trust.

### Google OAuth (for the Drive / Sheets / Docs connect feature)

- `laravel/socialite` is the package; not currently used in any sibling.
- `drive.readonly` is a **restricted** scope. A **Internal** consent screen
  (department Google Workspace) avoids Google's verification / CASA
  assessment; an **External** screen hits that process past 100 users. Decide
  this before Milestone 1 — `OPERATOR_SETUP.md` §Google Cloud. Fallback:
  `drive.file` (user-picked files only) is not restricted.
- Redirect URI `https://analytics.exciseup.in/google/callback` (hostname not
  final) — only resolves through the tunnel, and the route is behind the app
  login.
- Refresh tokens are `Crypt`-encrypted per user in `web/`'s MariaDB, never
  logged, revoked on disconnect. `SECURITY.md` §Google OAuth.

### Ports

In use: 8080 `pdf-markdown-pipeline`, 8081 `excise-budget-tracker`, 8082
`UP-excise-mailer`, 8083 `upexcise-stats-dashboard`.

Assigned here: **8084** Laravel (Apache vhost, tunnel target), **8085**
FastAPI orchestrator (bind `127.0.0.1` only, never tunneled). Ollama stays on
11434 loopback. `db:provision`'d MariaDB on 3306, the excise Postgres on 5432.

## 4. Reusable module inventory

### Directly reusable — Laravel (`web/`)

From `~/Sites/upexcise-stats-dashboard`, `~/Sites/UP-excise-mailer`,
`~/Sites/excise-budget-tracker` (all Laravel 13 / Livewire 4 / PHP 8.5):

| Piece | Source | Use here |
|---|---|---|
| OTP-login + magic-link onboarding/reset auth | `upexcise-stats-dashboard/app/Http/Controllers/Auth/*`, `app/Mail/*`, Fortify wiring in `FortifyServiceProvider` | Port near-verbatim — internal-tool auth |
| `SecurityHeaders` middleware (CSP, HSTS, `X-Frame-Options`, `X-Robots-Tag` noindex prefixes) | same, `app/Http/Middleware/SecurityHeaders.php` | Port; extend CSP with the FastAPI origin + Plotly/Chart.js CDN |
| `LogMutation` middleware + `activity_logs` + `ActivityLog::record()` | same | Port as-is — audit every non-GET |
| RBAC: flat `role` + `privileges` JSON + `designations` preset table | same, `app/Models/{User,Designation}.php` | Trim to `Admin` / `Analyst`; this tool has fewer surfaces |
| Rate-limiter definitions | `upexcise-stats-dashboard/app/Providers/AppServiceProvider.php` | Port `login`/`two-factor`/`password-reset`; add `ask` |
| Export service (CSV / XLSX / PDF via `openspout` + `laravel-dompdf`) | `upexcise-stats-dashboard/app/Services/ExportService.php` | Reuse for the "export this result" button — same three formats the brief asks for |
| Server-rendered SVG sparkline, no chart lib | `upexcise-stats-dashboard/app/Support/Sparkline.php` | Reuse for ledger-row mini previews |
| Brand assets + GIGW/UX4G chrome — State Emblem of Uttar Pradesh, favicons, app icons, `scripts/make-brand-assets.php` generator, OG card, the "Government of Uttar Pradesh" identity strip, A-/A/A+ text-size and high-contrast toggles, skip-to-content link, footer policy links | `assets/brand/` in this repo (emblem SVG + white PNG, favicons, app icons); the chrome, `scripts/make-brand-assets.php` and `og-default.png` from `~/Sites/upexcise-stats-dashboard`'s public layout | Move `assets/brand/*` into `web/public/` at Milestone 5; port the identity strip, the theme + high-contrast toggle and the skip link into the authed layout; regenerate the icons and `og-default.png` with the sibling's generator. Internal tool — drop the public reader-preferences panel, the policy-page footer, the sitemap / SEO / JSON-LD surface |
| Design system + tokens | `~/Sites/upexcise-stats-dashboard/docs/design-guidelines.md`; `resources/views/components/head.blade.php` (Tailwind config, UX4G `govviolet` `#4a2bc2` / `govsaffron` ramps, `@apply` classes `.stat-card` / `.badge` / `.field-*`, anti-flash theme script) | Follow the doc; copy the token block and the `@apply` classes into `web/`'s head partial |
| Admin shell | `resources/views/components/{layout,sidebar}.blade.php`, self-hosted Tabler Icons at `public/vendor/tabler-icons/` | The base layout for every authed screen (collapsible sidebar, header, dark toggle, account menu). The `Ask` split-view and the `Chat` panes mount inside it |
| Chart.js conventions | `docs/design-guidelines.md` §Charts; `app/Livewire/Public/*` | Single series `#4a2bc2` + `rgba(74,43,194,0.08)` fill; multi-series palette `#4a2bc2, #c47d00, #0f766e, #b91c1c, #1d4ed8, #7c3aed`; `maintainAspectRatio: false` in a fixed-height wrapper, bottom legend, `y.beginAtZero`. For the ledger sparklines and any non-Plotly chart |
| Export controllers + dompdf table view | `app/Http/Controllers/Public/{ExportController,TableExportController}.php`, `resources/views/exports/table.blade.php` (DejaVu Sans covers `₹` + Devanagari) | The `/…/export/{format}` route shape and the PDF view behind the "export this result" button, alongside the already-listed `ExportService` |
| Livewire write-authorization pattern | `upexcise-stats-dashboard/app/Livewire/Admin/{PublishToggles,Milestones}.php` | Route middleware gates the mount; every write method re-checks the privilege with `abort_unless()` because `livewire/update` does not re-run route middleware (`SECURITY.md` §3) |
| Deploy runbook shape (Apache vhost + tunnel + systemd `--user`, `view:clear` after pull, ProtectHome `ReadWritePaths` gotcha) | `upexcise-stats-dashboard/DEPLOY.md`, `infra-notes/laravel-apps-deploy.md` | `deploy/` follows this exactly |
| `db:provision` scoped-user convention (`<app>_local`, db name = user, never root) | `subhanraj/laravel-db-provisioner` in every sibling | Use for the MariaDB operational store |
| `laravel/socialite` | not yet used in any sibling — new dependency, but the standard Laravel OAuth package | The Google connect flow (`SECURITY.md` §Google OAuth). One package, not a hand-rolled OAuth client |

### Directly reusable — data

| Piece | Source | Use here |
|---|---|---|
| **Complete excise relational schema** — `zones -> divisions -> districts`, `financial_years`, fact tables `revenues` / `sales_volumes` / `operations`, `shops` + `shop_years`, `brands` / `brand_prices` / `duty_rates` / `policy_entries`, natural keys, `Publishable` pattern | `~/Sites/upexcise-stats-dashboard` `docs/data-model.md` + migrations | **Translate this to PostgreSQL as the data bank.** It is already imported, verified (75 districts, 900 rows/series, ~79.7k shops / 242k shop-years, 3.5k brands), and bug-fixed. Do not design a new schema. `DATA_PIPELINE.md` §Schema. |
| NITI workbook importer (`excise:import`, `openspout`, idempotent upsert on natural key, note-row quarantine) | `upexcise-stats-dashboard/app/Console/Commands/ImportExciseData.php` | The Excel-source branch of the ETL is this logic, moved to Python `etl/` |
| Zone/division/district seed (from the mailer's contact-list JSON) | `upexcise-stats-dashboard` seeders | Seed the Postgres dimension tables |
| **Verified policy / acts / rules corpus** — `documents` table (`visibility`, `status='verified'`, `document_type`, `language`, `rule_set` / `section` / `department`) + Markdown on the `public` disk (`storage/app/public/<markdown_path>`) | `~/Sites/pdf-markdown-pipeline` (`docsrepo.exciseup.in`), DB `pdf_markdown_pipeline_local` | The primary knowledge-base feed. Read-only sync in `etl/sources/pdf_pipeline.py` — MariaDB (scoped read-only user) + filesystem. `DATA_PIPELINE.md` §Knowledge base. |
| Government document taxonomy (Level -> Body -> Section, Acts & Rules, named policies with year-over-year supersession) | `~/Sites/pdf-markdown-pipeline` `claude.md` | Maps onto `kb.documents.doc_type` / `rule_set` / `effective_from` / `effective_to` |
| Legacy `pg_dump` set (~30 GB) | `~/mentor_portal_db` | Optional historical backfill source, already PostgreSQL-native |
| Local analysis-DB + scoped-user pattern (prod is Cloudflare D1, local clone for offline analysis) | `~/Projects/up-excise-spatial-revenue-optimizer`, `infra-notes/up-excise-local-analysis-db.md` | Same shape as what this project is — a local read-only analytical copy |

### Reference only — not code to copy

| Piece | Source | Value |
|---|---|---|
| Subprocess-call security review (OCR/convert jobs, temp-dir handling, `javascript:` URI stripping) | `~/Sites/pdf-markdown-pipeline/SECURITY.md` | The house standard for "we shell out to a tool safely" — `SECURITY.md` here follows its rigor |
| Cloudflare Workers + D1 + separate scraper worker split | `~/Projects/chinese-intel-pipeline` | Pattern reference for a two-service repo; not this stack |
| Tailscale-scoped Postgres remote access, per-node share, per-user read-only role | `infra-notes/postgres-tailscale-remote-access.md` | The read-only-role SQL there is the starting point for `db/` grants |

### Not found — must be built fresh

- **No FastAPI / uvicorn / Python microservice anywhere** in `~/Sites` or
  `~/Projects`. No `requirements.txt`, no `pyproject.toml` (one stray `.venv`
  in `up-finance-handbook`, unrelated). The orchestrator has no local
  precedent — `CLAUDE.md` §Python conventions sets the style from zero.
- No MCP client code, no Ollama integration code, no code-execution sandbox
  anywhere on the box.
- **No retrieval / RAG / embedding / vector-search code anywhere.** `pgvector`
  is not confirmed installed (checking needs root). The KB retrieval layer is
  greenfield; `MCP_ENGINES.md` §Chat and retrieval is the spec.
- **No chat / streaming / tool-loop UI anywhere.** The siblings render charts
  and tables, not conversations. The Livewire chat component and the
  orchestrator `/chat` loop are new.
- **No OAuth / Socialite** in any sibling — all use email+OTP only.
- No Google embed model, no `nomic-embed-text` / `bge-m3` pulled.

## 5. Right-sizing assessment (Technical Evaluator note)

The brief specifies four visualization engines, an MCP server in front of the
database, and an adapter that routes "by task complexity and data volume". On
this hardware, for excise analytics, most of that is cost without return.
Recommendations, each reversible:

1. **Ship one visualization engine (Python) and stop.** Excise questions
   produce time series, bar/line/stacked charts, district choropleths, and the
   occasional linear trend or growth rate. Matplotlib + Plotly + pandas +
   NumPy + SciPy cover all of it. Octave, MATLAB, and Mathematica add a Go
   binary, a paid license that forbids multi-user use, `wolframscript`, three
   more sandbox profiles, and an adapter layer — for zero capability the Python
   stack lacks here. Keep `IVisualizationEngine` as a thin seam (it is nearly
   free), implement `PythonEngine` only. Add
   [`OctaveEngine`](https://octave.org) if and when a real `.m` script needs to
   run ([open-source alternatives to
   MATLAB](https://opensource.com/alternatives/matlab) is the same argument);
   treat [MATLAB](https://in.mathworks.com/products/matlab.html) /
   [Mathematica](https://www.wolfram.com/mathematica/) as out of scope until
   there is a concrete symbolic-math or proprietary-toolbox requirement and a
   license story.

2. **Drop the MCP server between the orchestrator and Postgres.** MCP-server
   adoption is a per-capability call (`MCP_ENGINES.md` §MCP servers vs
   visualization engines); for this link the answer is no. It is
   indirection with a single in-process consumer. A direct `asyncpg` pool on
   the read-only role, `default_transaction_read_only = on`, a statement
   timeout, and a "single SELECT / WITH only" parser gives the same safety with
   less to run and monitor. Mount `crystaldba/postgres-mcp` later only if an
   external MCP client (Claude Desktop, an IDE) becomes a real second consumer.
   The word "MCP" in the project name does not require an MCP server here — the
   orchestrator being an MCP *client* to Ollama's tool interface is the part
   that matters.

3. **Route by an explicit `engine` field, not a heuristic.** The LLM picks
   `engine` from an allowlist (`["python"]` today), default `python`. A
   "complexity and data volume" classifier is a guessing layer that will pick
   wrong and be hard to debug. Explicit selection is one line and always
   correct.

4. **Set concurrency expectations in the UI.** CPU-only 7B inference plus a
   sandboxed plot process is a one-at-a-time workload on this box. The web
   layer queues; the UI shows position in queue. Do not design for many
   simultaneous analysts.

5. **Match the installed stack, not the brief's versions.** Build `web/` on
   Laravel 13 / Livewire 4 / PHP 8.5 like the four siblings, not Laravel 11/12
   / Livewire 3.

6. **Knowledge base: FTS before vectors.** Built-in Postgres full-text search
   over a few thousand chunks needs no extension and no embedding model.
   `kb.chunks` keeps a nullable `embedding` column so `pgvector` is a later
   `ALTER` + backfill, not a rebuild. Turn embeddings on only when the
   representative question set shows FTS missing sections (§2b).

7. **Chat: native Livewire against the orchestrator stream.** The
   orchestrator already owns the tool loop; `web/` renders and streams. One
   implementation of each tool, one web app, no Docker (§2c).

8. **Chat routing: the model picks tools, no classifier.** Same reasoning as
   point 3 — a "is this a data question or a law question" classifier guesses
   and is hard to debug. The system prompt describes the three tools; the
   model calls what it needs, including none.

9. **Google: OAuth via Socialite, service account kept.** One package for the
   OAuth flow; per-user encrypted refresh tokens; register specific
   folders/sheets/docs, not "all of Drive". Prefer an Internal consent screen
   to avoid restricted-scope verification (§Google OAuth).

The full four-engine, MCP-server, heuristic-router design stays documented in
`ARCHITECTURE.md` and `MCP_ENGINES.md` as the target shape if requirements grow.
The recommendation is to build the reduced version first and let real use pull
the rest in.
