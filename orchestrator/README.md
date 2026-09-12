# orchestrator/

Python 3.12 FastAPI service: the one-shot analytical pipeline (`/query`), the
MCP client to Ollama, the SQL guard, the sandbox launcher, and the engine
router. `127.0.0.1:8085` only, never tunneled. `MCP_ENGINES.md` covers the
full design; this is the package layout.

```
orchestrator/
  app/
    main.py            FastAPI app, lifespan, /health, /query, /query/{id}/status
    config.py           Settings (pydantic-settings) — MCP_ENGINES.md §Config
    auth.py              bearer-token dependency
    schemas.py           QueryRequest/Response, SqlPlan, PlotPlan, Stage, typed errors
    pipeline.py           the six stages: plan_sql -> guard_sql -> run_sql -> plan_plot -> render -> summarize
    llm/
      client.py           Ollama async client, structured-output retry loop
      prompts.py          system prompts, the schema-card slot, few-shot NL->SQL examples
    sql/
      schema_card.py       renders analytics.* into the prompt schema card
      guard.py              single-read-only-SELECT parser (sqlglot) + reject list
      runner.py             asyncpg pool on excise_ro, READ ONLY txn, statement timeout
    engines/
      base.py               IVisualizationEngine protocol + registry
      python_engine.py       the one implemented engine (Matplotlib/Plotly/pandas)
    sandbox/
      bwrap.py               builds + runs the bwrap sandbox command
  tests/
```

## Status

Milestone 2 is done: `ruff` / `ruff format --check` / `mypy --strict` green,
32 tests passing against the real `bwrap` + `systemd-run` on this box, and a
real `/query` end-to-end against the live `excise_bank` — "How many districts
are in each zone?" produces a real `GROUP BY` over `analytics.districts`, a
real sandboxed Plotly render, and a real `llama3.1`-narrated summary.

Two known gaps, both non-blocking:

- **Static chart export** (`chart.png`/`svg`/`pdf`). Plotly's `fig.write_image`
  needs `kaleido>=1.0`, which drives a real headless Chrome (the box's
  `/opt/google/chrome`, bind-mounted read-only) instead of the old pure-binary
  renderer — it fails to launch inside the sandbox even with `/dev/shm`
  mounted (`BrowserFailedError`). `llm/prompts.py` asks the model for
  `chart.plotly.json` only until this is debugged further; see the note in
  `engines/python_engine.py`. Matplotlib's `plt.savefig` has no Chrome
  dependency and may be a simpler path if the LLM is steered to prefer it —
  untried.
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
runtime settings.

## Local dev

```bash
cd ~/Sites/excise-mcp-dashboard/orchestrator
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env
# fill in DATABASE_URL_READONLY with the ro_pw set in db/roles.sql
# and pick a real ORCH_BEARER_TOKEN (shared with web/.env once web/ exists)
```

Verify:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8085 &
curl -s http://127.0.0.1:8085/health | python3 -m json.tool
```
