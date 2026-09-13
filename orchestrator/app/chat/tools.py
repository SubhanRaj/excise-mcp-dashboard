"""Chat tool dispatch: search_knowledge / run_sql_query / make_chart.
MCP_ENGINES.md §Tools (chat/tools.py).

Each tool calls into the modules the one-shot pipeline already uses — the
same SQL guard, the same read-only role, the same sandbox. No parallel
implementation.
"""

import pandas as pd
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.engines.base import RenderRequest
from app.engines.base import get as get_engine
from app.kb.retrieve import retrieve as kb_retrieve
from app.llm.client import OllamaClient
from app.llm.prompts import build_sql_prompt
from app.pipeline import _json_safe_rows, _write_parquet
from app.schemas import ChartArtifact, ChatToolArgumentError, SqlPlan, ToolCall, ToolResult
from app.sql.guard import guard_sql
from app.sql.runner import run_sql

# The most recent run_sql_query result per conversation, so make_chart can
# render it — one more key in the in-process working set MCP_ENGINES.md
# §Memory already describes, evicted along with the rest of that conversation's
# state.
_LAST_RESULT: dict[str, pd.DataFrame] = {}


class SearchKnowledgeArgs(BaseModel):
    query: str
    k: int = 6


class RunSqlQueryArgs(BaseModel):
    sql: str | None = None
    question: str | None = None


class MakeChartArgs(BaseModel):
    spec: str
    data_ref: str


async def _search_knowledge(args: SearchKnowledgeArgs) -> ToolResult:
    chunks = await kb_retrieve(args.query, min(args.k, 12))
    if not chunks:
        return ToolResult(ok=True, summary="No matching passages in the knowledge base.")
    lines = [
        f"[{c.title}{f' — {c.heading_path}' if c.heading_path else ''}] {c.content}" for c in chunks
    ]
    return ToolResult(ok=True, summary="\n\n".join(lines))


async def _run_sql_query(
    args: RunSqlQueryArgs, *, conversation_id: str, ollama: OllamaClient, schema_card: str
) -> ToolResult:
    if args.sql is None and args.question is None:
        raise ChatToolArgumentError("run_sql_query", "one of sql or question is required")
    sql = args.sql
    if sql is None:
        prompt = build_sql_prompt(args.question or "", schema_card, [])
        plan = await ollama.generate_structured(
            model=settings.ollama_sql_model,
            prompt=prompt,
            response_model=SqlPlan,
            stage="tool_call",
        )
        sql = plan.sql
    guard_result = guard_sql(sql, settings.query_row_limit_default)
    rows = await run_sql(guard_result.sql, settings.query_row_limit_default)
    _LAST_RESULT[conversation_id] = pd.DataFrame(rows)
    preview = _json_safe_rows(rows[:5])
    columns = ", ".join(rows[0].keys()) if rows else "(none)"
    summary = f"{len(rows)} row(s), columns: {columns}. Preview: {preview}"
    return ToolResult(ok=True, summary=summary)


async def _make_chart(args: MakeChartArgs, *, conversation_id: str) -> ToolResult:
    if args.data_ref != conversation_id:
        raise ChatToolArgumentError(
            "make_chart", "data_ref must point at this conversation's last run_sql_query result"
        )
    df = _LAST_RESULT.get(conversation_id)
    if df is None:
        raise ChatToolArgumentError(
            "make_chart", "no run_sql_query result yet in this conversation"
        )

    engine = get_engine("python")
    data_path = _write_parquet(df, conversation_id)
    try:
        render_result = await engine.render(
            RenderRequest(
                script=args.spec,
                data_path=data_path,
                outputs=["plotly_json"],
                title="",
                scratch_dir=data_path.parent,
            )
        )
    finally:
        data_path.unlink(missing_ok=True)

    chart = ChartArtifact(
        plotly_json=render_result.plotly_json,
        files={k: str(v) for k, v in render_result.files.items()},
    )
    return ToolResult(ok=True, summary="Chart rendered.", chart=chart)


async def dispatch(
    call: ToolCall,
    *,
    ollama: OllamaClient,
    schema_card: str,
    conversation_id: str,
) -> ToolResult:
    try:
        if call.name == "search_knowledge":
            return await _search_knowledge(SearchKnowledgeArgs.model_validate(call.arguments))
        if call.name == "run_sql_query":
            return await _run_sql_query(
                RunSqlQueryArgs.model_validate(call.arguments),
                conversation_id=conversation_id,
                ollama=ollama,
                schema_card=schema_card,
            )
        return await _make_chart(
            MakeChartArgs.model_validate(call.arguments), conversation_id=conversation_id
        )
    except ValidationError as e:
        raise ChatToolArgumentError(call.name, str(e)) from e
