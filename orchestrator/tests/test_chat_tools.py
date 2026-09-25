"""chat/tools.py: argument schema round-trips and dispatch's guardrails.
MCP_ENGINES.md §Tools (chat/tools.py).
"""

import json

import httpx
import pandas as pd
import pytest

from app.chat import tools as chat_tools
from app.chat.tools import RunSqlQueryArgs, SearchKnowledgeArgs, auto_chart, dispatch
from app.engines.base import RenderRequest, RenderResult
from app.llm.client import OllamaClient
from app.schemas import ChatToolArgumentError, KbChunk, SandboxViolationError, ToolCall


def _ollama_returning(response_text: str) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": response_text})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaClient("http://fake-ollama", http_client)


def _ollama_capturing(response_text: str, captured_prompts: list[str]) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured_prompts.append(json.loads(request.content)["prompt"])
        return httpx.Response(200, json={"response": response_text})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaClient("http://fake-ollama", http_client)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (SearchKnowledgeArgs, {"query": "MGQ policy"}),
        (RunSqlQueryArgs, {"question": "how many districts?"}),
    ],
)
def test_tool_args_schema_round_trips(model: type, payload: dict[str, object]) -> None:
    schema = model.model_json_schema()
    assert schema["type"] == "object"
    assert model.model_validate(payload)


async def test_dispatch_rejects_run_sql_query_without_a_question() -> None:
    call = ToolCall(name="run_sql_query", arguments={})
    with pytest.raises(ChatToolArgumentError):
        await dispatch(
            call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c1"
        )


async def test_dispatch_rejects_malformed_tool_arguments() -> None:
    call = ToolCall(name="search_knowledge", arguments={"k": "not-an-int"})
    with pytest.raises(ChatToolArgumentError):
        await dispatch(
            call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c1"
        )


def test_search_knowledge_args_accepts_an_explicit_null_k() -> None:
    # Llama's tool-calling fills in every schema property rather than omitting ones it
    # doesn't want to set, sending an explicit `k: null` for the unset default — this
    # crashed the whole chat turn live until `k` became Optional.
    assert SearchKnowledgeArgs.model_validate({"query": "MGQ policy", "k": None}).k is None


def test_search_knowledge_args_accepts_the_literal_string_null_too() -> None:
    # Confirmed live: asked "what are the different UP Excise shop types and license
    # codes", the model sent k as the JSON string "null" rather than the JSON value
    # null — a plain int | None doesn't coerce that on its own, since "null" the string
    # is valid (if odd) input for a str-typed field, not a null.
    assert SearchKnowledgeArgs.model_validate({"query": "shop types", "k": "null"}).k is None
    assert SearchKnowledgeArgs.model_validate({"query": "shop types", "k": "NULL"}).k is None
    assert SearchKnowledgeArgs.model_validate({"query": "shop types", "k": "3"}).k == 3


def test_search_knowledge_args_accepts_an_explicit_states_list() -> None:
    args = SearchKnowledgeArgs.model_validate(
        {"query": "how does UP compare to Delhi", "states": ["Uttar Pradesh", "Delhi"]}
    )
    assert args.states == ["Uttar Pradesh", "Delhi"]


def test_search_knowledge_args_tolerates_a_bare_state_name_or_null_string() -> None:
    # Same Llama tool-calling quirk k already needed a validator for — confirmed as a
    # real shape for a new list-typed argument too, before it ever ran live.
    assert SearchKnowledgeArgs.model_validate(
        {"query": "Delhi excise policy", "states": "Delhi"}
    ).states == ["Delhi"]
    assert (
        SearchKnowledgeArgs.model_validate({"query": "MGQ policy", "states": "null"}).states is None
    )
    assert SearchKnowledgeArgs.model_validate({"query": "MGQ policy"}).states is None


async def test_search_knowledge_passes_states_through_and_labels_the_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # kb/retrieve.py's own states filter hits a real Postgres, so this checks the
    # tool-layer half of the fix directly: the model's states argument reaches
    # kb_retrieve unchanged, and a result's own state rides into the citation the
    # model reads and is told to attribute by (chat/prompts.py's CHAT_SYSTEM_PROMPT).
    captured: dict[str, object] = {}

    async def fake_kb_retrieve(query: str, k: int, states: list[str] | None) -> list[object]:
        captured["states"] = states
        return [
            KbChunk(
                content="Delhi's own MGQ rule text.",
                heading_path="Rule 5",
                title="Delhi Excise Rules",
                source_url=None,
                doc_type="rule",
                effective_from=None,
                state="Delhi",
                rank=1.0,
            )
        ]

    monkeypatch.setattr(chat_tools, "kb_retrieve", fake_kb_retrieve)

    call = ToolCall(
        name="search_knowledge",
        arguments={"query": "MGQ", "states": ["Uttar Pradesh", "Delhi"]},
    )
    result = await dispatch(
        call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c1"
    )

    assert captured["states"] == ["Uttar Pradesh", "Delhi"]
    assert result.ok is True
    assert "[Delhi Excise Rules (Delhi) — Rule 5]" in result.summary


async def test_run_sql_query_with_a_bad_plan_returns_a_failed_tool_result() -> None:
    # Same rejection path /query's guard already has a test for. Unlike /query
    # (a one-shot pipeline with no one left to ask), a chat turn returns this
    # as a failed tool result rather than raising: the model sees why the SQL
    # was rejected and can call run_sql_query again within its own tool-call
    # budget, the same recovery make_chart already gets for a bad script.
    plan = json.dumps(
        {"sql": "DELETE FROM analytics.shops", "rationale": "x", "expected_columns": []}
    )
    call = ToolCall(name="run_sql_query", arguments={"question": "delete everything"})
    result = await dispatch(
        call, ollama=_ollama_returning(plan), schema_card="(schema)", conversation_id="c1"
    )
    assert result.ok is False


async def test_run_sql_query_with_a_null_aggregate_says_so_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bare SUM()/AVG() with no GROUP BY always returns exactly one row, even when
    # nothing matched the WHERE clause — NULL, not zero rows. Left as a bare preview of
    # null values, this used to read to the chat model like real data worth narrating
    # (confirmed live: a fabricated crore figure with an invented urban/rural split) or
    # leave it with nothing to say at all.
    plan = json.dumps(
        {
            "sql": "SELECT SUM(x) AS total_revenue FROM analytics.sro_shops",
            "rationale": "x",
            "expected_columns": ["total_revenue"],
        }
    )

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        return [{"total_revenue": None}]

    monkeypatch.setattr(chat_tools, "run_sql", fake_run_sql)

    call = ToolCall(name="run_sql_query", arguments={"question": "how much beer revenue"})
    result = await dispatch(
        call, ollama=_ollama_returning(plan), schema_card="(schema)", conversation_id="c1"
    )

    assert result.ok is True
    assert "no matching data" in result.summary
    assert "None" not in result.summary


async def test_run_sql_query_result_carries_a_precomputed_money_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The chat model narrates this preview with no summarize() call of its own to hand
    # a pre-computed figure to otherwise — same gap and same fix as pipeline.py's
    # build_summary_prompt (confirmed live: a district revenue reported tenfold too
    # large when the model did the crore conversion itself).
    plan = json.dumps(
        {
            "sql": "SELECT district, SUM(total_revenue) AS total_revenue FROM analytics.sro_shops",
            "rationale": "x",
            "expected_columns": ["district", "total_revenue"],
        }
    )

    async def fake_run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
        return [{"district": "Lucknow", "total_revenue": 28_608_029_608.93}]

    monkeypatch.setattr(chat_tools, "run_sql", fake_run_sql)

    call = ToolCall(name="run_sql_query", arguments={"question": "top district by revenue"})
    result = await dispatch(
        call, ollama=_ollama_returning(plan), schema_card="(schema)", conversation_id="c1"
    )

    assert "total_revenue = ₹2,860.80 crore" in result.summary


def _plan_plot_response(script: str = 'fig.write_json(f"{OUT}/chart.plotly.json")') -> str:
    return json.dumps(
        {"engine": "python", "script": script, "outputs": ["plotly_json"], "title": "x"}
    )


async def test_auto_chart_uses_the_conversations_own_last_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A chart is a deterministic step chat/loop.py takes itself, scoped by the
    # trusted conversation_id it already has from the request — never a tool
    # argument the model supplies (MCP_ENGINES.md §Tools).
    class _FakeEngine:
        supported_outputs = frozenset({"plotly_json"})

        async def render(self, req: RenderRequest) -> RenderResult:
            return RenderResult(plotly_json="{}", files={}, engine="python")

    monkeypatch.setattr(chat_tools, "get_engine", lambda name: _FakeEngine())
    chat_tools._LAST_RESULT["c1"] = pd.DataFrame([{"a": 1}, {"a": 2}])
    chat_tools._LAST_RESULT["c2"] = pd.DataFrame([{"a": 3}, {"a": 4}])
    result = await auto_chart(
        "c1", "chart it", ollama=_ollama_returning(_plan_plot_response()), usage=None
    )
    assert result is not None
    assert result.ok is True
    del chat_tools._LAST_RESULT["c1"]
    del chat_tools._LAST_RESULT["c2"]


async def test_auto_chart_never_offers_octave(monkeypatch: pytest.MonkeyPatch) -> None:
    # Confirmed live: with both engines offered, Qwen picked Octave for a
    # categorical bar chart -- Octave's own capability text says it can never
    # produce plotly_json, the only output chat's auto_chart ever collects, so a
    # script that succeeded there still could not have produced a usable chart.
    # Octave is excluded from build_plot_prompt's own engine list entirely rather
    # than corrected after the fact.
    class _FakeEngine:
        supported_outputs = frozenset({"plotly_json"})

        async def render(self, req: RenderRequest) -> RenderResult:
            return RenderResult(plotly_json="{}", files={}, engine="python")

    monkeypatch.setattr(chat_tools, "get_engine", lambda name: _FakeEngine())
    chat_tools._LAST_RESULT["c-engines"] = pd.DataFrame([{"a": 1}, {"a": 2}])
    prompts: list[str] = []
    await auto_chart(
        "c-engines",
        "chart it",
        ollama=_ollama_capturing(_plan_plot_response(), prompts),
        usage=None,
    )
    assert "octave" not in prompts[0].lower()
    del chat_tools._LAST_RESULT["c-engines"]


async def test_auto_chart_returns_none_when_theres_nothing_to_chart() -> None:
    # No prior run_sql_query result, or a single-row one (a bare COUNT(*), say) —
    # neither has a dimension to plot, the same reasoning pipeline.py's own
    # row_count > 1 gate already uses for /query. None, not a failed ToolResult:
    # this isn't an error, there was never a chart to attempt.
    chat_tools._LAST_RESULT.pop("c-empty", None)
    assert await auto_chart("c-empty", "x", ollama=_ollama_returning("{}"), usage=None) is None

    chat_tools._LAST_RESULT["c-single"] = pd.DataFrame([{"a": 1}])
    assert await auto_chart("c-single", "x", ollama=_ollama_returning("{}"), usage=None) is None
    del chat_tools._LAST_RESULT["c-single"]


async def test_auto_chart_returns_a_failed_tool_result_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bad script (Qwen hallucinating a Plotly kwarg that doesn't exist, say) must
    # come back as a failed ToolResult chat/loop.py can tell the model about, not
    # raise and end the turn.
    class _FailingEngine:
        supported_outputs = frozenset({"plotly_json"})

        async def render(self, req: RenderRequest) -> RenderResult:
            raise SandboxViolationError("exit 1: TypeError: bad kwarg")

    monkeypatch.setattr(chat_tools, "get_engine", lambda name: _FailingEngine())
    chat_tools._LAST_RESULT["c-fail"] = pd.DataFrame([{"a": 1}, {"a": 2}])
    result = await auto_chart(
        "c-fail", "chart it", ollama=_ollama_returning(_plan_plot_response()), usage=None
    )
    assert result is not None
    assert result.ok is False
    assert "bad kwarg" in result.summary
    del chat_tools._LAST_RESULT["c-fail"]
