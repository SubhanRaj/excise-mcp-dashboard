# ARCHITECTURE.md — excise-mcp-dashboard

## Systems overview

Three deployable units on one Linux host (the office AIO), fronted by a single
Cloudflare Tunnel, sharing one PostgreSQL data bank.

| Unit | Runtime | Port | Exposure | Job |
|---|---|---|---|---|
| `web/` | Laravel 13 + Livewire 4, PHP 8.5, Apache vhost | 8084 | via Cloudflare Tunnel; app email-OTP login is the gate | Analytical form + OpenWebUI-style chat window + admin (users, connected Google sources, knowledge base); auth; query ledger; exports; background jobs |
| `orchestrator/` | Python 3.12 + FastAPI, uvicorn | 8085 | `127.0.0.1` only | MCP client to Ollama; one-shot SQL pipeline; streaming chat with a tool loop (`run_sql_query`, `search_knowledge`, `make_chart`); knowledge retrieval; engine router; sandbox launcher |
| `etl/` | Python 3.12 CLI, run by cron / systemd timers | — | Google API (ingestion only) | Sheets / Drive / Docs / Excel / CSV -> Postgres data tables; pdf-markdown-pipeline verified docs + admin `.md` uploads + Google Docs -> `kb.*` |
| PostgreSQL 18 | system service | 5432 | `127.0.0.1` (+ Tailscale later if needed) | The excise data bank (`analytics.*`) and the knowledge base (`kb.*`) — read-only for the AI path |
| Ollama | system service | 11434 | `127.0.0.1` | Local LLM inference + embeddings, CPU-only |
| MariaDB | system service | 3306 | `127.0.0.1` | `web/` operational store — sessions, users, ledger, chat history, output artifacts (`saved_analyses`, `analysis_runs`, `reports`), `kb_uploads`, `google_connections`, queue |

### Request path for one question

1. Analyst signs in through the app's email-OTP login and types a question in
   the left pane.
2. Livewire dispatches a `RunExciseQuery` job (Laravel queue, `database`
   driver) and opens an SSE stream for stage updates. The web worker is not
   blocked.
3. The job calls `POST http://127.0.0.1:8085/query` on the orchestrator with a
   bearer token (shared secret) and the question plus recent conversation
   turns.
4. The orchestrator:
   a. sends the question, the excise schema, and few-shot examples to Ollama
      (`qwen2.5-coder:7b`), requesting a structured `SqlPlan` (one `SELECT`);
   b. validates the SQL is a single read-only statement, runs it on the
      read-only `asyncpg` pool inside a `READ ONLY` transaction with a
      statement timeout;
   c. sends the result shape back to Ollama for a `PlotPlan` (engine +
      script), validates it, writes the script to a scratch dir;
   d. runs the script in the `bwrap` sandbox (no network, one writable dir,
      wall-clock + memory caps), collecting a Plotly JSON blob and/or a
      PNG/SVG/PDF;
   e. asks Ollama for a short plain-language summary of the numbers;
   f. returns `{sql, rows_preview, chart, summary, stages[], request_id}`.
5. The job stores a `queries` row (prompt, SQL, timing, engine, model, status), a
   `chart_artifacts` row (files on the `local` disk), and streams `Complete`.
6. The right pane renders the interactive chart, the data table, and the
   generated SQL. The ledger view lists every past query with its feedback
   control.

### Streaming stages

`Querying database -> Running analysis -> Rendering chart -> Complete`, plus a
terminal `Failed: <stage>`. The orchestrator emits each transition on its
response as it goes (chunked) or the job polls a `/query/{id}/status`
endpoint; Laravel relays them to the browser over SSE, with `wire:poll` as the
fallback if SSE behaves badly through the tunnel.

### Request path for a chat message

1. Analyst opens the chat window, picks or starts a conversation, sends a
   message. Livewire posts it and opens an SSE reader.
2. `web/` calls `POST http://127.0.0.1:8085/chat` (bearer token) with the
   message and the trimmed conversation history.
3. The orchestrator runs the tool loop (`MCP_ENGINES.md` §Chat and retrieval):
   the model streams text; when it needs data it calls `run_sql_query` (same
   guard + read-only run as the one-shot path), for the law it calls
   `search_knowledge` (FTS over `kb.chunks`, optionally vector), for a picture
   it calls `make_chart` (same `bwrap` sandbox). Each tool call and result is
   an SSE event.
4. `web/` relays the SSE stream to the browser and persists `messages` +
   `message_tool_calls`; a chart is stored as a `chart_artifacts` row.
5. Cited knowledge chunks render with a link to `docsrepo.exciseup.in`; SQL
   the model ran renders as an inline, copyable card.

### Output artifact lifecycle

The data bank (PostgreSQL) holds raw data only. Everything the model produces —
charts, table previews, summaries, the generated SQL — is an app artifact in
`web/`'s MariaDB plus files on the `local` disk, never written back to
Postgres.

1. A `/query` or chat `make_chart` run writes a `queries` / `message` row and
   `chart.{plotly.json,png,svg,pdf}` under
   `web/storage/app/artifacts/<query-ulid>/`.
2. An unsaved run's files are swept after `ARTIFACT_TTL_DAYS`.
3. A user pins a run into `saved_analyses` (with a `recipe` to re-run it).
   "Refresh" — manual, scheduled, or fired by a matching `etl.ingestion_runs`
   completion — writes an `analysis_runs` row; the history is the trend.
4. `reports` order `saved_analyses` and Markdown blocks into a presentation
   that tracks live data or is frozen to a point in time.
5. Export: a chart as PNG/SVG/PDF/`plotly.json`; a result as CSV/XLSX; a report
   as a dompdf PDF, an XLSX workbook, or a ZIP bundle, each stamped with the
   ETL data vintage. `DATA_PIPELINE.md` §Output store.

### Knowledge ingestion path

- `etl sync --source pdf_pipeline_docs` (daily): reads
  `pdf_markdown_pipeline_local.documents` (a dedicated read-only MariaDB user)
  filtered to public + verified, reads each Markdown file from that project's
  `public` disk, chunks, writes `kb.documents` + `kb.chunks` in Postgres.
- `etl sync --source kb_uploads` (every 15 min): ingests admin-uploaded `.md`
  files staged by `web/`.
- `etl sync --source gdocs_* / gdrive_kb_*`: Google Docs and Drive `.md`/Docs
  via a user's OAuth connection.
- A document that stops being public/verified upstream is marked
  `withdrawn_at`; retrieval skips it, the text stays for audit.

### Google OAuth path

`web/` runs `laravel/socialite` (Google, read-only Drive/Sheets/Docs scopes,
offline access). A per-user `google_connections` row holds an encrypted
refresh token. The ETL reads the refresh token over loopback and lets
`google-auth` mint access tokens; a revoked grant surfaces as "reconnect
needed" on the admin screen. `SECURITY.md` §Google OAuth.

### Trust boundaries

- **Internet -> Cloudflare edge**: TLS termination and the named tunnel on a
  subdomain of `exciseup.in`. No Cloudflare Access — every route is behind the
  app's email-OTP login, so an unauthenticated request only ever reaches
  `/login`.
- **Tunnel -> Apache (8084)**: the only inbound path; no firewall port opened
  (`cloudflared` dials out over `lo`).
- **Laravel -> orchestrator (8085)**: loopback only, bearer token, request-id
  correlation. The orchestrator refuses any request without the token.
- **Orchestrator -> PostgreSQL**: dedicated `LOGIN` role, `SELECT` only,
  `default_transaction_read_only = on`, statement timeout. DDL/DML refused by
  the engine.
- **Orchestrator -> sandbox**: generated scripts run as a non-root user inside
  a `bwrap` namespace — no network, root filesystem read-only, one writable
  scratch dir, `RLIMIT` memory cap, `timeout(1)` wall clock. See `SECURITY.md`.
- **ETL -> PostgreSQL**: separate role with `INSERT`/`UPDATE`/`DELETE` on the
  data tables and `kb.*` only, no DDL after the initial migration. Runs from
  cron, not reachable from the web path.
- **Orchestrator -> knowledge base**: the same read-only role reads `kb.*`
  (`SELECT` only). Retrieval is FTS (built-in) or, when enabled, `pgvector`
  cosine search with embeddings from the local Ollama — no outbound network.
- **ETL -> Google API**: the only outbound call other than the tunnel.
  Read-only scopes; a service account for server-owned content, a user's
  OAuth refresh token for their own Drive/Sheets/Docs. Tokens are encrypted
  at rest and never logged.
- **`web/` -> pdf-markdown-pipeline data**: read-only. A scoped MariaDB user
  (`SELECT` on `pdf_markdown_pipeline_local` only) and group-read on that
  project's `storage/app/public` Markdown tree. No write path.

### Failure behavior

Every stage failure is typed and surfaced: `Ollama unreachable`, `SQL rejected`
(not a single SELECT), `SQL error` (DB raised), `query timeout`, `engine
unavailable`, `sandbox timeout`, `sandbox violation`, `render produced no
output`. The web app shows the failed stage and still writes a ledger row so
failures are reviewable. One automatic retry only for a malformed structured
output from the LLM.

### Not in the first build

Octave / MATLAB / Mathematica engines, an MCP server in front of Postgres, a
complexity-based routing heuristic, `pgvector` semantic retrieval, and an
embedded OpenWebUI. The interfaces accommodate all of them; `EVALUATION.md`
§Right-sizing explains why they wait. `ROADMAP.md` Milestone 3 builds the
knowledge base on Postgres FTS; Milestone 4 adds Octave behind the same
`IVisualizationEngine`; `pgvector` is a config flag plus a backfill if the
Milestone 6 quality check calls for it.

## Component diagrams

Diagrams 1 and 2 are the two from the brief. Diagrams 1U and 2U match what
this repo specifies: bubblewrap as the sandbox, a direct read-only `asyncpg`
pool in place of a standalone Postgres MCP server, one Python engine, Livewire
4, and the knowledge base, chat window, and Google OAuth. Diagram 3 covers the
chat and ingestion paths.

### Diagram 1 (as supplied in the brief): comprehensive system flow

```mermaid
flowchart TD
    classDef client fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#fff
    classDef edge fill:#d97706,stroke:#b45309,stroke-width:2px,color:#fff
    classDef app fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef ai fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef viz fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    classDef db fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff

    User([Public/Internal User]):::client
    CF[Cloudflare Tunnel\nZero Trust / Access Control]:::edge

    subgraph Linux_Host [Local Linux Infrastructure]
        subgraph Web_Tier [Web & Presentation Layer]
            Web[Laravel Application\nLivewire 3 + Tailwind CSS]:::app
            Queue[Laravel Queue Worker\nAsync Background Jobs]:::app
        end

        subgraph Ingestion_Tier [ETL & Data Sync Layer]
            ETL[Python Ingestion Service\nScheduled Cron Jobs]:::db
            Sources[(Google Drive / Sheets\nExcel / Local Storage)]:::db
            ETL <--> Sources
        end

        subgraph Data_Tier [Primary Data Store]
            PG[(PostgreSQL Database\nExcise Data Bank)]:::db
            ETL -->|Normalize & Insert| PG
        end

        subgraph Orchestration_Tier [MCP & AI Layer]
            FastAPI[Python FastAPI Microservice\nMCP Client & Router]:::app
            Ollama((Ollama Local LLM\nLlama 3.1 / Qwen 2.5)):::ai
        end

        subgraph Sandbox_Tier [Switchable Visualization Engines]
            Adapter{Engine Adapter Router}:::viz
            PyEngine[Native Python\nPandas / Matplotlib / Plotly]:::viz
            OctaveEngine[GNU Octave CLI\nHeadless .m Runner]:::viz
            MatlabEngine[Official MATLAB MCP\nGo Binary + Engine]:::viz
            WolframEngine[WolframScript\nMathematica Engine]:::viz
        end
    end

    User <-->|HTTPS| CF
    CF <-->|Reverse Proxy| Web
    Web <-->|Authenticated REST API| FastAPI
    Web -.->|Dispatches| Queue
    
    FastAPI <-->|Context & JSON Schema| Ollama
    Ollama -.->|Tool Calls| FastAPI
    
    FastAPI -->|postgres-mcp-server\nRead-Only SELECT| PG
    FastAPI -->|Route Script Execution| Adapter
    
    Adapter -->|Open-Source Python| PyEngine
    Adapter -->|Open-Source Octave| OctaveEngine
    Adapter -->|Proprietary MATLAB| MatlabEngine
    Adapter -->|Proprietary Mathematica| WolframEngine

    PyEngine -.->|Static PNG / Interactive JSON| FastAPI
    OctaveEngine -.->|Exported Chart| FastAPI
    MatlabEngine -.->|Exported Figure| FastAPI
    WolframEngine -.->|Rendered Graphic| FastAPI

    FastAPI -.->|Unified Payload + Insights| Web
```

> Implementation note: the first build wires `Web -> FastAPI -> Ollama`,
> `FastAPI -> PG` (direct `asyncpg`, read-only role, no separate
> `postgres-mcp-server` process), and `Adapter -> PyEngine` only. The Octave,
> MATLAB, and Wolfram paths and the standalone Postgres MCP server are drawn
> here as the target shape; see `EVALUATION.md` §Right-sizing and `ROADMAP.md`.

### Diagram 1U (updated): system flow as this repo specifies it

```mermaid
flowchart TD
    classDef client fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#fff
    classDef edge fill:#d97706,stroke:#b45309,stroke-width:2px,color:#fff
    classDef app fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef ai fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef viz fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    classDef db fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    classDef off fill:#94a3b8,stroke:#64748b,stroke-width:1px,color:#fff,stroke-dasharray:4 3

    User(["Analyst"]):::client
    CF["Cloudflare Tunnel<br/>subdomain of exciseup.in; app email-OTP login is the gate"]:::edge

    subgraph Host["Office AIO — on-premise, no inbound ports"]
        subgraph WebTier["web/ — Laravel 13 + Livewire 4, Apache 8084"]
            Ask["Ask — one-shot analytical form"]:::app
            Chat["Chat — streaming conversation"]:::app
            Admin["Admin — users, connected Google sources, knowledge base"]:::app
            Queue["Queue worker — RunExciseQuery job"]:::app
            MDB[("MariaDB<br/>users, ledger, chat history,<br/>kb_uploads, google_connections")]:::db
        end

        subgraph Orch["orchestrator/ — FastAPI 8085, loopback only"]
            OneShot["pipeline.py<br/>plan_sql then guard then run then plot then summarize"]:::app
            Loop["chat/loop.py<br/>agentic tool loop"]:::app
            Guard["sql/guard.py + sql/runner.py<br/>single SELECT, READ ONLY txn"]:::app
            Retr["kb/retrieve.py<br/>Postgres FTS (pgvector off)"]:::app
            PyEng["engines/python_engine.py<br/>Matplotlib / Plotly / pandas"]:::viz
        end

        Ollama(("Ollama — CPU only<br/>qwen2.5-coder 7b, llama3.1 8b")):::ai
        Sbx["bwrap sandbox<br/>no network, read-only FS, one scratch dir<br/>15s / 1GB caps, non-root user"]:::viz

        subgraph Bank["PostgreSQL 18 (5432) — the data bank"]
            AN[("analytics.* views<br/>published rows only")]:::db
            KB[("kb.documents / kb.chunks<br/>tsvector FTS")]:::db
        end

        subgraph EtlTier["etl/ — cron / systemd timers"]
            EtlData["data sources<br/>Sheets / Drive / Excel / CSV"]:::app
            EtlKB["kb sources<br/>pdf-pipeline / uploads / Docs"]:::app
        end

        OctEng["engines/octave_engine.py<br/>Milestone 4"]:::off
        MatEng["matlab / wolfram adapters<br/>stub, flag-off"]:::off
    end

    GAPI[["Google Drive / Sheets / Docs API<br/>read-only scopes"]]:::edge
    PDFP[("pdf-markdown-pipeline<br/>MariaDB + public .md<br/>verified + public only")]:::db

    User <-->|HTTPS| CF
    CF <-->|reverse proxy| WebTier
    Ask -->|dispatch| Queue
    Queue -->|"/query bearer"| OneShot
    Chat <-->|"/chat SSE bearer"| Loop
    Admin --- MDB
    Ask --- MDB
    Chat --- MDB

    OneShot --> Guard
    Loop --> Guard
    Loop --> Retr
    OneShot <--> Ollama
    Loop <--> Ollama
    Guard -->|"SELECT as excise_ro"| AN
    Retr -->|"SELECT as excise_ro"| KB
    OneShot --> PyEng
    Loop --> PyEng
    PyEng --> Sbx
    PyEng -.->|"plotly json + png/svg/pdf"| OneShot
    OctEng -.-> Sbx

    EtlData -->|"INSERT as excise_etl"| AN
    EtlKB -->|"INSERT as excise_etl"| KB
    EtlData <--> GAPI
    EtlKB <--> GAPI
    EtlKB -->|read-only| PDFP
    Admin -.->|"OAuth connect (Socialite)"| GAPI

    Retr -.->|"cited snippets + docsrepo links"| Loop
    OneShot -.->|"sql + rows + chart + summary"| WebTier
```

> Grey dashed nodes (Octave, MATLAB, Wolfram) are not in the first build.
> Everything else is Milestones 1-6 in `ROADMAP.md`.

### Diagram 2 (as supplied in the brief): execution security & read-only sandbox

```mermaid
flowchart LR
    classDef safe fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef danger fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    classDef box fill:#475569,stroke:#334155,stroke-width:2px,color:#fff

    subgraph LLM_Boundary [LLM Generated Code]
        SQL[Generated SQL Query]:::safe
        Script[Generated Viz Script]:::safe
    end

    subgraph Security_Gateways [Security Enforcement]
        PG_User[PostgreSQL Security Context\nStrict READ-ONLY User\nNo Write/Drop/Alter]:::box
        Firejail[OS Execution Sandbox\nFirejail / Subprocess Limits\nNo Network / Read-Only FS]:::box
    end

    subgraph Execution_Targets [Safe Execution Targets]
        DB[(PostgreSQL)]:::safe
        Engines[Python / Octave / MATLAB Engines]:::safe
    end

    SQL --> PG_User --> DB
    Script --> Firejail --> Engines
```

> Implementation note: the OS sandbox on this box is **bubblewrap (`bwrap`
> 0.11.1)**, already installed, plus a non-root execution user, `RLIMIT`
> memory caps, and `timeout(1)`. `firejail` is not installed and is not
> required. `SECURITY.md` §Code-execution sandbox has the exact invocation.

### Diagram 2U (updated): three enforcement layers as built

```mermaid
flowchart LR
    classDef safe fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef gen fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef box fill:#475569,stroke:#334155,stroke-width:2px,color:#fff

    subgraph Gen["LLM output — untrusted"]
        SQL["Generated SQL<br/>from /query or the chat run_sql_query tool"]:::gen
        Script["Generated plot script<br/>Python today, Octave later"]:::gen
        Q["User question text<br/>for knowledge search"]:::gen
    end

    subgraph Enforce["Enforcement — each layer independent"]
        G1["sql/guard.py<br/>exactly one SELECT / WITH<br/>analytics + kb only, no volatile fns<br/>LIMIT injected"]:::box
        G2["Role excise_ro<br/>SELECT only on analytics.* + kb.*<br/>default_transaction_read_only = on<br/>statement_timeout 10s"]:::box
        G3["bwrap namespace + non-root user<br/>unshare-all so no network<br/>read-only root FS, one writable scratch dir<br/>RLIMIT_AS 1GB, timeout KILL 15s"]:::box
        G4["Fixed parametrised query<br/>websearch_to_tsquery / vector search<br/>user text bound as a parameter"]:::box
    end

    subgraph Targets["Targets"]
        DB[("PostgreSQL<br/>analytics.* views + kb.*")]:::safe
        Eng["Python / Octave engine<br/>inside the sandbox"]:::safe
    end

    SQL --> G1
    G1 --> G2
    G2 --> DB
    Script --> G3
    G3 --> Eng
    Q --> G4
    G4 --> DB
```

> The read-only role is the primary control for data access; the guard and the
> `READ ONLY` transaction are redundant layers on top. `search_knowledge` runs
> no model-authored SQL at all. `SECURITY.md` §1 and §2 have the exact grants
> and the `bwrap` command line.

### Diagram 3: chat, knowledge, and ingestion

Covers the chat window, the knowledge base, and the Google OAuth ingestion
paths.

```mermaid
flowchart TD
    classDef client fill:#2563eb,stroke:#1d4ed8,stroke-width:2px,color:#fff
    classDef app fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef ai fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef db fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    classDef ext fill:#d97706,stroke:#b45309,stroke-width:2px,color:#fff

    User(["Analyst"]):::client
    Chat["Livewire Chat window<br/>SSE stream, markdown + code render"]:::app
    Orch["FastAPI orchestrator<br/>chat tool loop"]:::app
    Ollama(("Ollama<br/>chat + coder + embed, CPU")):::ai

    subgraph Tools["Tools the model calls"]
        T1["search_knowledge"]:::app
        T2["run_sql_query<br/>same guard + read-only role"]:::app
        T3["make_chart<br/>same bwrap sandbox"]:::app
    end

    subgraph Bank["PostgreSQL data bank"]
        AN[("analytics.* views<br/>published rows")]:::db
        KB[("kb.documents / kb.chunks<br/>FTS, optional pgvector")]:::db
    end

    subgraph Ingest["etl/ — cron / timers"]
        E1["pdf_pipeline sync"]:::app
        E2["kb_uploads sync"]:::app
        E3["gdocs / gdrive sync"]:::app
    end

    PDFP[("pdf-markdown-pipeline<br/>MariaDB + public .md files<br/>public + verified only")]:::db
    UP["Admin .md uploads<br/>web/ kb-uploads disk"]:::app
    G[["Google Drive / Sheets / Docs"]]:::ext

    User <--> Chat
    Chat <-->|"/chat bearer"| Orch
    Orch <--> Ollama
    Orch --> T1
    T1 --> KB
    Orch --> T2
    T2 --> AN
    Orch --> T3
    T1 -.->|"cited snippets + docsrepo links"| Chat

    E1 --> PDFP
    E1 --> KB
    E2 --> UP
    E2 --> KB
    E3 --> G
    E3 --> KB
    E3 --> AN

    User -.->|"OAuth connect via web/ Socialite"| G
```

## Cross-references

- Hardware limits, model choice, retrieval and chat-integration decisions,
  reuse inventory: `EVALUATION.md`
- ETL design, PostgreSQL schema, the `kb` schema, Google sources: `DATA_PIPELINE.md`
- Orchestrator internals, `IVisualizationEngine`, per-engine guides, the chat
  tool loop and retrieval: `MCP_ENGINES.md`
- Read-only role SQL, sandbox invocation, knowledge-base read paths, Google
  OAuth, tunnel + Access config: `SECURITY.md`
- Build order and checklists: `ROADMAP.md`
- Every sudo / install / external-console step: `OPERATOR_SETUP.md`
- Session rules and conventions: `CLAUDE.md`
