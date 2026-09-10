# excise-mcp-dashboard

On-premise conversational analytics for UP Excise departmental data. An
authorized user asks a question in plain language; a local LLM — Qwen 2.5 or
Llama 3.1 served through Ollama, never DeepSeek — turns it into a read-only SQL
query against a PostgreSQL copy of the excise figures, runs a sandboxed
analysis/plot script, and the web UI shows
the chart, the table, and the generated SQL. A knowledge base over the
department's verified acts, rules, and policies answers questions about the
law, and an OpenWebUI-style chat window ties the two together.

**Status: planning. This repository is documentation only** — no application
code, no environment, no installs, until the design is approved. Everything
here is the blueprint a build session works from.

## Documents

| File | Covers |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Session rules, coding conventions, negative constraints, test gates |
| [EVALUATION.md](EVALUATION.md) | Hardware audit, Ollama model choice, retrieval and chat-integration decisions, reusable-module inventory, right-sizing assessment |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Systems overview, request paths, trust boundaries, the diagrams |
| [DATA_PIPELINE.md](DATA_PIPELINE.md) | ETL design, the PostgreSQL schema, the `kb` knowledge-base schema, Google Sheets/Drive/Docs sources |
| [MCP_ENGINES.md](MCP_ENGINES.md) | The FastAPI orchestrator, the `IVisualizationEngine` adapter, the chat tool loop and retrieval, per-engine integration guides |
| [SECURITY.md](SECURITY.md) | Read-only PostgreSQL role, the bubblewrap execution sandbox, knowledge-base read paths, Google OAuth, Cloudflare Tunnel + Access |
| [ROADMAP.md](ROADMAP.md) | Six milestones, checklist-driven |
| [OPERATOR_SETUP.md](OPERATOR_SETUP.md) | Every `sudo` / install / Google-console / Cloudflare step, copy-pasteable, grouped by milestone |

## Shape

Three deployable units in one repo:

- **`web/`** — Laravel 13 + Livewire 4: the analytical form, the chat window,
  admin screens (users, connected Google sources, knowledge base).
- **`orchestrator/`** — Python 3.12 + FastAPI: the MCP client to Ollama, the
  SQL guard and read-only runner, the visualization sandbox, knowledge
  retrieval, and the streaming chat tool loop.
- **`etl/`** — Python 3.12: ingestion from Google Sheets/Drive/Docs, Excel,
  and CSV into PostgreSQL, plus the verified document corpus from
  [`pdf-markdown-pipeline`](https://github.com/SubhanRaj/pdf-markdown-pipeline)
  and admin `.md` uploads into the knowledge base.

## Constraints (see `CLAUDE.md` for the full list)

- No DeepSeek models, in any role.
- No unsandboxed execution of generated code.
- The AI path reaches PostgreSQL only through a `SELECT`-only role with
  `default_transaction_read_only = on` — writes are refused by the database
  engine, not by application-level string filtering.
- No document, prompt, embedding, or query leaves the box, except the
  Cloudflare Tunnel that serves the UI and the Google API used for ingestion.
