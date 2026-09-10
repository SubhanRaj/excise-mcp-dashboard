# excise-mcp-dashboard

On-premise conversational analytics for Uttar Pradesh Excise departmental data.
Ask a question in plain language; a local LLM turns it into a read-only SQL
query over a PostgreSQL copy of the excise figures, runs a sandboxed analysis
and plot script, and the web UI shows the chart, the data table, and the
generated SQL.

> **Status: planning.** This repository is documentation only — no application
> code, no environment, no installs — until the design is approved. Everything
> here is the blueprint a build session works from.

## What it does

- **Analytical questions.** A natural-language question in; a read-only SQL
  query, an interactive chart, a data table, a written summary, and the SQL
  itself out. Every query is kept in a ledger.
- **Knowledge base.** UP Excise acts, rules, regulations, and policies, drawn
  from the department's verified document repository and admin `.md` uploads.
  Questions about the law are answered from this corpus with citations back to
  the source.
- **Chat window.** An OpenWebUI-style streaming conversation with the local
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
| `web/` | Laravel 13 + Livewire 4, PHP 8.5 | Analytical form, chat window, admin screens (users, connected Google sources, knowledge base), auth, query ledger, exports |
| `orchestrator/` | Python 3.12 + FastAPI | Local-model client, SQL guard and read-only runner, visualization sandbox, knowledge retrieval, streaming chat tool loop |
| `etl/` | Python 3.12 | Ingestion from Google Sheets / Drive / Docs, Excel, and CSV into PostgreSQL; verified documents and admin uploads into the knowledge base |

The model is served by [Ollama](https://ollama.com) (Qwen 2.5 / Llama 3.1),
CPU-only. Retrieval is PostgreSQL full-text search, with `pgvector` as a
documented upgrade. The verified document corpus comes from
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
