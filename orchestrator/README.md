# orchestrator/

Python 3.12 FastAPI service: the one-shot analytical pipeline (`/query`), the
bounded chat tool loop (`/chat`), the MCP client to Ollama, knowledge-base
retrieval, the SQL guard, the sandbox launcher, and the engine router.
`127.0.0.1:8085` only, never tunneled. `MCP_ENGINES.md` covers the full
design; this is the package layout.

```
orchestrator/
  app/
    main.py            FastAPI app, lifespan, /health, /query, /chat, /kb/search, /kb/documents
    config.py           Settings (pydantic-settings) — MCP_ENGINES.md §Config
    auth.py              bearer-token dependency
    schemas.py           request/response models, tool-call models, typed errors
    pipeline.py           the six /query stages: plan_sql -> guard_sql -> run_sql -> plan_plot -> render -> summarize
    chat/
      loop.py              the bounded /chat tool loop (run_chat)
      tools.py             search_knowledge / run_sql_query / make_chart dispatch
      prompts.py           the chat system prompt + Ollama tool schemas
    llm/
      client.py           Ollama async client — structured-output retry loop, streaming chat
      prompts.py          system prompts, the schema-card slot, few-shot NL->SQL examples
    kb/
      retrieve.py          Postgres FTS retrieval + the admin "browse the corpus" listing
    sql/
      schema_card.py       renders analytics.* into the prompt schema card
      guard.py              single-read-only-SELECT parser (sqlglot) + reject list
      runner.py             asyncpg pool on excise_ro, READ ONLY txn, statement timeout
    engines/
      base.py               IVisualizationEngine protocol + registry
      python_engine.py       Matplotlib / Plotly / pandas
      octave_engine.py        GNU Octave, same bwrap sandbox
      static_render.py        the persistent, sandbox-external browser for static chart export
      matlab_engine.py / wolfram_engine.py   documented, unconfigured stubs
    sandbox/
      bwrap.py               builds + runs the bwrap sandbox command
  tests/
```

## Status

Milestones 2-4 are done, and Milestone 5's chat endpoint (Phase 2) is built
alongside them: `ruff` / `ruff format --check` / `mypy --strict` green, 70
tests passing — against the real `bwrap` + `systemd-run` on this box, a real
`/query` end-to-end against the live `excise_bank`, a real Octave render, and
a real headless-browser render for static chart export.

Static chart export (`chart.png`/`svg`/`pdf`) is resolved. Plotly's own
`fig.write_image()` needs a real browser (`kaleido>=1.0`); calling it *inside*
the per-script sandbox launched a fresh Chrome per chart and repeatedly
OOM-killed the render's cgroup instead of erroring. `python_engine.py`
rejects a script that calls it, and `engines/static_render.py` derives any
requested static format from the script's `chart.plotly.json` afterward,
using one persistent browser kept running for the orchestrator's whole
lifetime — it never executes model-authored code, so it doesn't need the
sandbox boundary. Isolated from the operator's own browser (a fresh profile
per launch, regardless of binary) and prefers an installed open-source
Chromium over the box's Chrome when the operator installs one
(`OPERATOR_SETUP.md` §Chart rendering). `SECURITY.md` §Static image export
has the full detail.

One known gap remains, non-blocking:

- **`excise-sandbox` uid separation.** The sandboxed script runs as the
  orchestrator's own user, not the dedicated `excise-sandbox` account.
  `sudo loginctl enable-linger excise-sandbox` is done, but
  `systemd-run --uid=excise-sandbox` from an unprivileged session still needs
  root/polkit regardless of linger — confirmed live. The sudoers fallback in
  `SECURITY.md` §2 (`OPERATOR_SETUP.md` §Sandbox execution route) is the real
  path; `sandbox_uid_switch_enabled` in `config.py` flips it on once that's in
  place. `bwrap`'s own namespace/network/filesystem confinement is the primary
  control either way and is fully active without the uid switch.

Also found and fixed along the way: `db/roles.sql`'s documented `psql -v`
invocation double-quoted the role passwords (see its header comment);
`systemd-run --property=MemoryMax=` alone lets a script page into swap instead
of getting OOM-killed (needs `MemorySwapMax=0` too); numpy/OpenBLAS defaults
to one thread per CPU and blew past `TasksMax=16` on import (capped via
`OPENBLAS_NUM_THREADS=1` etc. in the sandbox env); `OLLAMA_KEEP_ALIVE` /
`OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS` (`EVALUATION.md` §2) were
never actually applied to the Ollama service — `OPERATOR_SETUP.md` §Ollama
runtime settings; GNU Octave has no `table`/`readtable`, so query results
hand off as generated Octave variables instead — `MCP_ENGINES.md` §2.

## Local dev

```bash
cd ~/Sites/excise-mcp-dashboard/orchestrator
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env
# fill in DATABASE_URL_READONLY with the ro_pw set in db/roles.sql
# and pick a real ORCH_BEARER_TOKEN (shared with web/.env)
```

Verify:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8085 &
curl -s http://127.0.0.1:8085/health | python3 -m json.tool
```
