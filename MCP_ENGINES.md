# MCP_ENGINES.md — orchestrator and visualization engines

## The orchestrator (`orchestrator/`)

Python 3.12 + FastAPI + uvicorn, bound to `127.0.0.1:8085`, started by a
systemd `--user` unit. It is the MCP **client** (to Ollama's tool interface),
the SQL generator, and the engine router. It holds no long-term state beyond
in-memory conversation windows keyed by the ULID Laravel sends; durable
history is the Laravel ledger.

### Module layout

```
orchestrator/
  app/
    main.py            FastAPI app, lifespan (asyncpg pool, httpx client, ollama warmup)
    config.py          pydantic-settings Settings (one object)
    auth.py            bearer-token dependency
    schemas.py         Pydantic v2: QueryRequest/Response, SqlPlan, PlotPlan, Stage,
                       ChatRequest, chat SSE events, tool schemas, errors
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
      loop.py          agentic tool-calling loop, streams SSE events
      tools.py         tool defs: run_sql_query, search_knowledge, make_chart
    engines/
      base.py          IVisualizationEngine protocol + registry + errors
      python_engine.py the one implemented engine
      octave_engine.py Milestone 4
    sandbox/
      bwrap.py         build + run the bubblewrap command, collect artifacts
    pipeline.py        the one-shot analytical flow: orchestrates stages, emits Stage events
  tests/
  requirements.txt / requirements.lock
```

### HTTP surface

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/health` | — | `{status, ollama, postgres, engines, kb_docs, embeddings}` — no auth |
| `POST` | `/query` | `QueryRequest` | streamed `Stage` lines then a final `QueryResponse` (chunked), or a typed error |
| `GET` | `/query/{id}/status` | — | last `Stage` for a running query (poll fallback) |
| `POST` | `/chat` | `ChatRequest` | `text/event-stream` — `token` / `tool_call` / `tool_result` / `chart` / `done` / `error` events |
| `POST` | `/kb/search` | `{query: str, k: int}` | `{chunks: [...]}` — retrieval only, no LLM (used by tests and the "cite sources" panel) |

Both `/query` and `/chat` require the bearer token. `/query` is the one-shot
analytical form (question in, chart + table + SQL + summary out). `/chat` is
the free-form conversation where the model decides which tools to call.

`QueryRequest`:

```python
class QueryRequest(BaseModel):
    conversation_id: str            # ULID from Laravel
    question: str
    history: list[Turn] = []        # recent user/assistant turns, capped
    engine_hint: Literal["python"] | None = None   # analyst override; usually None
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
    timings_ms: dict[str, int]       # per stage
    stages: list[Stage]
```

### Pipeline stages

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
   to `row_limit`, rollback. DB errors surface as `SQL error` with the
   Postgres message.
4. **plan_plot** — prompt Ollama with the result columns, dtypes, row count,
   and the question; require a `PlotPlan`
   (`{engine: str, script: str, outputs: list["plotly_json"|"png"|"svg"|"pdf"],
   title: str}`). `engine` must be in the live registry; default `python`.
5. **render** — `engines/<engine>.py` writes `script` + the result data
   (Parquet) into a fresh scratch dir, runs it through `sandbox/bwrap.py`,
   collects the declared outputs. Missing output -> `render produced no
   output`. Timeout / namespace violation -> `sandbox timeout` /
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
- No third-party "agent framework". The MCP client is: a schema, a `POST` to
  `/api/chat` or `/api/generate`, and this validation loop. Ollama's own
  tool-calling (`tools=[...]`) is used where a genuine multi-tool turn is
  needed; for the fixed SQL->plot->summarize sequence, direct structured calls
  are simpler and more predictable.
- Model roles: `qwen2.5-coder:7b` for `plan_sql` and `plan_plot`,
  `llama3.1:8b` for `summarize`. Both pulled; `OLLAMA_MAX_LOADED_MODELS=1` so
  they swap — accept the reload cost at this concurrency (`EVALUATION.md` §2).

### Conversation memory

In-memory `dict[conversation_id, deque[Turn]]`, capped at the last 6 turns or
~2k tokens, whichever is smaller. Evicted after 30 min idle. Laravel resends
the trimmed history on each call as well, so an orchestrator restart loses
nothing that matters. No vector store, no summary chain — the schema card plus
a few recent turns is enough context for this task.

### Config (`config.py`)

```
ORCH_BEARER_TOKEN           shared secret with Laravel (required)
DATABASE_URL_READONLY       postgres://excise_ro:...@127.0.0.1:5432/excise_bank
OLLAMA_BASE_URL             http://127.0.0.1:11434
OLLAMA_SQL_MODEL            qwen2.5-coder:7b-instruct-q4_K_M
OLLAMA_CHAT_MODEL           llama3.1:8b-instruct-q4_K_M
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
```

### SSE events

`token` (assistant text delta), `tool_call` (`{name, arguments}` as the model
emits it), `tool_result` (`{name, ok, summary}` — never the full row set),
`chart` (`{plotly_json?, files}` when `make_chart` ran), `done`
(`{message_id, tool_calls_count}`), `error` (`{stage, message}`). Laravel
relays these to the browser and persists `messages` + `message_tool_calls`.

### Tools (`chat/tools.py`)

| Tool | Arguments | Does | Guardrails |
|---|---|---|---|
| `search_knowledge` | `{query: str, k?: int}` | Retrieves from `kb.chunks` (§Retrieval), returns chunk text + `heading_path` + `source_url` | read-only; `withdrawn_at IS NULL`; `k` capped at 12 |
| `run_sql_query` | `{sql: str}` or `{question: str}` | If `question`, first plan SQL like `/query`'s `plan_sql`; then `guard.py` -> `runner.py` (READ ONLY txn, statement timeout, row cap); returns column list + row count + a small preview | identical guard + read-only role as the one-shot path; no writes possible |
| `make_chart` | `{spec: str, data_ref: str}` | Runs a generated Python plot script over the last `run_sql_query` result in the `bwrap` sandbox; returns artifact refs | same sandbox, same caps; `data_ref` must point at a result from this conversation |

Ollama's native tool-calling (`tools=[...]` on `/api/chat`) drives this;
Qwen 2.5 and Llama 3.1 both support it. The loop:

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

### Model roles, restated

`qwen2.5-coder:7b` for `run_sql_query` planning and `make_chart` scripting;
`llama3.1:8b` for the conversational turns and `summarize`. `nomic-embed-text`
only if embeddings are enabled. `OLLAMA_MAX_LOADED_MODELS=1` still holds — the
chat model and the coder model swap between a tool call and the reply. At this
concurrency the reload cost is acceptable; if it is not, raise it to 2 and
accept ~13 GB resident (`EVALUATION.md` §2 has the headroom math).

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
  for static output `fig.write_image(...)` (Plotly+kaleido) or
  `plt.savefig(...)`; do not read other files, do not call the network.
- **Outputs**: `plotly_json` for the interactive pane; `png` (2x DPI), `svg`,
  `pdf` for the export buttons. Plotly static export needs `kaleido` (pure
  binary, no browser) — pin it.
- **Libraries in the venv**: `pandas`, `numpy`, `scipy`, `matplotlib`,
  `seaborn`, `plotly`, `kaleido`, `pyarrow`. Nothing else reachable from the
  sandbox.
- **Failure modes**: import error in the body -> `RenderEmpty` with
  `stdout_tail`; wall-clock -> `SandboxTimeout`; `MemoryError` / OOM-kill ->
  `SandboxViolation` (rlimit); no `chart.*` produced -> `RenderEmpty`.

### 2. GNU Octave — `octave_engine.py` — Milestone 4, only if needed

[octave.org](https://octave.org) — open-source, MATLAB-compatible `.m` syntax.

- **Availability**: `octave-cli --version` exits 0. **Not installed on the box
  now** — needs `sudo apt install octave` (root; give the command, do not work
  around). `is_available()` returns false until then, and the router simply
  never offers it.
- **Execution**: sandbox runs `octave-cli --no-gui --norc --eval
  "source('/scratch/chart.m')"` with `HOME=/scratch`.
- **Data hand-off**: the engine writes the result as CSV (`/scratch/data.csv`)
  alongside Parquet; the Octave preamble does `T = readtable('/scratch/data.csv');`.
- **Outputs**: Octave's `print()` to `chart.png` / `chart.svg` / `chart.pdf`
  via the `gnuplot` or `qt` toolkit (`qt` needs no X with
  `graphics_toolkit("gnuplot")` — use gnuplot headless). No interactive JSON —
  `supported_outputs = {"png", "svg", "pdf"}`; the pipeline falls back to a
  static chart when the chosen engine can't do Plotly JSON.
- **When to add it**: a real `.m` analysis script arrives that is not
  trivially portable to NumPy/SciPy. Until then it is a false choice for the
  LLM and stays unregistered.

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

No heuristic on data volume or "task complexity". The LLM is given the
one-line capability list (`python`: interactive + static, all output types)
and picks; with one engine registered the pick is always `python`. When Octave
is added, the prompt gains one line and the same mechanism handles it.
`EVALUATION.md` §Right-sizing point 3.
