"""Ollama async client: structured-output loop (one retry), plain text
generation, and the streaming chat call. MCP_ENGINES.md §Structured-output
loop, §Chat and retrieval.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas import LLMStructuredOutputError, OllamaUnreachableError, ToolCall

T = TypeVar("T", bound=BaseModel)


@dataclass
class ChatChunk:
    """One /api/chat streamed line, decoded: a content delta, or the tool
    calls Ollama attaches to a turn's final message. Internal to the chat
    loop, not a wire model.
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class OllamaClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http_client

    async def generate_structured(
        self, *, model: str, prompt: str, response_model: type[T], stage: str
    ) -> T:
        current_prompt = prompt
        last_error = ""
        for attempt in (1, 2):
            raw = await self._generate(
                model=model, prompt=current_prompt, format_schema=response_model.model_json_schema()
            )
            try:
                return response_model.model_validate_json(raw)
            except ValidationError as e:
                last_error = str(e)
                if attempt == 2:
                    raise LLMStructuredOutputError(
                        response_model.__name__, stage, last_error
                    ) from e
                current_prompt = (
                    f"{prompt}\n\nThe previous reply failed validation:\n{last_error}\n"
                    "Return only valid JSON matching the schema."
                )
        raise AssertionError("unreachable")  # loop always returns or raises

    async def generate_text(self, *, model: str, prompt: str) -> str:
        return await self._generate(model=model, prompt=prompt, format_schema=None)

    async def chat_stream(
        self, *, model: str, messages: list[dict[str, object]], tools: list[dict[str, object]]
    ) -> AsyncIterator[ChatChunk]:
        payload = {"model": model, "messages": messages, "tools": tools, "stream": True}
        try:
            async with self.http.stream(
                "POST", f"{self.base_url}/api/chat", json=payload, timeout=120.0
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    message = json.loads(line).get("message", {})
                    tool_calls = [
                        ToolCall(name=tc["function"]["name"], arguments=tc["function"]["arguments"])
                        for tc in message.get("tool_calls") or []
                    ]
                    yield ChatChunk(content=message.get("content") or "", tool_calls=tool_calls)
        except httpx.HTTPError as e:
            raise OllamaUnreachableError(str(e)) from e

    async def _generate(
        self, *, model: str, prompt: str, format_schema: dict[str, object] | None
    ) -> str:
        payload: dict[str, object] = {"model": model, "prompt": prompt, "stream": False}
        if format_schema is not None:
            payload["format"] = format_schema
        try:
            resp = await self.http.post(
                f"{self.base_url}/api/generate", json=payload, timeout=120.0
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaUnreachableError(str(e)) from e
        response_text = resp.json().get("response", "")
        return str(response_text)

    async def pulled_models(self) -> set[str]:
        try:
            resp = await self.http.get(f"{self.base_url}/api/tags", timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError:
            return set()
        data = resp.json()
        return {m["name"] for m in data.get("models", [])}
