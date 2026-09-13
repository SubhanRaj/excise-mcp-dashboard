"""llm/client.py structured-output retry loop. MCP_ENGINES.md §Structured-output loop."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.client import OllamaClient, TokenUsage
from app.schemas import LLMStructuredOutputError, OllamaUnreachableError


class _Thing(BaseModel):
    value: int


def _client_with_responses(*responses: str) -> OllamaClient:
    remaining = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        body = remaining.pop(0)
        return httpx.Response(200, json={"response": body})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return OllamaClient("http://fake-ollama", http_client)


async def test_generate_structured_succeeds_first_try() -> None:
    client = _client_with_responses(json.dumps({"value": 42}))
    result = await client.generate_structured(
        model="m", prompt="p", response_model=_Thing, stage="plan_sql"
    )
    assert result.value == 42


async def test_generate_structured_retries_once_then_succeeds() -> None:
    client = _client_with_responses("not json at all", json.dumps({"value": 7}))
    result = await client.generate_structured(
        model="m", prompt="p", response_model=_Thing, stage="plan_sql"
    )
    assert result.value == 7


async def test_generate_structured_fails_after_two_bad_attempts() -> None:
    client = _client_with_responses("still not json", "also not json")
    with pytest.raises(LLMStructuredOutputError):
        await client.generate_structured(
            model="m", prompt="p", response_model=_Thing, stage="plan_sql"
        )


async def test_ollama_unreachable_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://fake-ollama", http_client)
    with pytest.raises(OllamaUnreachableError):
        await client.generate_text(model="m", prompt="p")


async def test_chat_stream_parses_content_and_tool_call_chunks() -> None:
    lines = [
        json.dumps({"message": {"role": "assistant", "content": "Hel"}, "done": False}),
        json.dumps({"message": {"role": "assistant", "content": "lo."}, "done": False}),
        json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search_knowledge", "arguments": {"query": "MGQ"}}}
                    ],
                },
                "done": True,
            }
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=("\n".join(lines) + "\n").encode())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://fake-ollama", http_client)

    messages: list[dict[str, object]] = [{"role": "user", "content": "hi"}]
    chunks = [c async for c in client.chat_stream(model="m", messages=messages, tools=[])]

    assert [c.content for c in chunks] == ["Hel", "lo.", ""]
    assert chunks[-1].tool_calls[0].name == "search_knowledge"
    assert chunks[-1].tool_calls[0].arguments == {"query": "MGQ"}


async def test_generate_text_accumulates_token_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"response": "hi", "prompt_eval_count": 12, "eval_count": 3}
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://fake-ollama", http_client)
    usage = TokenUsage()

    await client.generate_text(model="m", prompt="p", usage=usage)

    assert usage.prompt_tokens == 12
    assert usage.completion_tokens == 3


async def test_generate_structured_sums_usage_across_a_retry() -> None:
    remaining = [
        {"response": "not json", "prompt_eval_count": 10, "eval_count": 5},
        {"response": json.dumps({"value": 1}), "prompt_eval_count": 20, "eval_count": 8},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=remaining.pop(0))

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://fake-ollama", http_client)
    usage = TokenUsage()

    await client.generate_structured(
        model="m", prompt="p", response_model=_Thing, stage="plan_sql", usage=usage
    )

    assert usage.prompt_tokens == 30
    assert usage.completion_tokens == 13


async def test_chat_stream_reports_usage_only_on_the_final_chunk() -> None:
    lines = [
        json.dumps({"message": {"role": "assistant", "content": "Hi"}, "done": False}),
        json.dumps(
            {
                "message": {"role": "assistant", "content": "!"},
                "done": True,
                "prompt_eval_count": 40,
                "eval_count": 6,
            }
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=("\n".join(lines) + "\n").encode())

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OllamaClient("http://fake-ollama", http_client)
    usage = TokenUsage()

    _ = [c async for c in client.chat_stream(model="m", messages=[], tools=[], usage=usage)]

    assert usage.prompt_tokens == 40
    assert usage.completion_tokens == 6
