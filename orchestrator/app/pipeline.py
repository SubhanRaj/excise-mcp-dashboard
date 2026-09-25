"""The one-shot analytical flow: plan_sql -> guard_sql -> run_sql -> plan_plot ->
render -> summarize. MCP_ENGINES.md §Pipeline stages.
"""

import datetime
import decimal
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import asyncpg
import pandas as pd

from app.config import settings
from app.engines.base import RenderRequest
from app.engines.base import available as available_engines
from app.engines.base import get as get_engine
from app.llm.client import OllamaClient, TokenUsage
from app.llm.prompts import build_plot_prompt, build_sql_prompt, build_summary_prompt
from app.schemas import (
    ChartArtifact,
    ModelNotAllowedError,
    PlotPlan,
    QueryRequest,
    QueryResponse,
    RenderEmptyError,
    SandboxViolationError,
    SqlExecutionError,
    SqlPlan,
    SqlRejectedError,
    Stage,
)
from app.sql.guard import guard_sql
from app.sql.runner import run_sql


def _select_model(requested: str | None, default: str) -> str:
    if requested is None:
        return default
    if requested not in settings.allowed_models:
        raise ModelNotAllowedError(requested)
    return requested


def _json_safe(value: object) -> object:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value


def _json_safe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{k: _json_safe(v) for k, v in row.items()} for row in rows]


def _resolve_outputs(requested: list[str], supported: frozenset[str]) -> list[str]:
    """Drops any output the chosen engine can't produce (e.g. a stale
    `plotly_json` request against Octave). Falls back to a static chart
    (`png`, in every engine's supported_outputs) rather than rendering
    nothing when the LLM's plan doesn't match the engine it picked.
    """
    kept = [o for o in requested if o in supported]
    return kept or ["png"]


def _write_parquet(df: pd.DataFrame, request_id: str) -> Path:
    fd, path_str = tempfile.mkstemp(prefix=f"excise-{request_id}-", suffix=".parquet")
    os.close(fd)
    path = Path(path_str)
    df.to_parquet(path)
    return path


async def run_query(
    request: QueryRequest,
    *,
    request_id: str,
    pool: asyncpg.Pool,
    ollama: OllamaClient,
    schema_card: str,
    on_stage: Callable[[Stage], Awaitable[None]] | None = None,
) -> QueryResponse:
    stages: list[Stage] = []
    timings_ms: dict[str, int] = {}
    usage = TokenUsage()
    sql_model = _select_model(request.model, settings.ollama_sql_model)
    chat_model = settings.ollama_chat_model  # summarize always narrates with the chat-role model

    async def emit(stage: Stage) -> None:
        stages.append(stage)
        if on_stage is not None:
            await on_stage(stage)

    t0 = time.monotonic()
    await emit(Stage(name="plan_sql", status="running"))
    prompt = build_sql_prompt(request.question, schema_card, request.history)
    sql_plan = await ollama.generate_structured(
        model=sql_model, prompt=prompt, response_model=SqlPlan, stage="plan_sql", usage=usage
    )
    try:
        guard_result = guard_sql(sql_plan.sql, request.row_limit)
    except SqlRejectedError as first_rejection:
        reprompt = (
            f"{prompt}\n\nThe previous SQL was rejected: {first_rejection.message}\n"
            "Write a corrected single read-only SELECT."
        )
        sql_plan = await ollama.generate_structured(
            model=sql_model, prompt=reprompt, response_model=SqlPlan, stage="plan_sql", usage=usage
        )
        guard_result = guard_sql(sql_plan.sql, request.row_limit)  # a second rejection propagates
    timings_ms["plan_sql"] = int((time.monotonic() - t0) * 1000)
    await emit(Stage(name="plan_sql", status="ok", ms=timings_ms["plan_sql"]))
    await emit(Stage(name="guard_sql", status="ok"))

    t0 = time.monotonic()
    await emit(Stage(name="run_sql", status="running"))
    try:
        rows = await run_sql(guard_result.sql, request.row_limit)
    except SqlExecutionError as first_run_failure:
        # Passing guard_sql only proves the statement is a single read-only
        # SELECT — a hallucinated table/column or an ambiguous cast (ask
        # Postgres, not a string filter) only surfaces once it actually runs.
        # Same reprompt-and-retry-once shape as guard_sql's own rejection above.
        reprompt = (
            f"{prompt}\n\nThe previous SQL failed against the database: "
            f"{first_run_failure.message}\nWrite a corrected single read-only SELECT."
        )
        sql_plan = await ollama.generate_structured(
            model=sql_model, prompt=reprompt, response_model=SqlPlan, stage="plan_sql", usage=usage
        )
        guard_result = guard_sql(sql_plan.sql, request.row_limit)
        rows = await run_sql(guard_result.sql, request.row_limit)  # a second failure propagates
    timings_ms["run_sql"] = int((time.monotonic() - t0) * 1000)
    await emit(Stage(name="run_sql", status="ok", ms=timings_ms["run_sql"]))

    df = pd.DataFrame(rows)
    row_count = len(df)
    rows_preview = _json_safe_rows(rows[:50])

    chart: ChartArtifact | None = None
    engine_used = "python"
    # A single-row result (typically a bare COUNT(*)) has no dimension to plot — asking
    # the model for a chart script anyway is how a "how many X" question ended up
    # crashing Octave's print() with "no axes object in figure": there was nothing to
    # draw. Same no-hallucination reasoning as the zero-row summary skip below.
    if row_count > 1:
        avail = available_engines()
        t0 = time.monotonic()
        await emit(Stage(name="plan_plot", status="running"))
        plot_prompt = build_plot_prompt(
            request.question, list(df.columns), [str(t) for t in df.dtypes], row_count, avail
        )
        plot_plan = await ollama.generate_structured(
            model=sql_model,
            prompt=plot_prompt,
            response_model=PlotPlan,
            stage="plan_plot",
            usage=usage,
        )
        engine_used = request.engine_hint or (
            plot_plan.engine if plot_plan.engine in avail else "python"
        )
        timings_ms["plan_plot"] = int((time.monotonic() - t0) * 1000)
        await emit(Stage(name="plan_plot", status="ok", ms=timings_ms["plan_plot"]))

        t0 = time.monotonic()
        await emit(Stage(name="render", status="running"))
        engine = get_engine(engine_used)
        outputs = _resolve_outputs([str(o) for o in plot_plan.outputs], engine.supported_outputs)
        data_path = _write_parquet(df, request_id)
        try:
            try:
                render_result = await engine.render(
                    RenderRequest(
                        script=plot_plan.script,
                        data_path=data_path,
                        outputs=outputs,
                        title=plot_plan.title,
                        scratch_dir=data_path.parent,
                    )
                )
            except (SandboxViolationError, RenderEmptyError) as first_failure:
                reprompt = (
                    f"{plot_prompt}\n\nThe previous script failed:\n{first_failure.message}\n"
                    f"Previous script:\n{plot_plan.script}\n\nWrite a corrected script."
                )
                plot_plan = await ollama.generate_structured(
                    model=sql_model,
                    prompt=reprompt,
                    response_model=PlotPlan,
                    stage="plan_plot",
                    usage=usage,
                )
                outputs = _resolve_outputs(
                    [str(o) for o in plot_plan.outputs], engine.supported_outputs
                )
                render_result = await engine.render(  # a second failure propagates
                    RenderRequest(
                        script=plot_plan.script,
                        data_path=data_path,
                        outputs=outputs,
                        title=plot_plan.title,
                        scratch_dir=data_path.parent,
                    )
                )
            chart = ChartArtifact(
                plotly_json=render_result.plotly_json,
                files={k: str(v) for k, v in render_result.files.items()},
            )
        finally:
            data_path.unlink(missing_ok=True)
        timings_ms["render"] = int((time.monotonic() - t0) * 1000)
        await emit(Stage(name="render", status="ok", ms=timings_ms["render"]))

    t0 = time.monotonic()
    await emit(Stage(name="summarize", status="running"))
    # An aggregate with no GROUP BY (SUM, AVG, ...) always returns exactly one row,
    # even when nothing in analytics matched the WHERE clause — NULL, not zero rows,
    # so row_count alone misses it. Confirmed live: "how much revenue from beer sale
    # in FY2025-26" matched nothing (the license-category filter it guessed at
    # doesn't isolate beer revenue), came back as one row with total_revenue = NULL,
    # and summarize — with nothing to say NULL means empty rather than a real
    # reading — invented a full answer, complete with a fabricated urban/rural split
    # nothing in the query even asked for.
    no_data = row_count == 0 or bool(df.isna().all().all())
    if no_data:
        # Asking the model to narrate this invites exactly what an LLM does with
        # nothing to work from: an invented trend. Same no-hallucination rule kb/retrieve.py
        # already follows for an empty corpus — say so, don't summarize.
        summary = "No rows matched this question."
    else:
        summary_prompt = build_summary_prompt(
            request.question, list(df.columns), row_count, rows_preview
        )
        summary = await ollama.generate_text(model=chat_model, prompt=summary_prompt, usage=usage)
    timings_ms["summarize"] = int((time.monotonic() - t0) * 1000)
    await emit(Stage(name="summarize", status="ok", ms=timings_ms["summarize"]))

    return QueryResponse(
        request_id=request_id,
        sql=guard_result.sql,
        row_count=row_count,
        rows_preview=rows_preview,
        chart=chart,
        summary=summary.strip(),
        engine=engine_used,
        model=sql_model,
        timings_ms=timings_ms,
        stages=stages,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
