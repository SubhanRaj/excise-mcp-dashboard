"""The bounded chat tool loop that drives /chat. MCP_ENGINES.md §Chat and
retrieval.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg

from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_TOOL_SCHEMAS
from app.chat.tools import dispatch
from app.config import settings
from app.llm.client import OllamaClient
from app.pipeline import _select_model
from app.schemas import ChartArtifact, ChatRequest, ChatToolLoopExceededError, ChatTurn, ToolCall


@dataclass
class TokenEvent:
    delta: str


@dataclass
class ToolCallEvent:
    name: str
    arguments: dict[str, object]


@dataclass
class ToolResultEvent:
    name: str
    ok: bool
    summary: str


@dataclass
class ChartEvent:
    chart: ChartArtifact


@dataclass
class DoneEvent:
    tool_calls_count: int


ChatEvent = TokenEvent | ToolCallEvent | ToolResultEvent | ChartEvent | DoneEvent


def _build_messages(message: str, history: list[ChatTurn]) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages.extend({"role": t.role, "content": t.content} for t in history)
    messages.append({"role": "user", "content": message})
    return messages


async def run_chat(
    request: ChatRequest,
    *,
    pool: asyncpg.Pool,
    ollama: OllamaClient,
    schema_card: str,
) -> AsyncIterator[ChatEvent]:
    model = _select_model(request.model, settings.ollama_chat_model)
    messages = _build_messages(request.message, request.history)
    tool_calls_made = 0

    for _ in range(settings.chat_max_tool_calls + 1):
        assistant_text = ""
        pending_calls: list[ToolCall] = []
        async for chunk in ollama.chat_stream(
            model=model, messages=messages, tools=CHAT_TOOL_SCHEMAS
        ):
            if chunk.content:
                assistant_text += chunk.content
                yield TokenEvent(delta=chunk.content)
            pending_calls.extend(chunk.tool_calls)
        messages.append({"role": "assistant", "content": assistant_text})

        if not pending_calls:
            yield DoneEvent(tool_calls_count=tool_calls_made)
            return

        for call in pending_calls:
            yield ToolCallEvent(name=call.name, arguments=call.arguments)
            result = await dispatch(
                call,
                ollama=ollama,
                schema_card=schema_card,
                conversation_id=request.conversation_id,
            )
            tool_calls_made += 1
            yield ToolResultEvent(name=call.name, ok=result.ok, summary=result.summary)
            if result.chart is not None:
                yield ChartEvent(chart=result.chart)
            messages.append({"role": "tool", "content": result.summary})

    raise ChatToolLoopExceededError()
