<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/up-gov-emblem-white.png">
  <img src="assets/brand/up-gov-emblem.svg" width="96" height="96" alt="State Emblem of Uttar Pradesh">
</picture>

# UP Excise MCP Dashboard

**Conversational analytics for UP Excise departmental data, on-premise, with a local LLM**

[![Laravel](https://img.shields.io/badge/Laravel-13-FF2D20?logo=laravel&logoColor=white)](https://laravel.com)
[![Livewire](https://img.shields.io/badge/Livewire-4-4E56A6?logo=livewire&logoColor=white)](https://livewire.laravel.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.12-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen%202.5%20%2F%20Llama%203.1-000000)](https://ollama.com)
[![Status](https://img.shields.io/badge/status-Milestone%205%20in%20progress-orange)](ROADMAP.md)

</div>

---

The app runs end to end on the department's own server. Milestones 0 through 4
are complete, and Milestone 5 (the Laravel UI) is in progress. Google ingestion
and the saved-analyses and report features (Milestone 7) are not built.
[ROADMAP.md](ROADMAP.md) has the checklist.

## What it does

- **Ask** takes a question in plain language and returns a read-only SQL query,
  the result table (money columns in ₹ with Indian digit grouping), an
  interactive chart, a short summary of the numbers, and
  the SQL itself. Each question is recorded in a ledger with its timings and
  stage.
- **Chat** is a streaming conversation with the local chat model. The model
  calls two tools, `search_knowledge` for the law and `run_sql_query` for the
  data, and it can take several turns of tool calls before it answers. When the
  composer's chart toggle is on and a query returns more than one row, a chart
  is planned and rendered after the query.
- **Knowledge base** holds UP Excise acts, rules, and policies synced from the
  [`pdf-markdown-pipeline`](https://github.com/SubhanRaj/pdf-markdown-pipeline)
  corpus. Retrieval is PostgreSQL full-text search, scoped to Uttar Pradesh
  unless a question asks to compare states. Each retrieved passage is cited with
  its title, state, and heading. Admin `.md` uploads are stored, but nothing
  ingests them yet.
- **Admin screens** cover users, the knowledge base, the data dictionary (table
  and column notes that the SQL model reads), ETL run history, the activity log,
  and system health.

## How a question is answered (Ask)

1. The Laravel queue worker sends the question to the orchestrator. The browser
   polls a status route for stage updates.
2. The orchestrator asks the SQL model for one `SELECT`, checks it with a
   SQL parser, and runs it as a `SELECT`-only role inside a `READ ONLY`
   transaction with a statement timeout. A rejected or failing statement gets
   one re-plan with the error attached.
3. The plot model writes a Python script (pandas, Matplotlib, Plotly) for the
   result. The script runs in a bubblewrap sandbox with no network, a read-only
   filesystem, one writable scratch directory, and wall-clock and memory caps.
   A failed script gets one re-plan with its error attached.
4. The chat model writes the plain-language summary. When the result breaks a
   figure down, the summary states the total and each part. Money figures are
   converted to lakh and crore in Python before they reach the model.

A result with no rows, or only empty values, skips the summary and returns a
fixed message instead.

## Components

Three deployable units in one repository. Each has its own virtual environment
or Composer and npm install.

| Unit | Runtime | Role |
|---|---|---|
| `web/` | Laravel 13, Livewire 4, PHP 8.5 | Ask and Chat screens, admin screens, auth (email OTP), query ledger, chart export |
| `orchestrator/` | Python 3.12, FastAPI | Ollama client, SQL guard and read-only runner, sandboxed chart engines, knowledge retrieval, streaming chat loop |
| `etl/` | Python 3.12 | Loads the IESCMS dispatch reports, SRO shop snapshot, NITI workbooks, and the pdf-markdown-pipeline corpus into PostgreSQL |

PostgreSQL 18 holds the data bank: `analytics.*` views over the fact tables, the
`kb` knowledge schema, and the `etl` bookkeeping tables. The operational store
(users, conversations, the query ledger, the queue) is a MariaDB database owned
by `web/`. The orchestrator is the only component that connects to PostgreSQL.

## Models

Ollama serves two models, both resident together:

| Role | Model | Used for |
|---|---|---|
| SQL and plot planning | `qwen2.5-coder:7b-instruct-q4_K_M` | Writing SQL and chart scripts |
| Chat and summaries | `llama3.1:8b-instruct-q4_K_M` | The chat turn, its tool calls, and the Ask summary |

`web/config/models.php` is the registry. The orchestrator accepts only the
Ollama tags listed in its `OLLAMA_ALLOWED_MODELS` setting. The chat window shows
a model picker when more than one chat-role model is registered.

Charts run through a Python engine. A GNU Octave engine is also implemented
and runs in the same sandbox, but chat charts use only the Python engine. The
MATLAB and Wolfram engines are documented stubs, disabled by default
(`ENABLE_MATLAB`, `ENABLE_WOLFRAM`). The engine adapter is the
`IVisualizationEngine` interface in `orchestrator/app/engines/base.py`.

Static chart export (PNG, SVG, PDF) runs outside the sandbox, in one persistent
isolated browser that rasterizes an already-produced Plotly JSON file. LLM-written
code never calls Plotly's own image export, which needs a headless browser the
sandbox cannot launch.

## Documents

| File | Covers |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Session rules, conventions, negative constraints, test gates, and the change log |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System overview, request paths, trust boundaries, diagrams |
| [DATA_PIPELINE.md](DATA_PIPELINE.md) | ETL design, the PostgreSQL schema, the `kb` schema, the data sources |
| [MCP_ENGINES.md](MCP_ENGINES.md) | The orchestrator, the engine adapters, the chat tool loop, retrieval |
| [EVALUATION.md](EVALUATION.md) | Hardware audit, model choice, retrieval and chat decisions, right-sizing |
| [SECURITY.md](SECURITY.md) | Read-only role, the bubblewrap sandbox, knowledge-base read paths, Google OAuth, the tunnel and login gate, the audit trail |
| [ROADMAP.md](ROADMAP.md) | Milestones and their checklists |
| [OPERATOR_SETUP.md](OPERATOR_SETUP.md) | The `sudo`, install, Google Console, and Cloudflare steps, grouped by milestone |

## Constraints

- Generated code runs only inside the sandbox. Nothing runs on the host.
- The AI path reaches PostgreSQL through a `SELECT`-only role with
  `default_transaction_read_only = on`. The database refuses writes; the
  application does not rely on string filtering for that.
- No document, prompt, embedding, or query leaves the box, except the
  Cloudflare Tunnel that serves the UI and the Google APIs used for ingestion.
- No DeepSeek models, for chat or embeddings.

The full list is in [CLAUDE.md](CLAUDE.md).
