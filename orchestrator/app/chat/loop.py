"""The bounded chat tool loop that drives /chat. MCP_ENGINES.md §Chat and
retrieval.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg

from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_TOOL_SCHEMAS
from app.chat.tools import dispatch
from app.config import settings
from app.llm.client import OllamaClient, TokenUsage
from app.pipeline import _select_model
from app.schemas import (
    ChartArtifact,
    ChatRequest,
    ChatToolArgumentError,
    ChatToolLoopExceededError,
    ChatTurn,
    ToolCall,
    ToolResult,
)


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
    prompt_tokens: int
    completion_tokens: int


ChatEvent = TokenEvent | ToolCallEvent | ToolResultEvent | ChartEvent | DoneEvent


_TOOL_NAMES = ("search_knowledge", "run_sql_query", "make_chart")


def _is_degenerate(text: str) -> bool:
    """llama3.1's tool-calling template occasionally answers a trivial message
    (e.g. "hi") with a bare "{}" instead of prose or a real tool call, once
    CHAT_TOOL_SCHEMAS is attached to the turn — confirmed directly against
    Ollama's /api/chat: the identical prompt without `tools` replies normally.
    Brace/whitespace-only output is that failure, not a real answer.

    The same template also sometimes narrates a *second* tool call as plain text
    instead of a real tool_calls entry — confirmed live, a chat turn answered
    `run_sql_query(question="...")` verbatim as its reply after an earlier tool
    call failed. `text` still being a prefix of one of the known tool names (or
    the full name itself, mid- or post-call) counts as degenerate too, so this
    accumulates unstreamed the same way a bare "{}" does instead of leaking the
    fake call's tokens to the user one at a time as they arrive.
    """
    stripped = text.strip()
    if stripped.strip("{}") == "":
        return True
    return any(stripped.startswith(name[: len(stripped)]) for name in _TOOL_NAMES)


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
    usage = TokenUsage()

    for _ in range(settings.chat_max_tool_calls + 1):
        assistant_text = ""
        held = ""
        pending_calls: list[ToolCall] = []
        async for chunk in ollama.chat_stream(
            model=model, messages=messages, tools=CHAT_TOOL_SCHEMAS, usage=usage
        ):
            if chunk.content:
                assistant_text += chunk.content
                held += chunk.content
                if not _is_degenerate(held):
                    yield TokenEvent(delta=held)
                    held = ""
            pending_calls.extend(chunk.tool_calls)

        if not pending_calls and _is_degenerate(assistant_text):
            # The turn didn't need a tool and the model's tool-aware reply came
            # back degenerate — retry once as a plain chat call, same
            # retry-once shape guard_sql/render already use for a bad first
            # attempt.
            assistant_text = ""
            async for chunk in ollama.chat_stream(
                model=model, messages=messages, tools=[], usage=usage
            ):
                if chunk.content:
                    assistant_text += chunk.content
                    yield TokenEvent(delta=chunk.content)
        messages.append({"role": "assistant", "content": assistant_text})

        if not pending_calls:
            yield DoneEvent(
                tool_calls_count=tool_calls_made,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
            return

        for call in pending_calls:
            yield ToolCallEvent(name=call.name, arguments=call.arguments)
            try:
                result = await dispatch(
                    call,
                    ollama=ollama,
                    schema_card=schema_card,
                    conversation_id=request.conversation_id,
                    usage=usage,
                )
            except ChatToolArgumentError as e:
                # Llama's tool-calling fills in every schema property, sending an
                # explicit null for one it means to leave unset (e.g. search_knowledge's
                # k) — a validation error, same as a bad run_sql_query/make_chart call.
                # Fed back as a failed tool result rather than raised, so this doesn't
                # end the whole turn the way it did before: the model sees why its
                # arguments were rejected and can call the tool again correctly.
                result = ToolResult(ok=False, summary=e.message)
            tool_calls_made += 1
            yield ToolResultEvent(name=call.name, ok=result.ok, summary=result.summary)
            if result.chart is not None:
                yield ChartEvent(chart=result.chart)
            messages.append({"role": "tool", "content": result.summary})

    raise ChatToolLoopExceededError()
