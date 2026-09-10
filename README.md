<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/up-gov-emblem-white.png">
  <img src="assets/brand/up-gov-emblem.svg" width="96" height="96" alt="State Emblem of Uttar Pradesh">
</picture>

# UP Excise MCP Dashboard

**Conversational analytics for UP Excise departmental data — on-premise, local LLM**

Ask a question in plain language; a local model turns it into a read-only SQL
query over a PostgreSQL copy of the excise figures, runs a sandboxed chart
script, and the web UI shows the chart, the table, and the generated SQL. A
knowledge base over the department's verified acts and rules answers questions
about the law, and an OpenWebUI-style chat window reaches both.

[![Laravel](https://img.shields.io/badge/Laravel-13-FF2D20?logo=laravel&logoColor=white)](https://laravel.com)
[![Livewire](https://img.shields.io/badge/Livewire-4-4E56A6?logo=livewire&logoColor=white)](https://livewire.laravel.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.12-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen%202.5%20%2F%20Llama%203.1-000000)](https://ollama.com)
[![Status](https://img.shields.io/badge/status-planning-blue)](ROADMAP.md)

</div>

---

> **Planning stage.** This repository is documentation only — no application
> code, no environment, no installs — until the design is approved. Everything
> here is the blueprint a build session works from.

## What it does

- **Analytical questions** — a natural-language question in; a read-only SQL
  query, an interactive chart, a data table, a written summary, and the SQL
  itself out. Every query is kept in a ledger.
- **Knowledge base** — UP Excise acts, rules, regulations, and policies, from
  the department's verified document repository and admin `.md` uploads.
  Questions about the law are answered from this corpus with citations back to
  the source.
- **Chat window** — an OpenWebUI-style streaming conversation with the local
  model. It calls the same SQL, retrieval, and charting tools mid-conversation,
  so the data and the law are both reachable without leaving the chat.

## How a question is answered

1. The Laravel UI queues the question and streams stage updates to the browser.
2. The FastAPI orchestrator asks the local model for one `SELECT`, checks it is
   a single read-only statement, and runs it as a `SELECT`-only PostgreSQL role
   inside a `READ ONLY` transaction with a statement timeout.
3. The model writes a Python plot script. It runs in a bubblewrap sandbox with
   no network, a read-only filesystem, one writable scratch directory, and wall
   clock and memory caps.
4. The UI renders the chart, the table, the SQL, and a short plain-language
   summary of the numbers.

## Components

Three deployable units in one repository.

| Unit | Runtime | Role |
|---|---|---|
| `web/` | Laravel 13 + Livewire 4, PHP 8.5 | Analytical form, chat window, admin screens, auth, query ledger, exports |
| `orchestrator/` | Python 3.12 + FastAPI | Local-model client, SQL guard and read-only runner, visualization sandbox, knowledge retrieval, streaming chat tool loop |
| `etl/` | Python 3.12 | Ingestion from Google Sheets / Drive / Docs, Excel, and CSV into PostgreSQL; verified documents and admin uploads into the knowledge base |

The model runs on [Ollama](https://ollama.com) (Qwen 2.5 / Llama 3.1), CPU-only.
Retrieval is PostgreSQL full-text search, with `pgvector` as a documented
upgrade. The verified document corpus comes from
[`pdf-markdown-pipeline`](https://github.com/SubhanRaj/pdf-markdown-pipeline).

## Documents

| File | Covers |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Session rules, coding conventions, negative constraints, test gates |
| [EVALUATION.md](EVALUATION.md) | Hardware audit, model choice, retrieval and chat-integration decisions, reusable-module inventory, right-sizing assessment |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Systems overview, request paths, trust boundaries, the diagrams |
| [DATA_PIPELINE.md](DATA_PIPELINE.md) | ETL design, the PostgreSQL schema, the `kb` knowledge-base schema, Google Sheets/Drive/Docs sources |
| [MCP_ENGINES.md](MCP_ENGINES.md) | The FastAPI orchestrator, the `IVisualizationEngine` adapter, the chat tool loop and retrieval, per-engine integration guides |
| [SECURITY.md](SECURITY.md) | Read-only PostgreSQL role, the bubblewrap execution sandbox, knowledge-base read paths, Google OAuth, Cloudflare Tunnel + Access |
| [ROADMAP.md](ROADMAP.md) | Six milestones, checklist-driven |
| [OPERATOR_SETUP.md](OPERATOR_SETUP.md) | Every `sudo` / install / Google-console / Cloudflare step, copy-pasteable, grouped by milestone |

## Constraints (see [CLAUDE.md](CLAUDE.md) for the full list)

- No unsandboxed execution of generated code.
- The AI path reaches PostgreSQL only through a `SELECT`-only role with
  `default_transaction_read_only = on`. Writes are refused by the database
  engine, not by application-level string filtering.
- No document, prompt, embedding, or query leaves the box, except the
  Cloudflare Tunnel that serves the UI and the Google API used for ingestion.
