"""Chat tool dispatch: search_knowledge / run_sql_query / make_chart.
MCP_ENGINES.md §Tools (chat/tools.py).

Each tool calls into the modules the one-shot pipeline already uses — the
same SQL guard, the same read-only role, the same sandbox. No parallel
implementation.
"""

import pandas as pd
from pydantic import BaseModel, ValidationError, field_validator

from app.config import settings
from app.engines.base import RenderRequest
from app.engines.base import get as get_engine
from app.kb.retrieve import retrieve as kb_retrieve
from app.llm.client import OllamaClient, TokenUsage
from app.llm.prompts import build_sql_prompt, money_annotations
from app.pipeline import _json_safe_rows, _write_parquet
from app.schemas import (
    ChartArtifact,
    ChatToolArgumentError,
    RenderEmptyError,
    SandboxViolationError,
    SqlExecutionError,
    SqlPlan,
    SqlRejectedError,
    ToolCall,
    ToolResult,
)
from app.sql.guard import guard_sql
from app.sql.runner import run_sql

# The most recent run_sql_query result per conversation, so make_chart can
# render it — one more key in the in-process working set MCP_ENGINES.md
# §Memory already describes, evicted along with the rest of that conversation's
# state.
_LAST_RESULT: dict[str, pd.DataFrame] = {}


class SearchKnowledgeArgs(BaseModel):
    query: str
    # Llama's tool-calling fills in every schema property rather than omitting ones it
    # doesn't want to set, sending an explicit `k: null` — plain `int = 6` rejects that,
    # since a default only applies when the key is absent, not when it's null. Confirmed
    # live: it also sometimes sends the literal string "null" instead of the JSON value,
    # which int | None does not coerce on its own — "null" is a valid (if odd) string,
    # not a null, as far as int parsing is concerned.
    k: int | None = 6
    # None retrieves Uttar Pradesh (plus state-agnostic Acts/GOs) only — the safe
    # default. A comparative question ("how does X compare to Y state") names the
    # states to widen to, e.g. ["Uttar Pradesh", "Delhi"]. Same "null" string quirk as
    # k above, plus a single bare state name instead of a one-item list — both
    # confirmed shapes of how Llama's tool-calling fills in an unset or singular
    # argument for a schema it hasn't seen a worked example of yet.
    states: list[str] | None = None

    @field_validator("k", mode="before")
    @classmethod
    def _treat_the_string_null_as_none(cls, v: object) -> object:
        return None if isinstance(v, str) and v.strip().lower() == "null" else v

    @field_validator("states", mode="before")
    @classmethod
    def _tolerate_a_null_string_or_a_bare_state_name(cls, v: object) -> object:
        if isinstance(v, str):
            return None if v.strip().lower() == "null" else [v]
        return v


class RunSqlQueryArgs(BaseModel):
    # Deliberately no raw `sql` escape hatch: a general chat model has never seen the
    # schema and hallucinates table/column names when asked to write SQL itself (e.g.
    # a made-up "excise_data" table). Routing every call through `question` means the
    # SQL always comes from the schema-aware planner /query's own pipeline already uses.
    question: str


class MakeChartArgs(BaseModel):
    spec: str

    @field_validator("spec", mode="before")
    @classmethod
    def _unescape_over_escaped_quotes(cls, v: object) -> object:
        # Confirmed live: Llama's tool-calling sometimes sends spec's string
        # value with every quote backslash-escaped (`x=\"category_name\"`
        # instead of `x="category_name"`) — invalid Python wherever it lands
        # outside an actual string literal, and the cause of a real make_chart
        # failure ("unexpected character after line continuation character").
        # Only applied when the script as given doesn't compile and the naive
        # unescape does, so a spec that already runs is never touched.
        if not isinstance(v, str):
            return v
        try:
            compile(v, "<make_chart>", "exec")
            return v
        except SyntaxError:
            pass
        unescaped = v.replace('\\"', '"').replace("\\'", "'")
        try:
            compile(unescaped, "<make_chart>", "exec")
            return unescaped
        except SyntaxError:
            return v


async def _search_knowledge(args: SearchKnowledgeArgs) -> ToolResult:
    chunks = await kb_retrieve(args.query, min(args.k or 6, 12), args.states)
    if not chunks:
        return ToolResult(ok=True, summary="No matching passages in the knowledge base.")
    lines = [
        f"[{c.title}{f' ({c.state})' if c.state else ''}"
        f"{f' (effective {c.effective_from.year})' if c.effective_from else ''}"
        f"{f' — {c.heading_path}' if c.heading_path else ''}] {c.content}"
        for c in chunks
    ]
    return ToolResult(ok=True, summary="\n\n".join(lines))


async def _run_sql_query(
    args: RunSqlQueryArgs,
    *,
    conversation_id: str,
    ollama: OllamaClient,
    schema_card: str,
    usage: TokenUsage | None,
) -> ToolResult:
    prompt = build_sql_prompt(args.question, schema_card, [])
    plan = await ollama.generate_structured(
        model=settings.ollama_sql_model,
        prompt=prompt,
        response_model=SqlPlan,
        stage="tool_call",
        usage=usage,
    )
    sql = plan.sql
    try:
        guard_result = guard_sql(sql, settings.query_row_limit_default)
        rows = await run_sql(guard_result.sql, settings.query_row_limit_default)
    except (SqlRejectedError, SqlExecutionError) as e:
        # Fed back as a failed tool result, not raised: same reasoning as
        # make_chart's own catch below — the chat loop's tool-call budget is
        # the retry mechanism, so the model sees why the SQL failed (a
        # hallucinated table, an ambiguous cast) and can call run_sql_query
        # again with a corrected statement instead of the turn just ending.
        return ToolResult(ok=False, summary=e.message)
    _LAST_RESULT[conversation_id] = pd.DataFrame(rows)
    preview = _json_safe_rows(rows[:5])
    columns = ", ".join(rows[0].keys()) if rows else "(none)"
    if rows and all(v is None for row in rows for v in row.values()):
        # An aggregate with no GROUP BY (SUM, AVG, ...) always returns exactly one
        # row even when nothing matched the WHERE clause — NULL, not zero rows, so
        # the empty-rows case below never catches it. Left as a bare preview of
        # null values, this reads to the chat model like real data worth
        # narrating, or it gives up with nothing to say — the same NULL-aggregate
        # gap pipeline.py's summarize guards against (MCP_ENGINES.md §Tools).
        summary = (
            f"{len(rows)} row(s), columns: {columns}, but every value is empty — "
            "no matching data for this question, not a real zero or total."
        )
    else:
        # The chat model narrates this preview directly with no summarize() call of
        # its own to hand a pre-computed figure to otherwise — same reasoning and
        # same helper as pipeline.py's build_summary_prompt.
        annotations = money_annotations(list(rows[0].keys()), rows[:5]) if rows else ""
        summary = f"{len(rows)} row(s), columns: {columns}. Preview: {preview}{annotations}"
    return ToolResult(ok=True, summary=summary)


async def _make_chart(args: MakeChartArgs, *, conversation_id: str) -> ToolResult:
    # The last run_sql_query result is already scoped by conversation_id — a trusted
    # value dispatch() passes in from the request, never from the model's own tool
    # arguments. An earlier data_ref argument asked the model to also state the
    # conversation_id itself as a match check, but the model is never told that id
    # anywhere (not in CHAT_SYSTEM_PROMPT, not in the message history), so it could
    # never supply the one value that would pass — every make_chart call failed.
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
    except (SandboxViolationError, RenderEmptyError) as e:
        # Fed back as a failed tool result, not raised: the chat loop's own
        # tool-call budget is the retry mechanism here — the model sees why its
        # script failed and can call make_chart again with a corrected one.
        return ToolResult(ok=False, summary=e.message)
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
    usage: TokenUsage | None = None,
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
                usage=usage,
            )
        return await _make_chart(
            MakeChartArgs.model_validate(call.arguments), conversation_id=conversation_id
        )
    except ValidationError as e:
        raise ChatToolArgumentError(call.name, str(e)) from e
