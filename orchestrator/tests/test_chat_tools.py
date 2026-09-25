"""chat/tools.py: argument schema round-trips and dispatch's guardrails.
MCP_ENGINES.md §Tools (chat/tools.py).
"""

import json

import httpx
import pandas as pd
import pytest

from app.chat import tools as chat_tools
from app.chat.tools import MakeChartArgs, RunSqlQueryArgs, SearchKnowledgeArgs, dispatch
from app.engines.base import RenderRequest, RenderResult
from app.llm.client import OllamaClient
from app.schemas import ChatToolArgumentError, SandboxViolationError, ToolCall


def _ollama_returning(response_text: str) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": response_text})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaClient("http://fake-ollama", http_client)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (SearchKnowledgeArgs, {"query": "MGQ policy"}),
        (RunSqlQueryArgs, {"question": "how many districts?"}),
        (MakeChartArgs, {"spec": "fig.write_json(...)"}),
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


async def test_make_chart_uses_the_conversations_own_last_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # data_ref (a required model-supplied argument matched against conversation_id)
    # used to gate this — but the model is never told the conversation_id anywhere
    # (not in CHAT_SYSTEM_PROMPT, not in the message history), so no real call could
    # ever pass it. The lookup is scoped by the trusted conversation_id dispatch()
    # already receives from the request, not by anything the model supplies.
    class _FakeEngine:
        supported_outputs = frozenset({"plotly_json"})

        async def render(self, req: RenderRequest) -> RenderResult:
            return RenderResult(plotly_json="{}", files={}, engine="python")

    monkeypatch.setattr(chat_tools, "get_engine", lambda name: _FakeEngine())
    chat_tools._LAST_RESULT["c1"] = pd.DataFrame([{"a": 1}])
    chat_tools._LAST_RESULT["c2"] = pd.DataFrame([{"a": 2}])
    call = ToolCall(name="make_chart", arguments={"spec": "fig.write_json(...)"})
    result = await dispatch(
        call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c1"
    )
    assert result.ok is True
    del chat_tools._LAST_RESULT["c1"]
    del chat_tools._LAST_RESULT["c2"]


async def test_make_chart_rejects_when_no_prior_result_exists() -> None:
    chat_tools._LAST_RESULT.pop("c-empty", None)
    call = ToolCall(name="make_chart", arguments={"spec": "x"})
    with pytest.raises(ChatToolArgumentError):
        await dispatch(
            call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c-empty"
        )


async def test_make_chart_returns_a_failed_tool_result_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bad script (the model hallucinating a Plotly kwarg that doesn't exist,
    # say) must come back as something the chat loop can feed to the model for
    # a retry within its own tool-call budget, not end the whole turn.
    class _FailingEngine:
        supported_outputs = frozenset({"plotly_json"})

        async def render(self, req: RenderRequest) -> RenderResult:
            raise SandboxViolationError("exit 1: TypeError: bad kwarg")

    monkeypatch.setattr(chat_tools, "get_engine", lambda name: _FailingEngine())
    chat_tools._LAST_RESULT["c-fail"] = pd.DataFrame([{"a": 1}])
    call = ToolCall(name="make_chart", arguments={"spec": "bad script"})
    result = await dispatch(
        call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c-fail"
    )
    assert result.ok is False
    assert "bad kwarg" in result.summary
    del chat_tools._LAST_RESULT["c-fail"]
