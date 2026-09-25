"""The bounded chat tool loop that drives /chat. MCP_ENGINES.md §Chat and
retrieval.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg

from app.chat.prompts import CHAT_SYSTEM_PROMPT, CHAT_TOOL_SCHEMAS
from app.chat.tools import auto_chart, dispatch
from app.config import settings
from app.llm.client import ChatChunk, OllamaClient, TokenUsage
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

    A third shape: confirmed live, asked "what are the different UP Excise shop
    types and license codes" — a question with real, substantial knowledge-base
    content already retrieved — the model's whole reply, all 78 completion
    tokens Ollama reported generating, reduced to a single streamed "#" with
    nothing else ever released. Markdown-filler characters (#, *, -, whitespace)
    stripped from both ends the same way the brace check strips {} — a reply
    that is only ever those, at any point while it is still arriving, is exactly
    as unhelpful as a bare "{}" and held back the same way.

    Both checks resolve within a few characters, so holding matching text back
    from the live stream costs nothing. `_needs_retry` below adds a fourth,
    slower-to-detect shape on top of this one — see its own docstring for why
    that one only gates the retry decision, not the live stream.
    """
    stripped = text.strip()
    if stripped.strip("{}") == "":
        return True
    if stripped.strip("#*-_ \n\t") == "":
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
    if "```sql" in text.strip().lower():
        return True
    # A raw tool-call JSON object narrated as text instead of a real tool_calls
    # entry — confirmed live, mid-response: a reply answered normally, then
    # trailed off into `{"name": "` before the connection ended. The same
    # failure shape _is_degenerate's tool-name-prefix check already catches
    # when the *whole* reply degenerates into a fake call; this catches it
    # showing up partway through an otherwise real answer instead, which is
    # why it waits for the full text the same way the fenced-sql check does.
    return '{"name"' in text


_CHART_CLAIM_PHRASES = (
    "here is a chart",
    "here's a chart",
    "chart showing",
    "chart below",
    "chart above",
    "graph showing",
    "visualization showing",
    "chart illustrat",
    "created a chart",
    "created a pie chart",
    "created a bar chart",
    "created a graph",
    "created a visualization",
    "made a chart",
    "made a pie chart",
    "made a bar chart",
    "made a graph",
    "made a visualization",
)


def _claims_unmade_chart(text: str, chart_made: bool) -> bool:
    """CHAT_SYSTEM_PROMPT already forbids claiming a chart exists unless
    make_chart was called and succeeded this turn -- confirmed live that this
    is a prompt instruction the model can still ignore outright, writing
    "Here is a chart showing..." with no make_chart call anywhere in the
    turn. Checked only once the full text is in, the same as _needs_retry's
    fenced-sql-block check, since these phrases read like ordinary prose
    until complete.
    """
    if chart_made:
        return False
    lowered = text.lower()
    return any(phrase in lowered for phrase in _CHART_CLAIM_PHRASES)


_TOOL_DECISION_NARRATION_PHRASES = (
    "no tool call is needed",
    "no tool call needed",
    "tool call is needed here",
    "i'll respond directly",
    "i will respond directly",
    "let me respond directly",
)


def _narrates_tool_decision(text: str) -> bool:
    """CHAT_SYSTEM_PROMPT already forbids narrating a tool-call decision by name
    ("Never narrate a tool call... Do not write things like 'No tool call is
    needed'") -- confirmed live that the prompt instruction alone is not
    reliable, the same as every other tool-calling gap here: asked a knowledge
    question with real content already retrieved by an earlier search_knowledge
    call this same turn, the model's whole reply was "# No tool call needed
    here; this is just plain-language shop-type information." -- the
    deliberation itself standing in for the answer, not the answer. Checked
    once the full text is in, same reasoning as _claims_unmade_chart: these
    phrases read like ordinary prose until complete, and holding a whole
    generation back per chunk risks the connection going quiet long enough to
    look dropped.
    """
    lowered = text.lower()
    return any(phrase in lowered for phrase in _TOOL_DECISION_NARRATION_PHRASES)


_REFUSAL_PHRASES = (
    "i can't provide",
    "i cannot provide",
    "i can't help with",
    "i cannot help with",
    "i can't assist",
    "i cannot assist",
    "i'm not able to provide",
    "i am not able to provide",
)


def _wrongly_refuses_after_a_successful_tool_call(
    text: str, last_tool_result: ToolResult | None
) -> bool:
    """A refusal reached after a tool call already succeeded this turn is a
    contradiction, not a legitimate decline -- the successful call is proof the
    question was answerable. Confirmed live twice, in two different refusal
    shapes: asked "what are the different UP Excise shop types and license
    codes" (the department's own terminology), the model retrieved exactly the
    right content and then declined anyway with the canned "I only answer UP
    Excise questions" line. Asked "What does the excise policy say about MGQ?",
    search_knowledge returned real Country Liquor Rules amendment text about
    licence fees and quotas, and the model refused with "I can't provide
    information or guidance on potentially illegal activities, including tax
    evasion and money laundering" -- a safety-style misfire on ordinary
    government rule text (licence fees, security deposits, penalties for
    shortfall) that only superficially resembles financial-crime language.
    """
    if last_tool_result is None or not last_tool_result.ok:
        return False
    lowered = text.lower()
    if "up excise questions" in lowered and ("only answer" in lowered or "only answers" in lowered):
        return True
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


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


async def _auto_chart_with_heartbeats(
    conversation_id: str,
    question: str,
    *,
    ollama: OllamaClient,
    usage: TokenUsage | None,
) -> AsyncIterator[HeartbeatEvent | ToolResult | None]:
    """Same heartbeat shape as `_dispatch_with_heartbeats`, for auto_chart's own
    Ollama call (Qwen planning the chart script) and sandboxed render — both can
    run long enough on this CPU-only box to need the same keep-alive.
    """
    task: asyncio.Task[ToolResult | None] = asyncio.create_task(
        auto_chart(conversation_id, question, ollama=ollama, usage=usage)
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


async def _generate_with_heartbeats(
    chunks: AsyncIterator[ChatChunk],
) -> AsyncIterator[HeartbeatEvent | ChatChunk]:
    """Same keep-alive shape as `_dispatch_with_heartbeats`, for the model's own
    turn generation rather than a tool call. Confirmed live: a compound question's
    follow-up turn (deciding whether to call make_chart after run_sql_query came
    back) can sit with no streamed content at all while the model composes a tool
    call, long enough to cross the PHP relay's 45s idle cap with nothing sent --
    only a running tool call had a heartbeat before this, not a turn's own
    generation.
    """
    queue: asyncio.Queue[ChatChunk | None] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for chunk in chunks:
                await queue.put(chunk)
        finally:
            await queue.put(None)

    task = asyncio.create_task(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_INTERVAL_S)
            except TimeoutError:
                yield HeartbeatEvent()
                continue
            if item is None:
                return
            yield item
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
    chart_made_this_turn = False
    usage = TokenUsage()

    for _ in range(settings.chat_max_tool_calls + 1):
        assistant_text = ""
        held = ""
        pending_calls: list[ToolCall] = []
        async for chunk in _generate_with_heartbeats(
            ollama.chat_stream(model=model, messages=messages, tools=CHAT_TOOL_SCHEMAS, usage=usage)
        ):
            if isinstance(chunk, HeartbeatEvent):
                yield chunk
                continue
            if chunk.content:
                assistant_text += chunk.content
                held += chunk.content
                if not _is_degenerate(held):
                    yield TokenEvent(delta=held)
                    held = ""
            pending_calls.extend(chunk.tool_calls)

        needs_plain_retry = _needs_retry(assistant_text)
        claims_chart = _claims_unmade_chart(assistant_text, chart_made_this_turn)
        wrongly_refuses = _wrongly_refuses_after_a_successful_tool_call(
            assistant_text, last_tool_result
        )
        narrates_decision = _narrates_tool_decision(assistant_text)
        if not pending_calls and (
            needs_plain_retry or claims_chart or wrongly_refuses or narrates_decision
        ):
            # The turn didn't need a tool and the model's tool-aware reply came
            # back degenerate — retry once as a plain chat call, same
            # retry-once shape guard_sql/render already use for a bad first
            # attempt. A live turn showed this retry can degenerate the exact same
            # way the first attempt did — narrating run_sql_query(question="...")
            # again after a failed call, even with no tools attached this time — so
            # the retry gets the same per-chunk holdback the first attempt already
            # has, instead of streaming it unconditionally.
            #
            # A chart claim with no chart attached is a different shape: there is no
            # make_chart tool to call anymore (a chart is chat/loop.py's own
            # deterministic step after run_sql_query, never the model's decision or
            # script to write — chat/tools.py's auto_chart docstring has the full
            # history) — the fix is telling the model plainly that no chart exists
            # and to drop the claim, the same feedback-and-retry shape a failed
            # run_sql_query call already gets. A wrong scope-refusal is the same
            # shape again: the fix is answering using the tool result already in
            # hand, not a fresh tool call, but tools stay attached in case the model
            # legitimately wants another run_sql_query call once it actually answers.
            retry_tools = [] if needs_plain_retry else CHAT_TOOL_SCHEMAS
            retry_messages = messages
            if claims_chart and not needs_plain_retry:
                retry_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your last reply referred to a chart, but no chart was "
                            "attached this turn. There is no tool to call for one — "
                            "answer the question in plain language, with no mention "
                            "of a chart at all."
                        ),
                    },
                ]
            elif wrongly_refuses and not needs_plain_retry:
                retry_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your last reply declined to answer, but a tool call "
                            "already succeeded this turn with relevant results — "
                            "the question is in scope. Answer it now using that "
                            "result."
                        ),
                    },
                ]
            elif narrates_decision and not needs_plain_retry:
                retry_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your last reply narrated whether a tool call was "
                            "needed instead of answering. Do not mention that "
                            "decision at all — either call a tool silently, or "
                            "write the plain-language answer itself, nothing else."
                        ),
                    },
                ]
            assistant_text = ""
            held = ""
            async for chunk in _generate_with_heartbeats(
                ollama.chat_stream(
                    model=model, messages=retry_messages, tools=retry_tools, usage=usage
                )
            ):
                if isinstance(chunk, HeartbeatEvent):
                    yield chunk
                    continue
                if chunk.content:
                    assistant_text += chunk.content
                    held += chunk.content
                    if not _is_degenerate(held):
                        yield TokenEvent(delta=held)
                        held = ""
                pending_calls.extend(chunk.tool_calls)
            if not pending_calls and (
                _needs_retry(assistant_text)
                or _claims_unmade_chart(assistant_text, chart_made_this_turn)
                or _wrongly_refuses_after_a_successful_tool_call(assistant_text, last_tool_result)
                or _narrates_tool_decision(assistant_text)
            ):
                # Both attempts came back degenerate — either genuinely empty (an 8B
                # model can fail to produce any follow-up text at all, with or without
                # a prior tool call), still narrating a fake call, still wrongly
                # declining a question a tool call already answered, or still
                # narrating the tool-call decision itself. Confirmed live: a chart-claim
                # retry can degenerate into narrating make_chart's own call as literal
                # `{"name": "make_chart", ...}` text instead of a real tool call — this
                # used only `_is_degenerate` before, which doesn't catch that shape (only
                # `_needs_retry` does), so the fake call streamed to the user with nothing
                # to correct it. `_needs_retry` also isn't held back per chunk, by design
                # (see its own docstring), so this retry's garbage may already be on the
                # wire; this is what stops it from standing as the turn's real answer.
                # With a tool result to reference, state its failure in plain terms (or,
                # for a successful call the model still won't use, its own summary
                # stands fine on its own); with none (the model never called a tool at
                # all, e.g. a knowledge question it tried to answer directly), a plain
                # retry prompt is the only honest fallback — there's no tool error to
                # show.
                assistant_text = (
                    _tool_failure_fallback(last_tool_result)
                    if last_tool_result is not None
                    else "I wasn't able to answer that — try rephrasing the question."
                )
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
                # k) — a validation error, same as a bad run_sql_query call. Fed back
                # as a failed tool result rather than raised, so this doesn't end the
                # whole turn the way it did before: the model sees why its arguments
                # were rejected and can call the tool again correctly.
                result = ToolResult(ok=False, summary=e.message)
            assert result is not None
            last_tool_result = result
            tool_calls_made += 1
            yield ToolResultEvent(name=call.name, ok=result.ok, summary=result.summary)
            messages.append({"role": "tool", "content": result.summary})

            # A chart is a deterministic step after a successful run_sql_query, not
            # something the chat model calls or writes the script for — confirmed
            # live, asking it to both judge whether a chart would help and author
            # Plotly Python as a tool argument is exactly the kind of judgment call
            # and coding task it gets wrong (chat/tools.py's auto_chart docstring has
            # the full history). Runs at most once per turn, right after the query
            # it charts, never at the model's own discretion.
            if call.name == "run_sql_query" and result.ok and request.want_chart:
                question = call.arguments.get("question")
                async for chart_item in _auto_chart_with_heartbeats(
                    request.conversation_id,
                    question if isinstance(question, str) else request.message,
                    ollama=ollama,
                    usage=usage,
                ):
                    if isinstance(chart_item, HeartbeatEvent):
                        yield chart_item
                    elif chart_item is not None:
                        tool_calls_made += 1
                        yield ToolCallEvent(name="make_chart", arguments={})
                        yield ToolResultEvent(
                            name="make_chart", ok=chart_item.ok, summary=chart_item.summary
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "content": (
                                    chart_item.summary
                                    if chart_item.ok
                                    else f"The chart could not be rendered: {chart_item.summary}"
                                ),
                            }
                        )
                        if chart_item.chart is not None:
                            chart_made_this_turn = True
                            yield ChartEvent(chart=chart_item.chart)
                    # item is None: nothing to chart (a single-row result) — no event,
                    # no message, the same silent skip pipeline.py's own row_count > 1
                    # gate already does for /query.

    raise ChatToolLoopExceededError()
