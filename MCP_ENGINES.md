# MCP_ENGINES.md — orchestrator and visualization engines

## The orchestrator (`orchestrator/`)

Python 3.12 + FastAPI + uvicorn, bound to `127.0.0.1:8085`, started by a
systemd `--user` unit. It is the MCP **client** (to Ollama's tool interface),
the SQL generator, and the engine router. It holds no long-term state beyond
in-memory conversation windows keyed by the ULID Laravel sends; durable
history is the Laravel ledger.

### MCP servers — used where they earn their place

The orchestrator is an MCP **client** to Ollama's tool interface. For every
other capability, direct / in-process is the default and an MCP server goes in
only where it earns its place, decided per capability:

- **SQL over the data bank** — direct `asyncpg` on the read-only role with the
  guard. [`crystaldba/postgres-mcp`](https://github.com/crystaldba/postgres-mcp)
  (`--access-mode=restricted`) is the drop-in if a server is wanted later —
  e.g. an external client (Claude Desktop, an IDE) becomes a second consumer.
- **Knowledge retrieval** — direct `SELECT` on `kb.*`; one parametrised query,
  no server.
- **Python and Octave charts** — the generated script runs natively in the
  `bwrap` sandbox (pandas / NumPy / SciPy / Matplotlib / Plotly; `octave-cli`
  the same way). No MCP.
- **MATLAB** — reached through
  [`matlab/matlab-mcp-server`](https://github.com/matlab/matlab-mcp-server)
  (stdio), the only way MathWorks ships it; the child still runs inside the
  sandbox wrapper (§3).
- **Wolfram** — `wolframscript` subprocess in the sandbox. No MCP.

The visualization engines (Python, Octave, MATLAB, Wolfram) are the thing that
runs the plot script; only MATLAB is an MCP integration.

### Module layout

```
orchestrator/
  app/
    main.py            FastAPI app, lifespan (asyncpg pool, httpx client, ollama warmup)
    config.py          pydantic-settings Settings (one object)
    auth.py            bearer-token dependency
    schemas.py         Pydantic v2: QueryRequest/Response, SqlPlan, PlotPlan, Stage,
                       ChatRequest, chat wire-event models, tool schemas, errors
    llm/
      client.py        Ollama async client, structured-output loop, retry, streaming
      prompts.py       system prompts, schema card, few-shot examples, chat system prompt
    sql/
      guard.py         "single read-only SELECT/WITH" parser + checks
      runner.py        asyncpg pool, READ ONLY txn, statement timeout
      schema_card.py   renders analytics.* views into the prompt schema description
    kb/
      retrieve.py      FTS query over kb.chunks (+ pgvector path when enabled)
      embed.py         local Ollama embed model client (only when KB_EMBEDDINGS_ENABLED)
    chat/
      loop.py          agentic tool-calling loop, streams ndjson events
      tools.py         tool defs: run_sql_query, search_knowledge, make_chart
      prompts.py       chat system prompt, tool JSON schemas for Ollama's `tools=`
    engines/
      base.py          IVisualizationEngine protocol + registry + errors
      python_engine.py implemented
      octave_engine.py implemented
      matlab_engine.py  documented stub, behind ENABLE_MATLAB (default off)
      wolfram_engine.py documented stub, behind ENABLE_WOLFRAM (default off)
    sandbox/
      bwrap.py         build + run the bubblewrap command, collect artifacts
    pipeline.py        the one-shot analytical flow: orchestrates stages, emits Stage events
  tests/
  requirements.txt / requirements.lock
```

### HTTP surface

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/health` | — | `{status, ollama, postgres, engines, models, kb_docs, embeddings}` — no auth; `models` is the registry with a pulled/not-pulled flag each |
| `POST` | `/query` | `QueryRequest` | streamed `Stage` lines then a final `QueryResponse` (chunked), or a typed error |
| `GET` | `/query/{id}/status` | — | last `Stage` for a running query (poll fallback) |
| `POST` | `/chat` | `ChatRequest` | streamed newline-delimited JSON (`application/x-ndjson`, matching `/query`) — `token` / `tool_call` / `tool_result` / `chart` / `done` / `error` lines |
| `POST` | `/kb/search` | `{query: str, k: int}` | `{chunks: [...]}` — ranked FTS retrieval, no LLM (used by tests and the "cite sources" panel) |
| `GET` | `/kb/documents` | — (paginated: `?page`) | `{documents: [...], total}` — unranked listing of `kb.documents` for the admin "browse the corpus" screen |
| `POST` | `/chart/render` | `ChartRenderRequest` (`spec`: a Plotly figure dict, `format`: `png`/`svg`/`pdf`) | the rasterized bytes, correct `Content-Type` — rasterizes an already-produced figure through `get_static_renderer()` (`engines/static_render.py`), the same persistent-browser renderer the sandboxed render step uses; no LLM-authored code runs on this path |
| `GET` | `/etl/runs` | — (paginated: `?page`) | `{runs: [...], total}` — `etl.ingestion_runs` rows for the admin ETL visibility screen |
| `GET` | `/etl/quarantine` | — (paginated: `?page`, optional `?run_id`) | `{rows: [...], total}` — `etl.quarantine` rows, optionally filtered to one run |

Both `/query` and `/chat` require the bearer token. `/query` is the one-shot
analytical form (question in, chart + table + SQL + summary out). `/chat` is
the free-form conversation where the model decides which tools to call.
`/chart/render`, `/etl/runs`, and `/etl/quarantine` are also bearer-gated;
none of the three touches an LLM.

`QueryRequest`:

```python
class QueryRequest(BaseModel):
    conversation_id: str            # ULID from Laravel
    question: str
    history: list[Turn] = []        # recent user/assistant turns, capped
    engine_hint: Literal["python"] | None = None   # analyst override; usually None
    model: str | None = None       # registry key; None -> per-task default
    row_limit: int = 5000
```

`QueryResponse`:

```python
class QueryResponse(BaseModel):
    request_id: str
    sql: str
    row_count: int
    rows_preview: list[dict]         # first N rows for the table pane
    chart: ChartArtifact | None      # plotly_json and/or file refs
    summary: str                     # short plain-language reading of the numbers
    engine: str
    model: str                       # which model ran plan_sql / plan_plot
    timings_ms: dict[str, int]       # per stage
    stages: list[Stage]
```

### Pipeline stages

```mermaid
flowchart TD
    classDef app fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef ai fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef viz fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    classDef db fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    classDef err fill:#b91c1c,stroke:#7f1d1d,stroke-width:2px,color:#fff

    Q(["question + analytics.* schema card + few-shot examples"]):::app
    P1["plan_sql<br/>Ollama qwen2.5-coder, structured SqlPlan"]:::ai
    G{"guard_sql<br/>one SELECT / WITH, analytics.* only,<br/>no DML/DDL/COPY/volatile fn, LIMIT enforced"}:::app
    RS["run_sql<br/>asyncpg as excise_ro, BEGIN READ ONLY,<br/>statement_timeout 10s, fetch, ROLLBACK"]:::db
    P2["plan_plot<br/>Ollama qwen2.5-coder, structured PlotPlan,<br/>engine must be in the live registry"]:::ai
    R["render<br/>engines/&lt;engine&gt;.py — script + data into scratch<br/>(Parquet, or a generated .m for Octave),<br/>run under bwrap, collect declared outputs"]:::viz
    S["summarize<br/>Ollama llama3.1, 2-4 sentence reading"]:::ai
    Out(["chart + table + SQL + summary + per-stage timings"]):::app
    Err["typed error<br/>(error, request_id, stage)"]:::err

    Q --> P1 --> G
    G -->|reject, reason to planner| P1
    G -->|rejected twice| Err
    G -->|ok — tables_used recorded| RS
    RS -->|DB error, reason to planner| P1
    RS -->|DB error twice| Err
    RS --> P2 --> R
    R -->|sandbox timeout / violation / no output| Err
    R --> S --> Out
```

1. **plan_sql** — prompt Ollama (`qwen2.5-coder:7b`) with the question, the
   `analytics.*` schema card, and few-shot examples; require an `SqlPlan`
   (`{sql: str, rationale: str, expected_columns: list[str]}`). Validate as
   structured output.
2. **guard_sql** — `sql/guard.py`: parse with `sqlglot`; reject unless the
   statement is exactly one `SELECT` or `WITH ... SELECT`; no `;`-joined
   statements; no DML/DDL/`COPY`/`CALL`/`DO`/`SET`/`GRANT`; no reference to
   anything outside schema `analytics`; enforce a `LIMIT` (inject
   `row_limit` if absent). A failure here is `SQL rejected` — one re-plan with
   the reason appended, then error.
3. **run_sql** — `sql/runner.py`: acquire from the read-only `asyncpg` pool,
   `BEGIN READ ONLY`, `SET LOCAL statement_timeout = '10s'`,
   `SET LOCAL idle_in_transaction_session_timeout = '15s'`, execute, fetch up
   to `row_limit`, rollback. `guard_sql` only proves the statement is a
   single read-only `SELECT` — it does not know whether the tables and
   columns it references exist, so a hallucinated table or an ambiguous cast
   only surfaces here, as a genuine Postgres error. One re-plan with the
   error message appended, then a second failure is `SQL error` with the
   Postgres message.
4. **plan_plot** — prompt Ollama with the result columns, dtypes, row count,
   and the question; require a `PlotPlan`
   (`{engine: str, script: str, outputs: list["plotly_json"|"png"|"svg"|"pdf"],
   title: str}`). `engine` must be in the live registry; default `python`.
5. **render** — `engines/<engine>.py` writes `script` + the result data into a
   fresh scratch dir (Parquet for Python, a generated `.m` variable file for
   Octave — it has no Parquet or table reader), runs it through
   `sandbox/bwrap.py`, collects the declared outputs. Missing output ->
   `render produced no output`. Timeout / namespace violation -> `sandbox
   timeout` /
   `sandbox violation`.
6. **summarize** — prompt Ollama (`llama3.1:8b`) for a 2–4 sentence reading of
   the numbers; plain text, `/general-english` tone rules apply on the Laravel
   side when displayed.

Each transition appends a `Stage{name, status, started_at, ms}` and is flushed
to the response stream so Laravel can relay it.

### Structured-output loop (`llm/client.py`)

```
for attempt in (1, 2):
    raw = await ollama.generate(model, prompt, format=Model.model_json_schema())
    try:
        return Model.model_validate_json(raw)
    except ValidationError as e:
        if attempt == 2:
            raise LLMStructuredOutputError(model=Model.__name__, errors=e.errors())
        prompt += f"\n\nThe previous reply failed validation:\n{e}\nReturn only valid JSON matching the schema."
```

- `format=` is Ollama's JSON-schema-constrained decoding — the model is forced
  toward valid shape, and Pydantic is the backstop.
- No third-party "agent framework" — not CrewAI, AutoGen, Semantic Kernel,
  LangGraph, or the like. The MCP client is: a schema, a `POST` to
  `/api/chat` or `/api/generate`, and this validation loop. Ollama's own
  tool-calling (`tools=[...]`) is used where a genuine multi-tool turn is
  needed; for the fixed SQL->plot->summarize sequence, direct structured calls
  are simpler and more predictable. Running more than one model is already the
  design (the roles below, the `config/models.php` registry); a framework to
  coordinate agents is a separate thing and is declined — `EVALUATION.md`
  §Right-sizing item 13 has the reasoning and the conditions to revisit.
- Model roles: `qwen2.5-coder:7b` for `plan_sql` and `plan_plot`,
  `llama3.1:8b` for `summarize`. Both pulled; `OLLAMA_MAX_LOADED_MODELS=1` so
  they swap — accept the reload cost at this concurrency (`EVALUATION.md` §2).

### Memory

Four stores, each a different span. Three are built; the fourth is a backlog
item.

| Store | Lives in | Span | Contents |
|---|---|---|---|
| Working set | orchestrator, in-process — `dict[conversation_id, deque[Turn]]` | one active conversation, evicted after 30 min idle | the last `CHAT_CONTEXT_TURNS` turns or ~2k tokens, whichever is smaller |
| Transcript | `web/` MariaDB — `conversations` / `messages` / `message_tool_calls` | permanent, per user | every turn and tool call; a conversation reloads and resumes from here, and Laravel resends the trimmed tail on each `/chat` call, so an orchestrator restart loses nothing that matters |
| Knowledge | Postgres `kb.*` | corpus-wide | UP Excise acts, rules, policies; FTS-retrieved per turn (`KB_RETRIEVE_K` chunks) when the question touches the law |
| Per-analyst memory (backlog) | `web/` MariaDB — `user_memory` | permanent, per user | short human-curated facts and defaults — a term glossary (`revenue = excise_duty + license_fee`), a home district, a default FY window — prepended to that user's chat system prompt |

```mermaid
flowchart TD
    classDef app fill:#059669,stroke:#047857,stroke-width:2px,color:#fff
    classDef db fill:#dc2626,stroke:#b91c1c,stroke-width:2px,color:#fff
    classDef ai fill:#7c3aed,stroke:#6d28d9,stroke-width:2px,color:#fff

    Turn["a chat turn<br/>user_id, conversation_id, message"]:::app

    subgraph Assemble["orchestrator assembles the prompt"]
        Recent["recent turns<br/>in-process deque — CHAT_CONTEXT_TURNS / ~2k tokens"]:::app
        Card["schema card<br/>analytics.* shape, static"]:::app
        KBhit["kb.chunks FTS hits<br/>KB_RETRIEVE_K, only when the turn needs the law"]:::app
    end

    Hist[("web/ MariaDB<br/>conversations / messages / message_tool_calls<br/>full transcript, resumable")]:::db
    KB[("Postgres kb.*<br/>acts, rules, policies — FTS")]:::db
    Prefs[("web/ MariaDB<br/>user_memory — per-analyst glossary + defaults<br/>human-curated, backlog")]:::db
    Model(("local model<br/>qwen2.5-coder / llama3.1")):::ai

    Hist -->|Laravel resends trimmed tail| Recent
    KB --> KBhit
    Prefs -. planned .-> Assemble
    Turn --> Assemble
    Recent --> Model
    Card --> Model
    KBhit --> Model
    Model -->|reply + tool calls| Hist
```

No vector store over past turns and no rolling-summary chain — the schema card
plus the recent tail is enough context here (`EVALUATION.md` §2). The
transcript is durable and resumable on its own; retrieval over it is added only
if real conversations start overflowing the working set.

Per-analyst memory is human-curated by design: the analyst adds, edits, and
forgets entries on a screen, and the model only reads it. Extracting "facts"
from a conversation and storing them for the model to trust later is the one
memory pattern this tool does not adopt — in a departmental analytics tool a
wrong fact that becomes memory is worse than no memory.

Agent-memory frameworks (Letta/MemGPT, Mem0, Zep, cognee) are declined for the
same reasons as the agent frameworks above: a server or a heavy dependency,
several with default outbound telemetry, built around autonomous self-editing
memory this tool should not have. `EVALUATION.md` §Right-sizing item 14.

### Config (`config.py`)

```
ORCH_BEARER_TOKEN           shared secret with Laravel (required)
DATABASE_URL_READONLY       postgres://excise_ro:...@127.0.0.1:5432/excise_bank
OLLAMA_BASE_URL             http://127.0.0.1:11434
OLLAMA_SQL_MODEL            qwen2.5-coder:7b-instruct-q4_K_M   (default for plan_sql / plan_plot)
OLLAMA_CHAT_MODEL           llama3.1:8b-instruct-q4_K_M         (default for chat / summarize)
OLLAMA_ALLOWED_MODELS       qwen2.5-coder:7b-instruct-q4_K_M,llama3.1:8b-instruct-q4_K_M
                            (registry the UI picker and the request `model` override are validated against)
OLLAMA_EMBED_MODEL          nomic-embed-text            (only used when embeddings enabled)
KB_EMBEDDINGS_ENABLED       false                       (FTS-only until flipped)
KB_EMBED_DIM               768
KB_RETRIEVE_K              6                            (chunks injected per turn)
CHAT_MAX_TOOL_CALLS        4                            (per turn, then end with error)
CHAT_CONTEXT_TURNS         8
SANDBOX_USER                excise-sandbox
SANDBOX_SCRATCH_ROOT        /var/tmp/excise-charts        (per-run subdir, cleaned)
SANDBOX_WALLCLOCK_SECONDS   15
SANDBOX_MEMORY_MB           1024
QUERY_ROW_LIMIT_DEFAULT     5000
STATEMENT_TIMEOUT           10s
```

## Chat and retrieval

`/chat` runs a free-form conversation with the local model. Where `/query` is a
fixed SQL->plot->summarize pipeline, `/chat` lets the model choose tools turn
by turn. Same primitives underneath — the SQL guard, the read-only runner, the
sandbox, the engine registry — no parallel implementation.

### `ChatRequest`

```python
class ChatRequest(BaseModel):
    conversation_id: str            # ULID from Laravel
    message: str
    history: list[ChatTurn] = []    # prior user/assistant/tool turns, capped by Laravel
    model: str | None = None        # registry key from the chat model picker; None -> chat default
```

`model` is a key from the model registry (`config.py`), not a free-form Ollama
tag. An unknown key is rejected before any Ollama call. The registry is the
same idea as `~/Sites/pdf-markdown-pipeline`'s `config/ocr.php`: `key`,
`label`, `role` (`sql` / `chat` / `embed`), Ollama tag. The Livewire picker
offers only registry entries with `role: chat` that `/health` also reports as
pulled — the coder model that plans SQL and plot scripts is never a
conversational choice, regardless of what `/health` reports for it.

### Streamed events

One JSON object per line (`application/x-ndjson`, the same wire format
`/query` already streams — not `text/event-stream`; `web/plan/webui.md` §9
has the reasoning): `token` (assistant text delta), `tool_call` (`{name,
arguments}` as the model emits it), `tool_result` (`{name, ok, summary}` —
never the full row set), `chart` (`{plotly_json?, files}` when `make_chart`
ran), `done` (`{message_id, tool_calls_count}`), `error` (`{stage,
message}`). Laravel pipes these lines to the browser unmodified and persists
`messages` + `message_tool_calls` as they arrive.

### Tools (`chat/tools.py`)

| Tool | Arguments | Does | Guardrails |
|---|---|---|---|
| `search_knowledge` | `{query: str, k?: int \| null}` | Retrieves from `kb.chunks` (§Retrieval), returns chunk text + `heading_path` + `source_url` | read-only; `withdrawn_at IS NULL`; `k` capped at 12, defaults to 6 on `null` |
| `run_sql_query` | `{question: str}` | Plans SQL like `/query`'s `plan_sql`, always — no raw-`sql` argument, so the chat model (which never sees the schema) can't hand-write a query against a table it invented; then `guard.py` -> `runner.py` (READ ONLY txn, statement timeout, row cap); returns column list + row count + a small preview | identical guard + read-only role as the one-shot path; no writes possible; a rejected or failing statement comes back as a failed tool result (see below), not a turn-ending exception |
| `make_chart` | `{spec: str}` | Runs a generated Python plot script over the last `run_sql_query` result in the `bwrap` sandbox; returns artifact refs | same sandbox, same caps; the DataFrame is looked up by the request's own `conversation_id`, a trusted value the model never supplies and is never shown — an earlier `data_ref` argument asked the model to restate that id as a match check, which no real call could ever pass |

Ollama's native tool-calling (`tools=[...]` on `/api/chat`) drives this;
Qwen 2.5 and Llama 3.1 both support it. A live chat turn on a plain greeting
surfaced Llama narrating its own tool-call decision as if it were the reply
— "No tool call is needed as it's a greeting..." streamed to the user token
by token, since every `content` delta the model emits is streamed as-is
with nothing held back. `CHAT_SYSTEM_PROMPT` now tells the model directly
not to narrate that decision: call a tool silently or write the answer
itself, nothing else. A second, related failure surfaced the same way:
attaching `CHAT_TOOL_SCHEMAS` at all sometimes makes Llama answer a trivial
message with a bare `"{}"` instead of prose or a real tool call — confirmed
directly against Ollama, since the identical prompt with no `tools=`
answers normally. `chat/loop.py` holds back a reply that is nothing but
braces/whitespace instead of streaming it, and on a turn that made no tool
call and produced only that, retries once with `tools=[]`.

A tool call that fails — a rejected or erroring `run_sql_query` statement, a
`make_chart` script the sandbox rejects — comes back as a failed tool result
(`{name, ok: false, summary}`), not a raised exception that would end the
turn. The model sees why its call failed and can call the tool again with a
correction, inside its own `CHAT_MAX_TOOL_CALLS` budget — the same recovery
`/query`'s `guard_sql` and `run_sql` retries give the one-shot pipeline,
adapted to the chat loop's own turn-taking instead of a fixed one-shot retry.

A malformed tool call gets the same treatment. `dispatch()` raises
`ChatToolArgumentError` when a call's arguments fail their Pydantic schema —
this used to propagate out of `run_chat()` uncaught, ending the turn
silently. It is caught around the `dispatch()` call and returned as a failed
tool result instead, the same shape as a rejected SQL statement above.
`search_knowledge`'s `k` argument needed a schema fix on top of that:
Llama's tool-calling fills in every schema property rather than omitting the
ones it means to leave unset, sending an explicit `k: null` — a plain
`int = 6` rejects that, since a default only applies when the key is
absent, not when it is `null`; `k` is `int | None` now.

A live turn also showed Llama narrate a *second* tool call as plain text
instead of a real `tool_calls` entry: after an earlier `run_sql_query` call
failed, it answered with the literal string `run_sql_query(question="...")`
as if that were its reply, leaving the user with a failed-query card and no
actual answer. The same bare-`{}` check above now also holds back any reply
that is a prefix of one of the three tool names, on the reasoning that both
are the tool-calling template breaking down the same way, so both get the
same one-retry-with-`tools=[]` recovery.

A live turn surfaced a fourth shape of the same underlying weakness: after a
real `run_sql_query` call succeeded, the follow-up turn produced no content
at all — not a bare `"{}"`, genuinely empty — on both the tool-aware attempt
and the `tools=[]` retry, leaving the user with a tool call card and nothing
else, no answer and no `make_chart` call either. `CHAT_SYSTEM_PROMPT` already
asks the model never to let a tool result be the last thing in the turn, but
an 8B model cannot be relied on to follow that every time. `run_chat` now
keeps the most recent tool result and, if both attempts still come back
degenerate, surfaces that result's own summary as the turn's answer instead
of ending on nothing.

A fifth shape mixed a real tool call with hallucinated content: asked a
two-metric question (revenue and volume together), Llama wrote its own
guessed SQL against a table that doesn't exist, in a fenced code block
introduced by "let me try running the following query" — skipping
`run_sql_query` even though `CHAT_SYSTEM_PROMPT` already said never to
invent a table or column name. `CHAT_SYSTEM_PROMPT` now names the narrated
SQL itself, not just the decision to call a tool, and once a completed
turn's text contains a fenced ```sql block and made no tool call,
`chat/loop.py` retries it once, the same as a bare `"{}"` or a narrated fake
call, rather than showing it to the user as a final answer against a table
that was never real.

Unlike those two, a fenced sql block can't be told apart from ordinary prose
until most of it has already streamed, so this check runs only once the
turn's full text is in — it does not hold the live stream back the way the
bare-`"{}"`/narrated-call checks do. An earlier version of this fix withheld
the guessed SQL from the stream entirely while it decided whether to retry,
and that broke a real turn: the connection sent nothing for the whole length
of that generation plus the retry, long enough that the browser dropped it
as interrupted before the correction ever arrived. The guessed SQL now
streams live and the correction follows right after it — a moment of a
wrong-looking answer costs less than the connection itself.

Past the model's own tool-calling reliability, two gaps sat on the
orchestrator's own side of the contract, both in `make_chart` specifically.
`MakeChartArgs` used to also require `data_ref`, checked against
`conversation_id` — but the model is never told that id anywhere, not in
`CHAT_SYSTEM_PROMPT`, not in the message history, so no real call could ever
supply the one value that would pass; every `make_chart` call failed on this
before it ever reached the sandbox. The lookup was already scoped by the
trusted `conversation_id` `dispatch()` receives from the request itself, so
the check guarded nothing a wrong `data_ref` could actually have exploited.
`data_ref` is gone; `make_chart` takes only `spec`. Separately, `/query`'s
`plan_plot` stage hands the planning model an explicit capability string per
engine (`llm/prompts.py`'s `_ENGINE_CAPABILITIES`: `df` is already loaded,
the exact `fig.write_json(...)` call, the forbidden `fig.write_image()`)
before it writes a line of script. `make_chart`'s tool description said only
"chart the most recent result," leaving the model to guess the sandbox's
variable names and output convention blind. The description now states the
same contract `plan_plot` gets, scoped to what chat's fixed
`outputs=["plotly_json"]` actually collects: a matplotlib `plt.savefig()`
script is a valid choice for `/query`, which picks its own `outputs`, but
produces nothing `make_chart` reads — the description says so explicitly, so
that path never looks like a silent option.

The loop:

```
messages = system + history + [user message]
for step in range(CHAT_MAX_TOOL_CALLS + 1):
    stream a model turn                      # emit `token` events as text arrives
    if the turn made no tool call:
        emit `done`; return
    for call in tool_calls:
        emit `tool_call`
        result = dispatch(call)              # guarded exactly as above
        emit `tool_result` (+ `chart` if make_chart)
        append result to messages
# fell through the cap:
emit `error` {stage: "tool_loop", message: "too many tool calls"}
```

```mermaid
sequenceDiagram
    participant B as Browser
    participant L as web/ (Laravel relay)
    participant O as orchestrator /chat
    participant M as Ollama (chat model)
    participant T as tools - run_sql_query, search_knowledge, make_chart

    B->>L: message
    L->>O: POST /chat — bearer, capped history, model key
    O->>O: reject the model key if it is not in the registry
    loop up to CHAT_MAX_TOOL_CALLS
        O->>M: stream a model turn
        M-->>O: token deltas
        O-->>L: ndjson line: {"token": ...}
        L-->>B: append assistant text
        alt the turn made a tool call
            O-->>L: ndjson line: {"tool_call": ...}
            O->>T: dispatch — same guard + read-only role + sandbox
            T-->>O: result (preview only, never the full row set)
            O-->>L: ndjson line: {"tool_result": ...} (+ {"chart": ...} if make_chart)
            O->>M: append the tool result and continue
        else no tool call
            O-->>L: ndjson line: {"done": ...}
        end
    end
    Note over O: cap exceeded -> ndjson line: {"error": {stage: tool_loop}}
    L->>L: persist messages + message_tool_calls
```

A client disconnect cancels the in-flight Ollama stream and any running tool.

### Routing (knowledge / data / hybrid / general)

There is no separate classifier. The system prompt describes the three tools
and when each applies; the model calls what it needs:

- "What does the 2016 excise policy say about MGQ?" -> `search_knowledge` only.
- "Revenue trend for Lucknow since FY2018-19" -> `run_sql_query` (+ maybe
  `make_chart`).
- "How does actual Lucknow revenue compare to what the 2019 policy targeted?"
  -> `search_knowledge` for the target, `run_sql_query` for the actuals, then
  a text answer tying them together.
- "Explain what MGQ means" -> neither tool, a plain answer.

This is the same "explicit selection over a heuristic" choice as the engine
router (`EVALUATION.md` §Right-sizing point 3).

### Retrieval (`kb/retrieve.py`)

Default path, no embeddings:

```sql
SELECT c.content, c.heading_path, d.title, d.source_url, d.doc_type,
       ts_rank(c.fts, websearch_to_tsquery('simple', $1)) AS rank
FROM kb.chunks c
JOIN kb.documents d ON d.id = c.document_id
WHERE d.withdrawn_at IS NULL
  AND c.fts @@ websearch_to_tsquery('simple', $1)
ORDER BY rank DESC
LIMIT $2;                                    -- KB_RETRIEVE_K
```

With `KB_EMBEDDINGS_ENABLED`: also embed the query via `kb/embed.py`
(local Ollama embed model), run an HNSW cosine search on `kb.chunks.embedding`,
merge the two result sets, de-duplicate by `chunk.id`, keep the top
`KB_RETRIEVE_K` by a blended score. Everything stays on the box.

Retrieved chunks go into the model context as a labelled block with the
`heading_path` and `source_url` for each, and the system prompt instructs the
model to cite the section and link when it uses one. An empty retrieval
returns nothing and the model is told to say it has no source rather than
guess.

### Conversation memory (chat)

Same as `/query`: an in-memory `deque` per `conversation_id`, capped at
`CHAT_CONTEXT_TURNS` or ~3k tokens. Laravel also resends trimmed history and
owns the durable record (`conversations` / `messages` / `message_tool_calls`
in its MariaDB). An orchestrator restart loses only the in-memory window.
A new conversation's `title` (shown in the conversation rail and the browser
tab) is the Laravel side's own concern — `Chat::send()` sets it from the
first message, truncated to 60 characters, entirely independent of the
orchestrator.

### Model roles, restated

`qwen2.5-coder:7b` for `run_sql_query` planning and `make_chart` scripting;
`llama3.1:8b` for the conversational turns and `summarize`. `nomic-embed-text`
only if embeddings are enabled. `OLLAMA_MAX_LOADED_MODELS=1` still holds — the
chat model and the coder model swap between a tool call and the reply. At this
concurrency the reload cost is acceptable; if it is not, raise it to 2 and
accept ~13 GB resident (`EVALUATION.md` §2 has the headroom math).

That mapping is the default. A `model` on `ChatRequest` / `QueryRequest`
(from the chat picker or the one-shot form's advanced control) overrides it
for that turn, provided the key is in `OLLAMA_ALLOWED_MODELS`. `run_sql_query`
planning inside a chat still uses the coder model regardless of the chat
picker — the picker changes the conversational model, not the SQL planner.

## `IVisualizationEngine` — the adapter interface

One `Protocol`, a registry, and typed errors. Adding an engine is one class and
one registry line; nothing else in the pipeline changes.

```python
# engines/base.py
from typing import Protocol, runtime_checkable
from pathlib import Path
from pydantic import BaseModel


class RenderRequest(BaseModel):
    script: str                       # LLM-generated, already schema-validated
    data_path: Path                   # Parquet of the SQL result, inside the scratch dir
    outputs: list[str]                # subset of {"plotly_json", "png", "svg", "pdf"}
    title: str
    scratch_dir: Path                 # the only writable path in the sandbox


class RenderResult(BaseModel):
    plotly_json: str | None = None
    files: dict[str, Path] = {}        # "png" -> path, etc., all under scratch_dir
    stdout_tail: str = ""
    engine: str


@runtime_checkable
class IVisualizationEngine(Protocol):
    name: str
    supported_outputs: frozenset[str]

    def is_available(self) -> bool:
        """Cheap check: binary on PATH, licence reachable, import works.
        Called at startup and surfaced on /health."""

    async def render(self, req: RenderRequest) -> RenderResult:
        """Write `script` into `scratch_dir`, execute it under the sandbox
        (sandbox/bwrap.py), collect `outputs`. Raise EngineUnavailable,
        SandboxTimeout, SandboxViolation, or RenderEmpty."""


# engines/base.py — registry
_ENGINES: dict[str, IVisualizationEngine] = {}

def register(engine: IVisualizationEngine) -> None:
    _ENGINES[engine.name] = engine

def get(name: str) -> IVisualizationEngine:
    try:
        eng = _ENGINES[name]
    except KeyError:
        raise EngineUnavailable(name, reason="not registered")
    if not eng.is_available():
        raise EngineUnavailable(name, reason="unavailable at runtime")
    return eng

def available() -> list[str]:
    return [n for n, e in _ENGINES.items() if e.is_available()]
```

Contract every engine keeps:

- **Input is untrusted.** `script` came from the LLM. The engine never `eval`s
  it in-process — it writes a file and executes it in the sandbox subprocess.
- **Output stays in `scratch_dir`.** Any file outside it is dropped and logged
  as a violation.
- **No network, no host writes.** Enforced by the sandbox, not by the engine
  trusting the script.
- **`is_available()` is cheap and honest.** `/health` shows the live list; the
  router refuses an unavailable engine with a clear message rather than
  failing mid-render.
- **Deterministic output names.** `chart.png`, `chart.svg`, `chart.pdf`,
  `chart.plotly.json` in `scratch_dir`.

## Engine integration guides

### 1. Python (Matplotlib / Plotly) — `python_engine.py` — implemented

- **Availability**: `import matplotlib, plotly, pandas, numpy` succeeds in
  `orchestrator/.venv`. Always true once installed; `is_available()` still
  checks so a broken venv shows on `/health`.
- **Execution**: the sandbox runs `orchestrator/.venv/bin/python
  /scratch/chart.py` with `MPLBACKEND=Agg`, `HOME=/scratch`,
  `MPLCONFIGDIR=/scratch/.mpl`, no `$DISPLAY`.
- **Script harness**: the engine prepends a fixed preamble the LLM does not
  write —

  ```python
  import pandas as pd, json, sys
  df = pd.read_parquet("/scratch/data.parquet")
  OUT = "/scratch"
  # --- LLM script body uses `df`, writes chart.* into OUT ---
  ```

  and appends nothing. The LLM is instructed: use `df`; for an interactive
  chart build a Plotly figure and `fig.write_json(f"{OUT}/chart.plotly.json")`;
  for a static chart built with matplotlib directly, use `plt.savefig(...)`;
  never call a Plotly figure's own `fig.write_image()`; do not read other
  files, do not call the network.
- **Outputs**: `plotly_json` for the interactive pane; `png` (2x DPI), `svg`,
  `pdf` for the export buttons — via `plt.savefig(...)` for a matplotlib
  script, or derived automatically from `chart.plotly.json` for a Plotly one
  (below).
- **Static export and `kaleido`, resolved**: this doc originally assumed
  `kaleido` was "pure binary, no browser" — true of `kaleido<1.0`, not of
  `kaleido==1.4.0` (the pinned version, `requirements.txt`), which drives a
  real system Chrome over the DevTools protocol instead. Calling
  `fig.write_image()` *inside the per-script sandbox* launched a fresh
  Chrome per chart and repeatedly OOM-killed the render's cgroup instead of
  erroring, so `llm/prompts.py` no longer offers it to the model, and
  `python_engine.py` rejects a script that calls it anyway before a
  sandboxed process runs (`SandboxViolationError`). Once the sandboxed
  script produces `chart.plotly.json`, `render()` hands that JSON to
  `engines/static_render.py` — a *persistent* browser, started once at
  orchestrator boot and reused for every chart, running entirely outside
  the sandbox. This step never executes LLM-authored code, only rasterizes
  an already-produced, schema-shaped JSON spec, so the untrusted-code
  sandbox boundary is a deliberate non-fit here, not a gap in it.
  `SECURITY.md` §Static image export has the isolation detail — a fresh
  browser profile per launch either way, and an open-source Chromium binary
  preferred over the box's Chrome when the operator installs one
  (`OPERATOR_SETUP.md` §Chart rendering).
- **Libraries in the venv**: `pandas`, `numpy`, `scipy`, `matplotlib`,
  `seaborn`, `plotly`, `kaleido`, `pyarrow`. Nothing else reachable from the
  sandbox. `fig.write_json()`'s interactive export is pure-Python
  serialization and doesn't touch `kaleido`/Chrome at all — only
  `static_render.py`, outside the sandbox, does.
- **Failure modes**: import error in the body -> `RenderEmpty` with
  `stdout_tail`; wall-clock -> `SandboxTimeout`; `MemoryError` / OOM-kill ->
  `SandboxViolation` (rlimit); no `chart.*` produced -> `RenderEmpty`.

### 2. GNU Octave — `octave_engine.py` — implemented

[octave.org](https://octave.org) — open-source, MATLAB-compatible `.m` syntax.

- **Availability**: `octave-cli --version` exits 0 (`OPERATOR_SETUP.md`
  §Octave installs it). `is_available()` returns false without it, and the
  router simply never offers it.
- **Execution**: sandbox runs `octave-cli --no-gui --norc --eval
  "source('/scratch/chart.m')"` with `HOME=/scratch` and `LANG=C.utf8` —
  `bwrap`'s `--clearenv` drops locale along with everything else, and
  Ghostscript's iconv step (see below) fails outright without one.
- **Data hand-off**: GNU Octave has no `table` type and does not implement
  `readtable` — it names that MATLAB function outright as not yet
  implemented, and the `octave-io` package doesn't add it either, only
  spreadsheet I/O. The engine writes the query result as a generated `.m`
  file instead (`/scratch/data.m`, alongside the Parquet the Python engine
  uses): each column becomes a plain Octave variable, a numeric column
  vector or a cell array of strings, named after its SQL column alias. The
  Octave preamble does `source('/scratch/data.m');`.
- **Figure setup**: a new `figure()` does not inherit the
  `graphics_toolkit("gnuplot")` global default — it silently falls back to
  `fltk`, which needs a real display and fails `print()` with "requires
  visible figure" in the sandbox's headless namespace. The preamble creates
  the one figure the script draws into and sets `__graphics_toolkit__` on
  that figure object directly, so the LLM-written body only calls a plotting
  function (`plot`/`bar`/...) and never creates its own figure.
- **Outputs**: Octave's `print()` to `chart.png` / `chart.svg` / `chart.pdf`,
  using gnuplot's own cairo terminals — `-dpngcairo`, `-dsvg`, `-dpdfcairo`.
  `-dpng` and `-dpdf` route through Ghostscript in Octave's gnuplot toolkit,
  and that Ghostscript step fails inside the sandbox namespace with a plain
  `EPERM` on its own output file (not a bwrap bind-mount gap — plain file
  writes and gnuplot's own terminals both work in the same sandbox); the
  cairo terminals write the file directly and never reach Ghostscript. No
  interactive JSON — `supported_outputs = {"png", "svg", "pdf"}`; the
  pipeline falls back to a static chart when the chosen engine can't do
  Plotly JSON.

### 3. MATLAB via `matlab-mcp-server` — Milestone 4, behind a config flag,
     currently blocked

[mathworks.com/products/matlab](https://in.mathworks.com/products/matlab.html) —
proprietary, per-seat licence. [Open-source alternatives to
MATLAB](https://opensource.com/alternatives/matlab) (Octave, NumPy/SciPy) cover
this project's needs.

- **Prerequisites, none of which the box has**: MATLAB R2021a+ installed and
  on `PATH`; a valid MATLAB licence; the Go toolchain (or a downloaded release
  binary). The server's licence terms forbid sharing an MCP server across
  multiple users — a multi-user dashboard does not fit that.
- **Shape if it is ever added**: `matlab_engine.py` is an MCP-client adapter,
  not a subprocess-script adapter. It spawns `matlab-mcp-server
  --matlab-session-mode=new` as a stdio MCP child, calls its `run`/`eval`
  tool with the generated MATLAB, and pulls back a saved figure
  (`saveas(gcf, '/scratch/chart.png')` inside the MATLAB code). The stdio
  child still runs inside the sandbox wrapper for filesystem and network
  confinement; MATLAB's own compute limits (workers, `maxNumCompThreads`) are
  set in a startup script.
- **Session modes**: `new` (fresh MATLAB per render — safest, slowest),
  `auto` (reuse if a shared session exists), `existing` (attach only, needs
  `shareMATLABSession()` + `--setup-matlab`). If this is ever used here, `new`
  is the only safe choice — a shared session leaks state between analysts'
  queries.
- **Recommendation**: do not build this adapter until there is a concrete
  toolbox requirement (e.g. a specific MATLAB statistics/optimization routine
  with no SciPy equivalent) and a licence that permits the deployment.
  `EVALUATION.md` §Right-sizing.

### 4. Wolfram Mathematica (`wolframscript`) — Milestone 4, behind a config
     flag, currently blocked

[wolfram.com/mathematica](https://www.wolfram.com/mathematica/) — proprietary;
its value here would be symbolic math, not charting.

- **Prerequisites**: Wolfram Engine (free for non-production developer use) or
  a Mathematica licence, providing `wolframscript`. **Not installed.**
- **Shape**: `wolfram_engine.py` writes `/scratch/chart.wls`, the sandbox runs
  `wolframscript -file /scratch/chart.wls`, the script does
  `Export["/scratch/chart.pdf", plot]` / `.png` / `.svg`.
  `supported_outputs = {"png", "svg", "pdf"}`.
- **Where it would earn its place**: symbolic math, exact arithmetic, special
  functions — none of which excise revenue/dispatch/enforcement analytics
  needs. Duty-rate elasticity or high-precision projection work could justify
  it later.
- **Recommendation**: out of scope until a symbolic/high-precision requirement
  is named.

## Routing

`plan_plot` returns `engine`. The router:

1. If `QueryRequest.engine_hint` is set (analyst override), use it.
2. Else use the LLM's `engine` if it is in `available()`.
3. Else fall back to `"python"`.

No heuristic on data volume or "task complexity". The LLM is given a one-line
capability list per engine actually in the live registry (`python`:
interactive + static, all output types; `octave`: static only, no
`table`/`readtable`, gnuplot's cairo print devices) and picks —
`llm/prompts.py`'s `build_plot_prompt`. A future engine only adds one more
line the same way; the routing logic itself doesn't change.
`EVALUATION.md` §Right-sizing point 3.
