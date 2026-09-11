"""llm/client.py structured-output retry loop. MCP_ENGINES.md §Structured-output loop."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.client import OllamaClient
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
