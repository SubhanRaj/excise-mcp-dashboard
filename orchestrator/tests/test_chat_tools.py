"""chat/tools.py: argument schema round-trips and dispatch's guardrails.
MCP_ENGINES.md §Tools (chat/tools.py).
"""

import json

import httpx
import pandas as pd
import pytest

from app.chat import tools as chat_tools
from app.chat.tools import MakeChartArgs, RunSqlQueryArgs, SearchKnowledgeArgs, dispatch
from app.llm.client import OllamaClient
from app.schemas import ChatToolArgumentError, SqlRejectedError, ToolCall


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


async def test_dispatch_rejects_run_sql_query_with_neither_sql_nor_question() -> None:
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


async def test_run_sql_query_with_a_bad_plan_raises_the_same_guard_error() -> None:
    # Same rejection path /query's guard already has a test for — not a new one.
    plan = json.dumps(
        {"sql": "DELETE FROM analytics.shops", "rationale": "x", "expected_columns": []}
    )
    call = ToolCall(name="run_sql_query", arguments={"question": "delete everything"})
    with pytest.raises(SqlRejectedError):
        await dispatch(
            call, ollama=_ollama_returning(plan), schema_card="(schema)", conversation_id="c1"
        )


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
