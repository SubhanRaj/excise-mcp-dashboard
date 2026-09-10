# ARCHITECTURE.md — excise-mcp-dashboard

## Systems overview

Three deployable units on one Linux host (the office AIO), fronted by a single
Cloudflare Tunnel, sharing one PostgreSQL data bank.

| Unit | Runtime | Port | Exposure | Job |
|---|---|---|---|---|
| `web/` | Laravel 13 + Livewire 4, PHP 8.5, Apache vhost | 8084 | via Cloudflare Tunnel + Access | Split-view chat/chart UI, auth, query ledger, exports, background jobs |
| `orchestrator/` | Python 3.12 + FastAPI, uvicorn | 8085 | `127.0.0.1` only | MCP client to Ollama, SQL generation, engine router, sandbox launcher |
| `etl/` | Python 3.12 CLI, run by cron / systemd timers | — | none | Normalize Sheets / Drive / Excel / CSV into PostgreSQL |
| PostgreSQL 18 | system service | 5432 | `127.0.0.1` (+ Tailscale later if needed) | The excise data bank — read-only for the AI path |
| Ollama | system service | 11434 | `127.0.0.1` | Local LLM inference, CPU-only |
| MariaDB | system service | 3306 | `127.0.0.1` | `web/` operational store — sessions, users, ledger, queue |

### Request path for one question

1. Analyst signs in through Cloudflare Access, then the app's OTP login, and
   types a question in the left pane.
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
5. The job stores a `queries` row (prompt, SQL, timing, engine, status), a
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

### Trust boundaries

- **Internet -> Cloudflare edge**: TLS, Access policy (email domain / group).
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
  data tables only, no DDL after the initial migration. Runs from cron, not
  reachable from the web path.

### Failure behavior

Every stage failure is typed and surfaced: `Ollama unreachable`, `SQL rejected`
(not a single SELECT), `SQL error` (DB raised), `query timeout`, `engine
unavailable`, `sandbox timeout`, `sandbox violation`, `render produced no
output`. The web app shows the failed stage and still writes a ledger row so
failures are reviewable. One automatic retry only for a malformed structured
output from the LLM.

### What is deliberately not in the first build

Octave / MATLAB / Mathematica engines, an MCP server in front of Postgres, and
a complexity-based routing heuristic. The interfaces below accommodate them;
`EVALUATION.md` §Right-sizing explains why they wait. `ROADMAP.md` Milestone 3
adds Octave behind the same `IVisualizationEngine`.

## Component diagrams

### Diagram 1: comprehensive system flow

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

### Diagram 2: execution security & read-only sandbox

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

## Cross-references

- Hardware limits and model choice: `EVALUATION.md`
- ETL design and the PostgreSQL schema: `DATA_PIPELINE.md`
- Orchestrator internals, `IVisualizationEngine`, per-engine guides:
  `MCP_ENGINES.md`
- Read-only role SQL, sandbox invocation, tunnel + Access config: `SECURITY.md`
- Build order and checklists: `ROADMAP.md`
- Session rules and conventions: `CLAUDE.md`
