"""The bounded chat tool loop that drives /chat. MCP_ENGINES.md §Chat and
retrieval.
"""

import asyncio
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


@dataclass
class HeartbeatEvent:
    """A no-op line sent while a tool call is still running. A slow SQL plan or
    chart render otherwise leaves the ndjson stream silent for the whole tool
    call — long enough, on a compound question chaining several of these, for
    a client-side idle timeout (or an intermediate proxy) to drop the
    connection before the turn ever reaches a `done` or an `error` line. This
    is the same keep-alive mechanism a streaming tool-calling API relies on
    generally: the wire stays live off periodic bytes. A single fixed
    request-duration cap has no size that fits every turn.
    """


ChatEvent = TokenEvent | ToolCallEvent | ToolResultEvent | ChartEvent | DoneEvent | HeartbeatEvent


_TOOL_NAMES = ("search_knowledge", "run_sql_query", "make_chart")
_HEARTBEAT_INTERVAL_S = 15.0


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

    Both checks resolve within a few characters, so holding matching text back
    from the live stream costs nothing. `_needs_retry` below adds a third,
    slower-to-detect shape on top of this one — see its own docstring for why
    that one only gates the retry decision, not the live stream.
    """
    stripped = text.strip()
    if stripped.strip("{}") == "":
        return True
    return any(stripped.startswith(name[: len(stripped)]) for name in _TOOL_NAMES)


def _needs_retry(text: str) -> bool:
    """Whether a *completed* turn's text should be discarded and retried once,
    rather than shown as the final answer.

    Confirmed live: instead of calling run_sql_query, the model sometimes
    narrates "let me try running the following query" and writes its own
    guessed SQL in a fenced code block — exactly what CHAT_SYSTEM_PROMPT tells
    it never to do, since it has never seen the schema. Unlike the bare-"{}"
    and narrated-call cases in `_is_degenerate`, a fenced sql block can't be
    told apart from ordinary prose until a lot of it has already arrived, so
    this is only checked once the turn's full text is in — checking it
    per-chunk, the way `_is_degenerate` does, would hold the live stream back
    for however long that generation takes. That held silence is exactly what
    broke a real turn: withholding output for the length of a whole
    generation left the connection sending nothing for long enough that the
    browser's fetch dropped it as interrupted before the retry ever ran.
    Streaming the guessed SQL live and correcting it right after, the way this
    function's caller does, costs a moment of a wrong-looking answer instead
    of the connection itself.
    """
    if _is_degenerate(text):
        return True
    return "```sql" in text.strip().lower()


def _tool_failure_fallback(result: ToolResult) -> str:
    """The final answer when neither the tool-aware attempt nor the tools=[] retry
    produced usable prose — both held back per chunk by `_is_degenerate`, so this
    replaces what would otherwise have been an empty turn, not something already
    shown to the user.

    A successful call's own summary already reads fine standing alone ("Chart
    rendered." or a row-count sentence). A failed call's summary is a database or
    engine error — 'column sv.shop_id does not exist' means nothing to someone who
    didn't ask a SQL question — so this states the failure in plain terms first and
    keeps the technical detail after it, for whoever does want to check.
    """
    if result.ok:
        return result.summary
    return (
        f"I couldn't finish this part of the analysis: {result.summary}\n\n"
        "This usually means the question needs a different table, column, or date "
        "range than the one tried — try narrowing the date range, naming the shop "
        "category directly, or rephrasing the question."
    )


async def _dispatch_with_heartbeats(
    call: ToolCall,
    *,
    ollama: OllamaClient,
    schema_card: str,
    conversation_id: str,
    usage: TokenUsage | None,
) -> AsyncIterator[HeartbeatEvent | ToolResult]:
    """Runs dispatch() as a background task, yielding a HeartbeatEvent every
    _HEARTBEAT_INTERVAL_S seconds it is still running instead of leaving the
    caller's stream silent until it finishes. Ends by yielding the
    ToolResult itself; a raised ChatToolArgumentError propagates from
    `task.result()` the same as it would from a plain `await dispatch(...)`.
    """
    task: asyncio.Task[ToolResult] = asyncio.create_task(
        dispatch(
            call,
            ollama=ollama,
            schema_card=schema_card,
            conversation_id=conversation_id,
            usage=usage,
        )
    )
    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=_HEARTBEAT_INTERVAL_S)
            if done:
                yield task.result()
                return
            yield HeartbeatEvent()
    finally:
        if not task.done():
            task.cancel()


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
    last_tool_result: ToolResult | None = None
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

        if not pending_calls and _needs_retry(assistant_text):
            # The turn didn't need a tool and the model's tool-aware reply came
            # back degenerate — retry once as a plain chat call, same
            # retry-once shape guard_sql/render already use for a bad first
            # attempt. A live turn showed this retry can degenerate the exact same
            # way the first attempt did — narrating run_sql_query(question="...")
            # again after a failed call, even with no tools attached this time — so
            # the retry gets the same per-chunk holdback the first attempt already
            # has, instead of streaming it unconditionally.
            assistant_text = ""
            held = ""
            async for chunk in ollama.chat_stream(
                model=model, messages=messages, tools=[], usage=usage
            ):
                if chunk.content:
                    assistant_text += chunk.content
                    held += chunk.content
                    if not _is_degenerate(held):
                        yield TokenEvent(delta=held)
                        held = ""
            if _is_degenerate(assistant_text) and last_tool_result is not None:
                # Both attempts came back degenerate — either genuinely empty (an 8B
                # model can fail to produce any follow-up text at all after a tool
                # result) or still narrating a fake call. The per-chunk holdback above
                # kept every degenerate attempt off the wire, so nothing has been
                # shown to the user yet; this is the turn's first and only answer, a
                # plain statement of the failure with the tool's own error kept
                # available underneath it for whoever wants to check.
                assistant_text = _tool_failure_fallback(last_tool_result)
                yield TokenEvent(delta=assistant_text)
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
            result: ToolResult | None = None
            try:
                async for item in _dispatch_with_heartbeats(
                    call,
                    ollama=ollama,
                    schema_card=schema_card,
                    conversation_id=request.conversation_id,
                    usage=usage,
                ):
                    if isinstance(item, HeartbeatEvent):
                        yield item
                    else:
                        result = item
            except ChatToolArgumentError as e:
                # Llama's tool-calling fills in every schema property, sending an
                # explicit null for one it means to leave unset (e.g. search_knowledge's
                # k) — a validation error, same as a bad run_sql_query/make_chart call.
                # Fed back as a failed tool result rather than raised, so this doesn't
                # end the whole turn the way it did before: the model sees why its
                # arguments were rejected and can call the tool again correctly.
                result = ToolResult(ok=False, summary=e.message)
            assert result is not None
            last_tool_result = result
            tool_calls_made += 1
            yield ToolResultEvent(name=call.name, ok=result.ok, summary=result.summary)
            if result.chart is not None:
                yield ChartEvent(chart=result.chart)
            messages.append({"role": "tool", "content": result.summary})

    raise ChatToolLoopExceededError()
