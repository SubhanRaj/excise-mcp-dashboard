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
        (MakeChartArgs, {"spec": "fig.write_json(...)", "data_ref": "conv-1"}),
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


async def test_make_chart_rejects_a_data_ref_for_a_different_conversation() -> None:
    chat_tools._LAST_RESULT["c1"] = pd.DataFrame([{"a": 1}])
    call = ToolCall(name="make_chart", arguments={"spec": "x", "data_ref": "someone-elses-conv"})
    with pytest.raises(ChatToolArgumentError):
        await dispatch(
            call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c1"
        )
    del chat_tools._LAST_RESULT["c1"]


async def test_make_chart_rejects_when_no_prior_result_exists() -> None:
    chat_tools._LAST_RESULT.pop("c-empty", None)
    call = ToolCall(name="make_chart", arguments={"spec": "x", "data_ref": "c-empty"})
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
    call = ToolCall(name="make_chart", arguments={"spec": "bad script", "data_ref": "c-fail"})
    result = await dispatch(
        call, ollama=_ollama_returning("{}"), schema_card="(schema)", conversation_id="c-fail"
    )
    assert result.ok is False
    assert "bad kwarg" in result.summary
    del chat_tools._LAST_RESULT["c-fail"]
