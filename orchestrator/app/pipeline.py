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
from app.llm.client import OllamaClient
from app.llm.prompts import build_plot_prompt, build_sql_prompt, build_summary_prompt
from app.schemas import (
    ChartArtifact,
    ModelNotAllowedError,
    PlotPlan,
    QueryRequest,
    QueryResponse,
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
    sql_model = _select_model(request.model, settings.ollama_sql_model)
    chat_model = settings.ollama_chat_model  # summarize always narrates with the chat-role model

    async def emit(stage: Stage) -> None:
        stages.append(stage)
        if on_stage is not None:
            await on_stage(stage)

    t0 = time.monotonic()
    prompt = build_sql_prompt(request.question, schema_card, request.history)
    sql_plan = await ollama.generate_structured(
        model=sql_model, prompt=prompt, response_model=SqlPlan, stage="plan_sql"
    )
    try:
        guard_result = guard_sql(sql_plan.sql, request.row_limit)
    except SqlRejectedError as first_rejection:
        reprompt = (
            f"{prompt}\n\nThe previous SQL was rejected: {first_rejection.message}\n"
            "Write a corrected single read-only SELECT."
        )
        sql_plan = await ollama.generate_structured(
            model=sql_model, prompt=reprompt, response_model=SqlPlan, stage="plan_sql"
        )
        guard_result = guard_sql(sql_plan.sql, request.row_limit)  # a second rejection propagates
    timings_ms["plan_sql"] = int((time.monotonic() - t0) * 1000)
    await emit(Stage(name="plan_sql", status="ok", ms=timings_ms["plan_sql"]))
    await emit(Stage(name="guard_sql", status="ok"))

    t0 = time.monotonic()
    rows = await run_sql(guard_result.sql, request.row_limit)
    timings_ms["run_sql"] = int((time.monotonic() - t0) * 1000)
    await emit(Stage(name="run_sql", status="ok", ms=timings_ms["run_sql"]))

    df = pd.DataFrame(rows)
    row_count = len(df)
    rows_preview = _json_safe_rows(rows[:50])

    chart: ChartArtifact | None = None
    engine_used = "python"
    if row_count > 0:
        t0 = time.monotonic()
        plot_prompt = build_plot_prompt(
            request.question, list(df.columns), [str(t) for t in df.dtypes], row_count
        )
        plot_plan = await ollama.generate_structured(
            model=sql_model, prompt=plot_prompt, response_model=PlotPlan, stage="plan_plot"
        )
        engine_used = request.engine_hint or (
            plot_plan.engine if plot_plan.engine in available_engines() else "python"
        )
        timings_ms["plan_plot"] = int((time.monotonic() - t0) * 1000)
        await emit(Stage(name="plan_plot", status="ok", ms=timings_ms["plan_plot"]))

        t0 = time.monotonic()
        engine = get_engine(engine_used)
        data_path = _write_parquet(df, request_id)
        try:
            render_result = await engine.render(
                RenderRequest(
                    script=plot_plan.script,
                    data_path=data_path,
                    outputs=[str(o) for o in plot_plan.outputs],
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
    summary_prompt = build_summary_prompt(
        request.question, list(df.columns), row_count, rows_preview
    )
    summary = await ollama.generate_text(model=chat_model, prompt=summary_prompt)
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
    )
